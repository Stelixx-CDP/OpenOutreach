import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.core.management import call_command
import io

from linkedin.enums import ProfileState
from linkedin.models import Task, ActionLog
from crm.models import Deal, Outcome
from crm.models.lead import Lead
from chat.models import ChatMessage
from linkedin.db.deals import set_profile_state
from linkedin.db.leads import create_enriched_lead, promote_lead_to_deal
from linkedin.tasks.follow_up import handle_follow_up
from linkedin.agents.follow_up import _render_system_prompt, FollowUpDecision
from linkedin.notifications import notify

SAMPLE_PROFILE = {
    "first_name": "Alice",
    "last_name": "Smith",
    "headline": "Engineer",
    "positions": [{"company_name": "Acme"}],
}


def _make_connected(session, public_id="alice"):
    url = f"https://www.linkedin.com/in/{public_id}/"
    create_enriched_lead(session, url, SAMPLE_PROFILE)
    promote_lead_to_deal(session, public_id)
    deal = Deal.objects.get(lead__public_identifier=public_id, campaign=session.campaign)
    deal.profile_summary = {"first_name": "Alice", "last_name": "Smith"}
    deal.state = ProfileState.CONNECTED.value
    deal.save()
    # Clear tasks so we can check task enqueuing cleanly
    Task.objects.all().delete()


