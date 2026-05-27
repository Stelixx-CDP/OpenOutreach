# tests/test_account_safety.py
import datetime
from unittest.mock import patch

import pytest
from django.utils import timezone

from crm.models import Deal
from linkedin.enums import ProfileState
from linkedin.models import ActionLog, Task
from linkedin.safety import compute_acceptance_rate_7d, auto_throttle_check
from linkedin.tasks.scheduler import reconcile


@pytest.mark.django_db
class TestAutoThrottle:
    def test_compute_acceptance_rate_7d_zero_sent(self, fake_session):
        lp = fake_session.linkedin_profile
        rate = compute_acceptance_rate_7d(lp)
        assert rate is None

    @patch("linkedin.notifications.safe_notify")
    def test_auto_throttle_skip_when_zero_sent(self, mock_notify, fake_session):
        lp = fake_session.linkedin_profile
        lp.original_connect_daily_limit = 20
        lp.connect_daily_limit = 20
        lp.save()
        
        auto_throttle_check(lp)
        
        lp.refresh_from_db()
        assert lp.connect_daily_limit == 20
        mock_notify.assert_not_called()

    def test_compute_acceptance_rate_7d_success(self, fake_session):
        lp = fake_session.linkedin_profile
        campaign = fake_session.campaign
        
        # Create 10 sent connects in last 7 days
        for _ in range(10):
            ActionLog.objects.create(
                linkedin_profile=lp,
                campaign=campaign,
                action_type=ActionLog.ActionType.CONNECT
            )
            
        # Create 3 accepted deals in last 7 days
        from crm.models import Lead
        for i in range(3):
            lead = Lead.objects.create(
                public_identifier=f"lead_{i}",
                linkedin_url=f"https://linkedin.com/in/lead_{i}"
            )
            Deal.objects.create(
                lead=lead,
                campaign=campaign,
                state=ProfileState.CONNECTED.value
            )
            
        rate = compute_acceptance_rate_7d(lp)
        assert rate == 0.3  # 3 / 10

    @patch("linkedin.notifications.safe_notify")
    def test_auto_throttle_reduce_limit(self, mock_notify, fake_session):
        lp = fake_session.linkedin_profile
        campaign = fake_session.campaign
        
        # Initialize limits
        lp.original_connect_daily_limit = 20
        lp.connect_daily_limit = 20
        lp.save()
        
        # 10 sent, 1 accepted (10% < 15%)
        for _ in range(10):
            ActionLog.objects.create(
                linkedin_profile=lp,
                campaign=campaign,
                action_type=ActionLog.ActionType.CONNECT
            )
        from crm.models import Lead
        lead = Lead.objects.create(
            public_identifier="lead_under_throttle",
            linkedin_url="https://linkedin.com/in/lead_under_throttle"
        )
        Deal.objects.create(
            lead=lead,
            campaign=campaign,
            state=ProfileState.CONNECTED.value
        )
        
        auto_throttle_check(lp)
        
        lp.refresh_from_db()
        assert lp.connect_daily_limit == 10  # 20 // 2
        mock_notify.assert_called_once_with(
            "auto_throttle",
            profile=lp,
            rate=0.1,
            new_limit=10,
            severity="warning"
        )

    @patch("linkedin.notifications.safe_notify")
    def test_auto_throttle_restore_limit(self, mock_notify, fake_session):
        lp = fake_session.linkedin_profile
        campaign = fake_session.campaign
        
        # Initialize limits with throttled value
        lp.original_connect_daily_limit = 20
        lp.connect_daily_limit = 10
        lp.save()
        
        # 10 sent, 4 accepted (40% > 30%)
        for _ in range(10):
            ActionLog.objects.create(
                linkedin_profile=lp,
                campaign=campaign,
                action_type=ActionLog.ActionType.CONNECT
            )
        from crm.models import Lead
        for i in range(4):
            lead = Lead.objects.create(
                public_identifier=f"lead_restore_{i}",
                linkedin_url=f"https://linkedin.com/in/lead_restore_{i}"
            )
            Deal.objects.create(
                lead=lead,
                campaign=campaign,
                state=ProfileState.CONNECTED.value
            )
            
        auto_throttle_check(lp)
        
        lp.refresh_from_db()
        assert lp.connect_daily_limit == 12  # 10 + 2
        mock_notify.assert_called_once_with(
            "auto_throttle",
            profile=lp,
            rate=0.4,
            new_limit=12,
            severity="info"
        )


@pytest.mark.django_db
class TestSchedulerWithdrawInterval:
    def test_reconcile_creates_withdraw_task(self, fake_session):
        # Clear existing tasks
        Task.objects.all().delete()
        
        # Trigger reconcile
        reconcile(fake_session)
        
        # Verify a WITHDRAW_OLD_INVITES task is scheduled
        withdraw_task = Task.objects.filter(task_type=Task.TaskType.WITHDRAW_OLD_INVITES).first()
        assert withdraw_task is not None
        assert withdraw_task.status == Task.Status.PENDING
        assert withdraw_task.payload == {"profile_id": fake_session.linkedin_profile.pk}

    def test_reconcile_does_not_duplicate_withdraw_task(self, fake_session):
        # Clear existing tasks
        Task.objects.all().delete()
        
        # Reconcile twice
        reconcile(fake_session)
        reconcile(fake_session)
        
        # Verify only 1 WITHDRAW_OLD_INVITES task exists
        assert Task.objects.filter(task_type=Task.TaskType.WITHDRAW_OLD_INVITES).count() == 1

    def test_reconcile_schedules_7_days_after_last_completed(self, fake_session):
        # Clear existing tasks
        Task.objects.all().delete()
        
        # Create a completed task in the past
        completed_time = timezone.now() - datetime.timedelta(days=2)
        Task.objects.create(
            task_type=Task.TaskType.WITHDRAW_OLD_INVITES,
            status=Task.Status.COMPLETED,
            scheduled_at=completed_time - datetime.timedelta(hours=1),
            completed_at=completed_time,
            payload={"profile_id": fake_session.linkedin_profile.pk}
        )
        
        # Reconcile
        reconcile(fake_session)
        
        # Verify next task is scheduled at completed_time + 7 days
        pending_task = Task.objects.filter(
            task_type=Task.TaskType.WITHDRAW_OLD_INVITES,
            status=Task.Status.PENDING
        ).first()
        assert pending_task is not None
        expected_time = completed_time + datetime.timedelta(days=7)
        assert abs((pending_task.scheduled_at - expected_time).total_seconds()) < 1.0
