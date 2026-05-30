# tests/tasks/test_follow_up_logic.py
import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from linkedin.enums import ProfileState
from linkedin.models import Task, ActionLog, PendingMessage
from crm.models import Deal, Outcome
from crm.models.lead import Lead
from chat.models import ChatMessage
from linkedin.tasks.follow_up import handle_follow_up
from linkedin.tasks.send_approved_message import handle_send_approved_message
from linkedin.agents.follow_up import FollowUpDecision
from linkedin.db.deals import set_profile_state
from linkedin.db.leads import create_enriched_lead, promote_lead_to_deal

SAMPLE_PROFILE = {
    "first_name": "Charlie",
    "last_name": "Logic",
    "headline": "Tester",
    "positions": [{"company_name": "Logic Corp"}],
}


def _make_connected(session, public_id="charlie"):
    url = f"https://www.linkedin.com/in/{public_id}/"
    create_enriched_lead(session, url, SAMPLE_PROFILE)
    promote_lead_to_deal(session, public_id)
    deal = Deal.objects.get(lead__public_identifier=public_id, campaign=session.campaign)
    deal.profile_summary = {"first_name": "Charlie", "last_name": "Logic"}
    deal.state = ProfileState.CONNECTED.value
    deal.linkedin_profile = session.linkedin_profile
    deal.connect_sent_at = timezone.now()
    deal.save()
    Task.objects.all().delete()
    PendingMessage.objects.all().delete()


