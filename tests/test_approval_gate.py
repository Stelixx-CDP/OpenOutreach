import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from linkedin.enums import ProfileState
from linkedin.models import Task, ActionLog, Campaign, PendingMessage, AgentFeedback
from crm.models import Deal, Outcome
from crm.models.lead import Lead
from chat.models import ChatMessage
from linkedin.db.deals import set_profile_state
from linkedin.db.leads import create_enriched_lead, promote_lead_to_deal
from linkedin.tasks.follow_up import handle_follow_up, should_require_approval
from linkedin.tasks.send_approved_message import handle_send_approved_message
from linkedin.management.commands.telegram_listener import listen_to_telegram
from linkedin.agents.follow_up import _render_system_prompt, FollowUpDecision, run_follow_up_agent

SAMPLE_PROFILE = {
    "first_name": "Bob",
    "last_name": "Test",
    "headline": "Tester",
    "positions": [{"company_name": "QA"}],
}

@pytest.fixture(autouse=True)
def setup_telegram_env(monkeypatch):
    """Setup dummy telegram env vars for listener tests."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "0000000000:AAFakeTokenForTestingOnly00000000000")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1234567890")


def _make_connected(session, public_id="bob"):
    url = f"https://www.linkedin.com/in/{public_id}/"
    create_enriched_lead(session, url, SAMPLE_PROFILE)
    promote_lead_to_deal(session, public_id)
    deal = Deal.objects.get(lead__public_identifier=public_id, campaign=session.campaign)
    deal.profile_summary = {"first_name": "Bob", "last_name": "Test"}
    deal.state = ProfileState.CONNECTED.value
    deal.save()
    Task.objects.all().delete()
    PendingMessage.objects.all().delete()
    AgentFeedback.objects.all().delete()


@pytest.mark.django_db
class TestApprovalGate:

    def test_should_require_approval_modes(self, fake_session):
        _make_connected(fake_session, "bob")
        deal = Deal.objects.get(lead__public_identifier="bob", campaign=fake_session.campaign)
        campaign = deal.campaign

        # 1. Mode 'auto' -> Should never require approval
        campaign.approval_mode = "auto"
        campaign.save()
        decision_send = FollowUpDecision(action="send_message", message="Hello", intent="low", situation="cold", follow_up_hours=24.0)
        assert not should_require_approval(deal, decision_send)

        # 2. Mode 'all' -> Should require approval for send_message, but not wait/mark_completed
        campaign.approval_mode = "all"
        campaign.save()
        decision_wait = FollowUpDecision(action="wait", intent="low", situation="cold", follow_up_hours=24.0)
        assert should_require_approval(deal, decision_send)
        assert not should_require_approval(deal, decision_wait)

        # 3. Mode 'first_touch'
        campaign.approval_mode = "first_touch"
        campaign.save()
        # No outgoing message yet -> Requires approval
        assert should_require_approval(deal, decision_send)
        # Create an outgoing message
        ct = ContentType.objects.get_for_model(Lead)
        ChatMessage.objects.create(
            content_type=ct,
            object_id=deal.lead_id,
            is_outgoing=True,
            content="Pitch",
            creation_date=timezone.now()
        )
        # Already has outgoing message -> Does not require approval
        assert not should_require_approval(deal, decision_send)

        # 4. Mode 'high_intent'
        campaign.approval_mode = "high_intent"
        campaign.save()
        decision_high = FollowUpDecision(action="send_message", message="High", intent="high", situation="engaging", follow_up_hours=24.0)
        decision_medium = FollowUpDecision(action="send_message", message="Medium", intent="medium", situation="engaging", follow_up_hours=24.0)
        decision_needs_human = FollowUpDecision(action="send_message", message="Human", intent="low", situation="needs_human", follow_up_hours=24.0)
        decision_low_cold = FollowUpDecision(action="send_message", message="Low", intent="low", situation="cold", follow_up_hours=24.0)
        
        assert should_require_approval(deal, decision_high)
        assert should_require_approval(deal, decision_medium)
        assert should_require_approval(deal, decision_needs_human)
        assert not should_require_approval(deal, decision_low_cold)

    def test_handle_follow_up_early_return(self, fake_session):
        _make_connected(fake_session, "bob")
        deal = Deal.objects.get(lead__public_identifier="bob", campaign=fake_session.campaign)
        campaign = deal.campaign
        campaign.approval_mode = "all"
        campaign.save()

        task = Task.objects.create(
            task_type=Task.TaskType.FOLLOW_UP,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"campaign_id": fake_session.campaign.pk, "public_id": "bob"},
        )

        mock_decision = FollowUpDecision(
            action="send_message",
            message="Please approve this message.",
            intent="low",
            situation="cold",
            follow_up_hours=24.0,
        )

        with (
            patch("linkedin.agents.follow_up.run_follow_up_agent", return_value=mock_decision),
            patch("linkedin.notifications.safe_notify") as mock_notify,
            patch("linkedin.actions.message.send_raw_message") as mock_send,
        ):
            handle_follow_up(task, fake_session, qualifiers=[])

            # 1. State must move to WAITING_APPROVAL
            deal.refresh_from_db()
            assert deal.state == ProfileState.WAITING_APPROVAL.value
            assert deal.reason == "waiting_approval"

            # 2. PendingMessage must be created
            pending = PendingMessage.objects.filter(deal=deal).first()
            assert pending is not None
            assert pending.message_text == "Please approve this message."
            assert pending.decision_json["action"] == "send_message"

            # 3. safe_notify was called with pending_approval event
            mock_notify.assert_any_call(
                "pending_approval",
                pending_message=pending,
                campaign=campaign,
            )

            # 4. send_raw_message was NOT called
            mock_send.assert_not_called()

            # 5. No follow_up task scheduled
            assert not Task.objects.filter(task_type=Task.TaskType.FOLLOW_UP, status=Task.Status.PENDING).exists()

    def test_handle_send_approved_message_success(self, fake_session):
        _make_connected(fake_session, "bob")
        deal = Deal.objects.get(lead__public_identifier="bob", campaign=fake_session.campaign)
        deal.state = ProfileState.WAITING_APPROVAL.value
        deal.save()

        pending = PendingMessage.objects.create(
            deal=deal,
            message_text="Approved message text",
            decision_json={"action": "send_message", "follow_up_hours": 24.0, "intent": "low", "situation": "cold"},
        )

        task = Task.objects.create(
            task_type=Task.TaskType.SEND_APPROVED_MESSAGE,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"pending_message_id": pending.id, "campaign_id": fake_session.campaign.pk},
        )

        with patch("linkedin.actions.message.send_raw_message", return_value=True) as mock_send:
            handle_send_approved_message(task, fake_session, qualifiers=[])

            # 1. Message should be sent
            mock_send.assert_called_once_with(fake_session, {"public_identifier": "bob", "urn": ""}, "Approved message text")

            # 2. State returns to CONNECTED
            deal.refresh_from_db()
            assert deal.state == ProfileState.CONNECTED.value
            assert deal.reason == "approved_message_sent"

            # 3. Next follow up scheduled
            assert Task.objects.filter(
                task_type=Task.TaskType.FOLLOW_UP,
                status=Task.Status.PENDING,
                payload__public_id="bob"
            ).exists()

            # 4. PendingMessage is deleted
            assert not PendingMessage.objects.filter(pk=pending.id).exists()

    def test_handle_send_approved_message_escalated(self, fake_session):
        _make_connected(fake_session, "bob")
        deal = Deal.objects.get(lead__public_identifier="bob", campaign=fake_session.campaign)
        deal.state = ProfileState.WAITING_APPROVAL.value
        deal.save()

        pending = PendingMessage.objects.create(
            deal=deal,
            message_text="Approved bridge message",
            decision_json={"action": "send_message", "follow_up_hours": 24.0, "intent": "high", "situation": "needs_human"},
        )

        task = Task.objects.create(
            task_type=Task.TaskType.SEND_APPROVED_MESSAGE,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"pending_message_id": pending.id, "campaign_id": fake_session.campaign.pk},
        )

        with (
            patch("linkedin.actions.message.send_raw_message", return_value=True) as mock_send,
            patch("linkedin.notifications.safe_notify") as mock_notify,
        ):
            handle_send_approved_message(task, fake_session, qualifiers=[])

            # 1. Message sent
            mock_send.assert_called_once()

            # 2. State changes to ESCALATED
            deal.refresh_from_db()
            assert deal.state == ProfileState.ESCALATED.value

            # 3. Telegram escalation notify is triggered
            mock_notify.assert_any_call(
                "escalation",
                public_id="bob",
                intent="high",
                situation="needs_human",
                last_message="(no reply yet)",
                linkedin_url=deal.lead.linkedin_url,
                campaign=deal.campaign,
            )
            assert mock_notify.call_args[0][0] == "escalation"

            # 4. PendingMessage deleted
            assert not PendingMessage.objects.filter(pk=pending.id).exists()

    def test_handle_send_approved_message_fail(self, fake_session):
        _make_connected(fake_session, "bob")
        deal = Deal.objects.get(lead__public_identifier="bob", campaign=fake_session.campaign)
        deal.state = ProfileState.WAITING_APPROVAL.value
        deal.save()

        pending = PendingMessage.objects.create(
            deal=deal,
            message_text="Fail to send",
            decision_json={"action": "send_message", "follow_up_hours": 24.0, "intent": "low", "situation": "cold"},
        )

        task = Task.objects.create(
            task_type=Task.TaskType.SEND_APPROVED_MESSAGE,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"pending_message_id": pending.id, "campaign_id": fake_session.campaign.pk},
        )

        with patch("linkedin.actions.message.send_raw_message", return_value=False) as mock_send:
            handle_send_approved_message(task, fake_session, qualifiers=[])

            # State moves to QUALIFIED
            deal.refresh_from_db()
            assert deal.state == ProfileState.QUALIFIED.value
            assert deal.reason == "approved_send_failed"

            # PendingMessage is deleted
            assert not PendingMessage.objects.filter(pk=pending.id).exists()

    @patch("requests.get")
    @patch("requests.post")
    def test_telegram_listener_callback_approve(self, mock_post, mock_get, fake_session):
        _make_connected(fake_session, "bob")
        deal = Deal.objects.get(lead__public_identifier="bob", campaign=fake_session.campaign)
        pending = PendingMessage.objects.create(
            deal=deal,
            message_text="Approved message via callback",
            decision_json={"action": "send_message", "follow_up_hours": 24.0, "intent": "low", "situation": "cold"},
            telegram_message_id=9876,
        )

        # Mock updates from Telegram
        mock_resp_get = MagicMock()
        mock_resp_get.status_code = 200
        mock_resp_get.json.return_value = {
            "result": [
                {
                    "update_id": 200,
                    "callback_query": {
                        "id": "cb_123",
                        "data": f"approve:{pending.id}",
                        "message": {
                            "chat": {"id": -1234567890},
                            "message_id": 9876,
                        }
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp_get

        # Mock post requests for answering callback and editing message
        mock_resp_post = MagicMock()
        mock_resp_post.status_code = 200
        mock_resp_post.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp_post

        listen_to_telegram(max_iterations=1)

        # 1. Callback query answered
        mock_post.assert_any_call(
            "https://api.telegram.org/bot0000000000:AAFakeTokenForTestingOnly00000000000/answerCallbackQuery",
            json={"callback_query_id": "cb_123"},
            timeout=10
        )

        # 2. Original message edited
        # Find calls to editMessageText
        edit_calls = [call for call in mock_post.call_args_list if "editMessageText" in call[0][0]]
        assert len(edit_calls) > 0
        assert "Đã duyệt và đang xếp lịch gửi" in edit_calls[0][1]["json"]["text"]

        # 3. AgentFeedback is created
        fb = AgentFeedback.objects.filter(deal=deal).first()
        assert fb is not None
        assert fb.feedback_type == AgentFeedback.FeedbackType.APPROVED
        assert fb.original_message == "Approved message via callback"

        # 4. SEND_APPROVED_MESSAGE task is queued
        assert Task.objects.filter(
            task_type=Task.TaskType.SEND_APPROVED_MESSAGE,
            status=Task.Status.PENDING,
            payload__pending_message_id=pending.id,
        ).exists()

    @patch("requests.get")
    @patch("requests.post")
    def test_telegram_listener_callback_skip(self, mock_post, mock_get, fake_session):
        _make_connected(fake_session, "bob")
        deal = Deal.objects.get(lead__public_identifier="bob", campaign=fake_session.campaign)
        pending = PendingMessage.objects.create(
            deal=deal,
            message_text="Skip message via callback",
            decision_json={"action": "send_message", "follow_up_hours": 24.0, "intent": "low", "situation": "cold"},
            telegram_message_id=9876,
        )

        mock_resp_get = MagicMock()
        mock_resp_get.status_code = 200
        mock_resp_get.json.return_value = {
            "result": [
                {
                    "update_id": 201,
                    "callback_query": {
                        "id": "cb_124",
                        "data": f"skip:{pending.id}",
                        "message": {
                            "chat": {"id": -1234567890},
                            "message_id": 9876,
                        }
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp_get

        mock_resp_post = MagicMock()
        mock_resp_post.status_code = 200
        mock_resp_post.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp_post

        listen_to_telegram(max_iterations=1)

        # 1. State returns to CONNECTED
        deal.refresh_from_db()
        assert deal.state == ProfileState.CONNECTED.value
        assert deal.reason == "skipped_by_user"

        # 2. AgentFeedback rejection created
        fb = AgentFeedback.objects.filter(deal=deal).first()
        assert fb is not None
        assert fb.feedback_type == AgentFeedback.FeedbackType.REJECTED

        # 3. Next follow up enqueued exactly once (no duplicates)
        follow_up_tasks = Task.objects.filter(
            task_type=Task.TaskType.FOLLOW_UP,
            status=Task.Status.PENDING,
            payload__public_id="bob"
        )
        assert follow_up_tasks.count() == 1

        # 4. PendingMessage is deleted
        assert not PendingMessage.objects.filter(pk=pending.id).exists()

    @patch("requests.get")
    @patch("requests.post")
    def test_telegram_listener_reply_edit(self, mock_post, mock_get, fake_session):
        _make_connected(fake_session, "bob")
        deal = Deal.objects.get(lead__public_identifier="bob", campaign=fake_session.campaign)
        pending = PendingMessage.objects.create(
            deal=deal,
            message_text="Original bad text",
            decision_json={"action": "send_message", "follow_up_hours": 24.0, "intent": "low", "situation": "cold"},
            telegram_message_id=9876,
        )

        # Mock reply message from Telegram
        mock_resp_get = MagicMock()
        mock_resp_get.status_code = 200
        mock_resp_get.json.return_value = {
            "result": [
                {
                    "update_id": 202,
                    "message": {
                        "chat": {"id": -1234567890},
                        "message_id": 9999,
                        "text": "Corrected better text",
                        "reply_to_message": {
                            "message_id": 9876,
                        }
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp_get

        mock_resp_post = MagicMock()
        mock_resp_post.status_code = 200
        mock_resp_post.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp_post

        listen_to_telegram(max_iterations=1)

        # 1. AgentFeedback created with type EDITED
        fb = AgentFeedback.objects.filter(deal=deal).first()
        assert fb is not None
        assert fb.feedback_type == AgentFeedback.FeedbackType.EDITED
        assert fb.original_message == "Original bad text"
        assert fb.corrected_message == "Corrected better text"

        # 2. PendingMessage message_text updated
        pending.refresh_from_db()
        assert pending.message_text == "Corrected better text"

        # 3. SEND_APPROVED_MESSAGE task is queued
        assert Task.objects.filter(
            task_type=Task.TaskType.SEND_APPROVED_MESSAGE,
            status=Task.Status.PENDING,
            payload__pending_message_id=pending.id,
        ).exists()

        # 4. Confirmation message sent
        send_calls = [call for call in mock_post.call_args_list if "sendMessage" in call[0][0]]
        assert len(send_calls) > 0
        assert "Đã ghi nhận nội dung sửa đổi" in send_calls[0][1]["json"]["text"]

    def test_prompt_corrections_injection(self, fake_session):
        _make_connected(fake_session, "bob")
        deal = Deal.objects.get(lead__public_identifier="bob", campaign=fake_session.campaign)
        campaign = deal.campaign

        # Create EDITED agent feedbacks
        AgentFeedback.objects.create(
            campaign=campaign,
            deal=deal,
            original_message="Hi friend, please buy.",
            corrected_message="Hi Bob, would you be interested in checking our platform?",
            feedback_type=AgentFeedback.FeedbackType.EDITED,
        )

        AgentFeedback.objects.create(
            campaign=campaign,
            deal=deal,
            original_message="We are robust and leverage synergy.",
            corrected_message="We help teams collaborate faster.",
            feedback_type=AgentFeedback.FeedbackType.EDITED,
        )

        from linkedin.agents.follow_up import _load_recent_corrections
        corrections = _load_recent_corrections(campaign)
        assert len(corrections) == 2
        assert corrections[0]["original"] == "We are robust and leverage synergy."
        assert corrections[0]["corrected"] == "We help teams collaborate faster."

        prompt = _render_system_prompt(
            fake_session,
            deal,
            recent_messages=[],
            lead_first_name_safe="Bob",
            conversation_mode="LEAD_REPLIED",
            recent_corrections=corrections,
        )

        # Verify that corrections are present in the rendered prompt
        assert "Style Corrections (learn from these)" in prompt
        assert "Hi friend, please buy." in prompt
        assert "Hi Bob, would you be interested in checking our platform?" in prompt
        assert "We help teams collaborate faster." in prompt

    @patch("linkedin.management.commands.send_daily_report.send_text")
    def test_daily_report_includes_waiting_approval(self, mock_send_report, fake_session):
        from django.core.management import call_command
        import io
        
        _make_connected(fake_session, "bob")
        deal_bob = Deal.objects.get(lead__public_identifier="bob", campaign=fake_session.campaign)
        deal_bob.state = ProfileState.WAITING_APPROVAL.value
        deal_bob.save()

        # Record action log (connect sent)
        ActionLog.objects.create(
            linkedin_profile=fake_session.linkedin_profile,
            campaign=fake_session.campaign,
            action_type=ActionLog.ActionType.CONNECT
        )

        out = io.StringIO()
        call_command("send_daily_report", stdout=out)

        mock_send_report.assert_called_once()
        report_text = mock_send_report.call_args[0][0]

        # Connects accepted today should be 1 (counting WAITING_APPROVAL)
        assert "Accepted 1" in report_text
        # Accepted 7d should be 1 (counting WAITING_APPROVAL)
        assert "Đồng ý 1" in report_text
        # Acceptance rate 7d should be 100.0%
        assert "100.0%" in report_text
        # Bob is WAITING_APPROVAL, so he should NOT be in hot leads list
        if "Hot Leads phản hồi cần check:" in report_text:
            hot_leads_part = report_text.split("Hot Leads phản hồi cần check:")[1].split("📊")[0]
            assert "bob" not in hot_leads_part
        # Bob should be in WAITING_APPROVAL section
        assert "Deals chờ duyệt (WAITING_APPROVAL):" in report_text
        assert "bob" in report_text