@pytest.mark.django_db
class TestIntentDetectionAndEscalation:

    def test_render_prompt_classification(self, fake_session):
        """Verify new classification instructions are rendered in follow_up prompt."""
        _make_connected(fake_session, "alice")
        deal = Deal.objects.get(lead__public_identifier="alice", campaign=fake_session.campaign)
        
        prompt = _render_system_prompt(
            fake_session,
            deal,
            recent_messages=[],
            lead_first_name_safe="Alice",
            conversation_mode="LEAD_REPLIED",
        )
        
        assert "Classification — required for EVERY response" in prompt
        assert "intent" in prompt
        assert "situation" in prompt
        assert "needs_human" in prompt

    def test_handle_follow_up_guard(self, fake_session):
        """CRIT-1: handle_follow_up should skip if deal is not CONNECTED (e.g., ESCALATED)."""
        _make_connected(fake_session, "alice")
        deal = Deal.objects.get(lead__public_identifier="alice", campaign=fake_session.campaign)
        deal.state = ProfileState.ESCALATED.value
        deal.save()

        task = Task.objects.create(
            task_type=Task.TaskType.FOLLOW_UP,
            status=Task.Status.PENDING,
            scheduled_at=timezone.now(),
            payload={"campaign_id": fake_session.campaign.pk, "public_id": "alice"},
        )

        with patch("linkedin.agents.follow_up.run_follow_up_agent") as mock_agent:
            handle_follow_up(task, fake_session, qualifiers=[])
            # The agent should not be called because deal is ESCALATED
            mock_agent.assert_not_called()

    def test_handle_follow_up_escalate_high_intent(self, fake_session):
        """Verify transition to ESCALATED and Telegram alert for high intent."""
        _make_connected(fake_session, "alice")
        deal = Deal.objects.get(lead__public_identifier="alice", campaign=fake_session.campaign)

        # Create mock ChatMessage as last incoming message
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Lead)
        ChatMessage.objects.create(
            content_type=ct,
            object_id=deal.lead_id,
            is_outgoing=False,
            content="Can we hop on a call tomorrow?",
            creation_date=timezone.now()
        )

        task = Task.objects.create(
            task_type=Task.TaskType.FOLLOW_UP,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"campaign_id": fake_session.campaign.pk, "public_id": "alice"},
        )

        mock_decision = FollowUpDecision(
            action="send_message",
            message="Absolutely, here is my link.",
            intent="high",
            situation="engaging",
            follow_up_hours=24.0,
        )

        with (
            patch("linkedin.agents.follow_up.run_follow_up_agent", return_value=mock_decision),
            patch("linkedin.actions.message.send_raw_message", return_value=True) as mock_send,
            patch("linkedin.notifications.safe_notify") as mock_notify,
        ):
            handle_follow_up(task, fake_session, qualifiers=[])
            
            # 1. State must become ESCALATED
            deal.refresh_from_db()
            assert deal.state == ProfileState.ESCALATED.value
            assert "intent=high, situation=engaging" in deal.reason
            
            # 2. Bridge message should be sent
            mock_send.assert_called_once()
            
            # 3. Notification should trigger with correct details
            mock_notify.assert_any_call(
                "escalation",
                public_id="alice",
                intent="high",
                situation="engaging",
                last_message="Can we hop on a call tomorrow?",
                linkedin_url=deal.lead.linkedin_url,
                campaign=deal.campaign,
            )
            
            # 4. No follow_up task should be enqueued
            assert not Task.objects.filter(
                task_type=Task.TaskType.FOLLOW_UP,
                status=Task.Status.PENDING,
                payload__public_id="alice"
            ).exists()

    def test_handle_follow_up_escalate_needs_human(self, fake_session):
        """Verify transition to ESCALATED for needs_human situation."""
        _make_connected(fake_session, "alice")
        deal = Deal.objects.get(lead__public_identifier="alice", campaign=fake_session.campaign)

        # Create mock ChatMessage
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Lead)
        ChatMessage.objects.create(
            content_type=ct,
            object_id=deal.lead_id,
            is_outgoing=False,
            content="I am seeing a bug on page 2.",
            creation_date=timezone.now()
        )

        task = Task.objects.create(
            task_type=Task.TaskType.FOLLOW_UP,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"campaign_id": fake_session.campaign.pk, "public_id": "alice"},
        )

        mock_decision = FollowUpDecision(
            action="send_message",
            message="I'll flag this to our team.",
            intent="low",
            situation="needs_human",
            follow_up_hours=12.0,
        )

        with (
            patch("linkedin.agents.follow_up.run_follow_up_agent", return_value=mock_decision),
            patch("linkedin.actions.message.send_raw_message", return_value=True) as mock_send,
            patch("linkedin.notifications.safe_notify") as mock_notify,
        ):
            handle_follow_up(task, fake_session, qualifiers=[])
            
            deal.refresh_from_db()
            assert deal.state == ProfileState.ESCALATED.value
            assert "situation=needs_human" in deal.reason
            mock_send.assert_called_once()
            
            mock_notify.assert_any_call(
                "escalation",
                public_id="alice",
                intent="low",
                situation="needs_human",
                last_message="I am seeing a bug on page 2.",
                linkedin_url=deal.lead.linkedin_url,
                campaign=deal.campaign,
            )

    def test_handle_follow_up_no_escalate_completed(self, fake_session):
        """HIGH-3: Do NOT escalate if action is mark_completed (even if intent/situation is high)."""
        _make_connected(fake_session, "alice")
        deal = Deal.objects.get(lead__public_identifier="alice", campaign=fake_session.campaign)

        task = Task.objects.create(
            task_type=Task.TaskType.FOLLOW_UP,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"campaign_id": fake_session.campaign.pk, "public_id": "alice"},
        )

        mock_decision = FollowUpDecision(
            action="mark_completed",
            outcome="converted",
            intent="high",
            situation="engaging",
            follow_up_hours=24.0,
        )

        with (
            patch("linkedin.agents.follow_up.run_follow_up_agent", return_value=mock_decision),
            patch("linkedin.notifications.safe_notify") as mock_notify,
        ):
            handle_follow_up(task, fake_session, qualifiers=[])
            
            deal.refresh_from_db()
            assert deal.state == ProfileState.COMPLETED.value
            assert deal.outcome == Outcome.CONVERTED
            # Ensure "escalation" was not called
            for call in mock_notify.call_args_list:
                assert call[0][0] != "escalation"

    def test_handle_follow_up_normal_flow(self, fake_session):
        """Verify normal messaging flow without escalation for low intent & cold situation."""
        _make_connected(fake_session, "alice")
        deal = Deal.objects.get(lead__public_identifier="alice", campaign=fake_session.campaign)

        task = Task.objects.create(
            task_type=Task.TaskType.FOLLOW_UP,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"campaign_id": fake_session.campaign.pk, "public_id": "alice"},
        )

        mock_decision = FollowUpDecision(
            action="send_message",
            message="Just bumping this.",
            intent="low",
            situation="cold",
            follow_up_hours=24.0,
        )

        with (
            patch("linkedin.agents.follow_up.run_follow_up_agent", return_value=mock_decision),
            patch("linkedin.actions.message.send_raw_message", return_value=True) as mock_send,
            patch("linkedin.notifications.safe_notify") as mock_notify,
        ):
            handle_follow_up(task, fake_session, qualifiers=[])
            
            deal.refresh_from_db()
            assert deal.state == ProfileState.CONNECTED.value
            mock_send.assert_called_once()
            mock_notify.assert_not_called()
            
            # Should schedule next follow_up
            assert Task.objects.filter(
                task_type=Task.TaskType.FOLLOW_UP,
                status=Task.Status.PENDING,
                payload__public_id="alice"
            ).exists()

    def test_telegram_escalation_markup(self):
        """Verify Telegram escalation event passes correct reply_markup with profile URL."""
        with (
            patch("linkedin.notifications._get_token", return_value="fake_token"),
            patch("linkedin.notifications._get_chat_id", return_value="fake_chat_id"),
            patch("linkedin.notifications.send_text") as mock_send,
        ):
            notify(
                "escalation",
                public_id="alice",
                intent="high",
                situation="engaging",
                last_message="Hello Diego",
                linkedin_url="https://linkedin.com/in/alice",
            )
            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            assert "YÊU CẦU XỬ LÝ THỦ CÔNG (ESCALATION)" in args[0]
            assert "Hello Diego" in args[0]
            assert kwargs["reply_markup"] == {
                "inline_keyboard": [
                    [
                        {"text": "📱 Open Chat", "url": "https://linkedin.com/in/alice"}
                    ]
                ]
            }

    def test_send_daily_report_escalated_section(self, fake_session):
        """HIGH-4: Verify escalated deals are listed separately in daily report and excluded from hot deals."""
        _make_connected(fake_session, "alice")
        _make_connected(fake_session, "bob")
    
        deal_alice = Deal.objects.get(lead__public_identifier="alice", campaign=fake_session.campaign)
        deal_bob = Deal.objects.get(lead__public_identifier="bob", campaign=fake_session.campaign)
    
        # Alice is Escalated
        deal_alice.state = ProfileState.ESCALATED.value
        deal_alice.reason = "Needs human support"
        deal_alice.save()
    
        # Bob is Hot (replied today, active)
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Lead)
        ChatMessage.objects.create(
            content_type=ct,
            object_id=deal_bob.lead_id,
            is_outgoing=False,
            content="Count me in!",
            creation_date=timezone.now()
        )
    
        with patch("linkedin.management.commands.send_daily_report.send_text") as mock_send_report:
            out = io.StringIO()
            call_command("send_daily_report", stdout=out)
    
            mock_send_report.assert_called_once()
            report_text = mock_send_report.call_args[0][0]
    
            # Alice should be in ESCALATED section
            assert "Deals cần xử lý thủ công (ESCALATED):" in report_text
            assert "alice" in report_text
            assert "Needs human support" in report_text
    
            # Bob should be in Hot Leads section
            assert "Hot Leads phản hồi cần check:" in report_text
            assert "bob" in report_text
    
            # Escalated should NOT pollute Hot Leads
            # split on 🚨 instead of 💬 since the 🚨 Escalated section is immediately after Hot Leads
            hot_leads_section = report_text.split("Hot Leads phản hồi cần check:")[1].split("🚨")[0]
            assert "bob" in hot_leads_section
            assert "alice" not in hot_leads_section