@pytest.mark.django_db
class TestFollowUpLogicFlows:

    def test_follow_up_syncs_first(self, fake_session):
        """1. handle_follow_up thực hiện sync_conversation trước khi chạy AI."""
        _make_connected(fake_session, "charlie")
        deal = Deal.objects.get(lead__public_identifier="charlie", campaign=fake_session.campaign)

        task = Task.objects.create(
            task_type=Task.TaskType.FOLLOW_UP,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"campaign_id": fake_session.campaign.pk, "public_id": "charlie"},
        )

        mock_decision = FollowUpDecision(
            action="wait",
            intent="low",
            situation="cold",
            follow_up_hours=24.0,
        )

        calls = []

        def track_sync(session, public_id):
            calls.append("sync")

        def track_agent(session, deal_obj):
            calls.append("agent")
            return mock_decision

        with (
            patch("linkedin.db.chat.sync_conversation", side_effect=track_sync) as mock_sync,
            patch("linkedin.agents.follow_up.run_follow_up_agent", side_effect=track_agent) as mock_agent,
        ):
            handle_follow_up(task, fake_session, qualifiers=[])
            
            # Đảm bảo sync được gọi trước agent
            assert calls == ["sync", "agent"]
            mock_sync.assert_called_once_with(fake_session, "charlie")
            mock_agent.assert_called_once()

    def test_follow_up_sync_failure_crashes_task(self, fake_session):
        """2. Sync failure trong follow_up làm crash task và không tiếp tục gửi tin."""
        _make_connected(fake_session, "charlie")

        task = Task.objects.create(
            task_type=Task.TaskType.FOLLOW_UP,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"campaign_id": fake_session.campaign.pk, "public_id": "charlie"},
        )

        with (
            patch("linkedin.db.chat.sync_conversation", side_effect=ValueError("Sync connection failed")),
            patch("linkedin.agents.follow_up.run_follow_up_agent") as mock_agent,
        ):
            with pytest.raises(ValueError, match="Sync connection failed"):
                handle_follow_up(task, fake_session, qualifiers=[])

            # Đảm bảo luồng AI và gửi tin không được thực thi khi sync crash
            mock_agent.assert_not_called()

    def test_follow_up_rate_limit_does_not_block_escalation_completed_wait(self, fake_session):
        """3. Rate limit chỉ chặn gửi tin nhắn, không chặn các hành động khác (ESCALATED, COMPLETED, wait)."""
        _make_connected(fake_session, "charlie")
        deal = Deal.objects.get(lead__public_identifier="charlie", campaign=fake_session.campaign)

        # Tạo inbound message từ lead để bypass early rate limit check dành cho nudge
        lead_ct = ContentType.objects.get_for_model(Lead)
        ChatMessage.objects.create(
            content_type=lead_ct,
            object_id=deal.lead_id,
            is_outgoing=False,
            content="Yes, please tell me more.",
            creation_date=timezone.now(),
        )

        task = Task.objects.create(
            task_type=Task.TaskType.FOLLOW_UP,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"campaign_id": fake_session.campaign.pk, "public_id": "charlie"},
        )

        # Giả lập đã hết follow-up quota
        with patch.object(fake_session.linkedin_profile, "can_execute", return_value=False):
            # A. Test action 'wait' không bị chặn
            mock_decision_wait = FollowUpDecision(
                action="wait",
                intent="low",
                situation="cold",
                follow_up_hours=24.0,
            )
            with (
                patch("linkedin.agents.follow_up.run_follow_up_agent", return_value=mock_decision_wait),
                patch("linkedin.tasks.scheduler.enqueue_follow_up") as mock_enqueue,
                patch("linkedin.db.chat.sync_conversation"),
            ):
                handle_follow_up(task, fake_session, qualifiers=[])
                # Trạng thái deal vẫn là CONNECTED và được re-enqueue tiếp
                deal.refresh_from_db()
                assert deal.state == ProfileState.CONNECTED.value
                mock_enqueue.assert_called_once()

            # B. Test action 'mark_completed' không bị chặn
            mock_decision_completed = FollowUpDecision(
                action="mark_completed",
                outcome="converted",
                intent="low",
                situation="cold",
                follow_up_hours=24.0,
            )
            task.status = Task.Status.RUNNING
            task.save()
            with (
                patch("linkedin.agents.follow_up.run_follow_up_agent", return_value=mock_decision_completed),
                patch("linkedin.db.chat.sync_conversation"),
            ):
                handle_follow_up(task, fake_session, qualifiers=[])
                deal.refresh_from_db()
                assert deal.state == ProfileState.COMPLETED.value
                assert deal.outcome == Outcome.CONVERTED

            # C. Test action 'send_message' (nhưng escalate) không bị chặn cập nhật trạng thái ESCALATED
            deal.state = ProfileState.CONNECTED.value
            deal.save()
            mock_decision_escalate = FollowUpDecision(
                action="send_message",
                message="Let's jump on a call",
                intent="high",
                situation="engaging",
                follow_up_hours=24.0,
            )
            task.status = Task.Status.RUNNING
            task.save()
            with (
                patch("linkedin.agents.follow_up.run_follow_up_agent", return_value=mock_decision_escalate),
                patch("linkedin.actions.message.send_raw_message") as mock_send,
                patch("linkedin.notifications.safe_notify"),
                patch("linkedin.db.chat.sync_conversation"),
            ):
                handle_follow_up(task, fake_session, qualifiers=[])
                deal.refresh_from_db()
                # Trạng thái deal phải chuyển thành ESCALATED
                assert deal.state == ProfileState.ESCALATED.value
                # Nhưng do rate limit (can_execute trả về False), tin nhắn bridge thực tế không được gửi
                mock_send.assert_not_called()

    def test_send_approved_message_syncs_before_sending(self, fake_session):
        """4. send_approved_message thực hiện sync conversation trước khi gửi tin nhắn đã duyệt."""
        _make_connected(fake_session, "charlie")
        deal = Deal.objects.get(lead__public_identifier="charlie", campaign=fake_session.campaign)
        deal.state = ProfileState.WAITING_APPROVAL.value
        deal.save()

        pending = PendingMessage.objects.create(
            deal=deal,
            message_text="Hello, this is approved",
            decision_json={"action": "send_message", "follow_up_hours": 24.0, "intent": "low", "situation": "cold"},
        )

        task = Task.objects.create(
            task_type=Task.TaskType.SEND_APPROVED_MESSAGE,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"pending_message_id": pending.id, "campaign_id": fake_session.campaign.pk},
        )

        calls = []

        def track_sync(session, public_id):
            calls.append("sync")

        def track_send(session, profile, message):
            calls.append("send")
            return True

        with (
            patch("linkedin.db.chat.sync_conversation", side_effect=track_sync) as mock_sync,
            patch("linkedin.actions.message.send_raw_message", side_effect=track_send) as mock_send,
        ):
            handle_send_approved_message(task, fake_session, qualifiers=[])
            
            # Đảm bảo đồng bộ được gọi trước khi gửi tin nhắn đi
            assert calls == ["sync", "send"]
            mock_sync.assert_called_once_with(fake_session, "charlie")
            mock_send.assert_called_once()

    def test_send_approved_message_sync_failure_crashes_task(self, fake_session):
        """5. Sync failure trong approved flow làm crash task và dừng luồng gửi tin."""
        _make_connected(fake_session, "charlie")
        deal = Deal.objects.get(lead__public_identifier="charlie", campaign=fake_session.campaign)
        deal.state = ProfileState.WAITING_APPROVAL.value
        deal.save()

        pending = PendingMessage.objects.create(
            deal=deal,
            message_text="Approved message",
            decision_json={"action": "send_message", "follow_up_hours": 24.0, "intent": "low", "situation": "cold"},
        )

        task = Task.objects.create(
            task_type=Task.TaskType.SEND_APPROVED_MESSAGE,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"pending_message_id": pending.id, "campaign_id": fake_session.campaign.pk},
        )

        with (
            patch("linkedin.db.chat.sync_conversation", side_effect=ValueError("Sync failure")),
            patch("linkedin.actions.message.send_raw_message") as mock_send,
        ):
            with pytest.raises(ValueError, match="Sync failure"):
                handle_send_approved_message(task, fake_session, qualifiers=[])

            # Đảm bảo tin nhắn không được gửi đi khi sync lỗi
            mock_send.assert_not_called()

    def test_approved_message_cancelled_if_new_inbound(self, fake_session):
        """6. Inbound message mới sau thời điểm duyệt sẽ hủy gửi tin cũ, chuyển Deal về CONNECTED để AI regenerate."""
        _make_connected(fake_session, "charlie")
        deal = Deal.objects.get(lead__public_identifier="charlie", campaign=fake_session.campaign)
        deal.state = ProfileState.WAITING_APPROVAL.value
        deal.save()

        # Tạo pending message duyệt lúc 10 phút trước
        ten_mins_ago = timezone.now() - timezone.timedelta(minutes=10)
        pending = PendingMessage.objects.create(
            deal=deal,
            message_text="Approved pitch",
            decision_json={"action": "send_message", "follow_up_hours": 24.0, "intent": "low", "situation": "cold"},
        )
        # Hack created_at vì auto_now_add=True
        PendingMessage.objects.filter(pk=pending.id).update(created_at=ten_mins_ago)
        pending.refresh_from_db()

        # Tạo một inbound message của lead được gửi lúc 5 phút trước (sau pending message)
        five_mins_ago = timezone.now() - timezone.timedelta(minutes=5)
        lead_ct = ContentType.objects.get_for_model(Lead)
        ChatMessage.objects.create(
            content_type=lead_ct,
            object_id=deal.lead_id,
            is_outgoing=False,
            content="Thanks, but I have a question first.",
            creation_date=five_mins_ago,
        )

        task = Task.objects.create(
            task_type=Task.TaskType.SEND_APPROVED_MESSAGE,
            status=Task.Status.RUNNING,
            scheduled_at=timezone.now(),
            payload={"pending_message_id": pending.id, "campaign_id": fake_session.campaign.pk},
        )

        with (
            patch("linkedin.db.chat.sync_conversation") as mock_sync,
            patch("linkedin.actions.message.send_raw_message") as mock_send,
            patch("linkedin.tasks.scheduler.enqueue_follow_up") as mock_enqueue,
        ):
            handle_send_approved_message(task, fake_session, qualifiers=[])

            # 1. Sync conversation vẫn được gọi để cập nhật
            mock_sync.assert_called_once_with(fake_session, "charlie")

            # 2. Không được gửi tin nhắn duyệt cũ
            mock_send.assert_not_called()

            # 3. PendingMessage bị xóa khỏi DB
            assert not PendingMessage.objects.filter(pk=pending.id).exists()

            # 4. Trạng thái Deal quay lại CONNECTED với lý do phù hợp
            deal.refresh_from_db()
            assert deal.state == ProfileState.CONNECTED.value
            assert deal.reason == "new_inbound_after_approval"

            # 5. Phải lập lịch lại FOLLOW_UP ngay lập tức (delay_seconds=10) để AI regenerate
            mock_enqueue.assert_called_once_with(fake_session.campaign.pk, "charlie", delay_seconds=10)
