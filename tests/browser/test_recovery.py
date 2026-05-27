# tests/browser/test_recovery.py
import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
from playwright.sync_api import Error as PlaywrightError

from linkedin.browser.session import AccountSession
from linkedin.daemon import run_daemon
from linkedin.models import Task, Campaign

class StopDaemon(Exception):
    pass

@pytest.mark.django_db
class TestBrowserRecovery:
    def test_session_is_alive(self):
        # Setup mock profile
        mock_profile = MagicMock()
        session = AccountSession(mock_profile)
        
        # Test Case 1: page is None
        session.page = None
        assert not session.is_alive()
        
        # Test Case 2: page is closed
        mock_page = MagicMock()
        mock_page.is_closed.return_value = True
        session.page = mock_page
        assert not session.is_alive()
        
        # Test Case 3: page raises exception on evaluate
        mock_page.is_closed.return_value = False
        mock_page.evaluate.side_effect = Exception("Browser crashed")
        session.page = mock_page
        assert not session.is_alive()
        
        # Test Case 4: page works
        mock_page.evaluate.side_effect = None
        mock_page.evaluate.return_value = 2
        assert session.is_alive()

    @patch("linkedin.daemon.Task.objects.claim_next")
    @patch("linkedin.daemon.seconds_until_active", return_value=0.0)
    @patch("linkedin.daemon._HANDLERS")
    @patch("linkedin.daemon.failure_diagnostics")
    @patch("linkedin.tasks.scheduler.reconcile")
    def test_daemon_retries_on_playwright_error_and_succeeds(
        self, mock_reconcile, mock_diagnostics, mock_handlers, mock_active, mock_claim_next, db
    ):
        # Setup campaign
        campaign = Campaign.objects.create(name="Test Campaign")
        
        # Setup task
        task = Task.objects.create(
            task_type=Task.TaskType.CONNECT,
            status=Task.Status.PENDING,
            scheduled_at=timezone.now(),
            payload={"campaign_id": campaign.pk}
        )
        
        # Mock handlers and diagnostics
        mock_handler = MagicMock()
        # First call raises PlaywrightError, second call succeeds
        mock_handler.side_effect = [PlaywrightError("Closed"), None]
        mock_handlers.get.return_value = mock_handler
        
        # Mock claim_next to return task then raise StopDaemon to exit loop
        mock_claim_next.side_effect = [task, StopDaemon()]
        
        # Setup fake session
        session = MagicMock()
        session.campaigns = [campaign]
        session.page = MagicMock()
        session.is_alive.return_value = True
        
        with pytest.raises(StopDaemon):
            run_daemon(session)
            
        # Verify handler was called twice
        assert mock_handler.call_count == 2
        # Verify session was closed and ensure_browser called to recover
        session.close.assert_called_once()
        session.ensure_browser.assert_called_once()
        # Verify task was marked completed eventually (because it succeeded on 2nd attempt)
        task.refresh_from_db()
        assert task.status == Task.Status.COMPLETED

    @patch("linkedin.daemon.Task.objects.claim_next")
    @patch("linkedin.daemon.seconds_until_active", return_value=0.0)
    @patch("linkedin.daemon._HANDLERS")
    @patch("linkedin.daemon.failure_diagnostics")
    @patch("linkedin.daemon._safe_notify")
    @patch("linkedin.tasks.scheduler.reconcile")
    def test_daemon_retries_exhausted_marks_failed(
        self, mock_reconcile, mock_notify, mock_diagnostics, mock_handlers, mock_active, mock_claim_next, db
    ):
        # Setup campaign
        campaign = Campaign.objects.create(name="Test Campaign 2")
        
        # Setup task
        task = Task.objects.create(
            task_type=Task.TaskType.CONNECT,
            status=Task.Status.PENDING,
            scheduled_at=timezone.now(),
            payload={"campaign_id": campaign.pk}
        )
        
        # Mock handler to raise PlaywrightError consistently
        mock_handler = MagicMock()
        mock_handler.side_effect = PlaywrightError("Browser process crashed")
        mock_handlers.get.return_value = mock_handler
        
        # Mock claim_next to return task then raise StopDaemon to exit loop
        mock_claim_next.side_effect = [task, StopDaemon()]
        
        # Setup fake session
        session = MagicMock()
        session.campaigns = [campaign]
        session.page = MagicMock()
        session.is_alive.return_value = True
        
        with pytest.raises(StopDaemon):
            run_daemon(session)
            
        # Verify handler was called 3 times (attempt 0, retry 1, retry 2)
        assert mock_handler.call_count == 3
        # Verify session was closed and ensure_browser called twice for recovery
        assert session.close.call_count == 2
        assert session.ensure_browser.call_count == 2
        
        # Verify task was marked failed
        task.refresh_from_db()
        assert task.status == Task.Status.FAILED
        # Verify Telegram warning was sent
        mock_notify.assert_called_with(
            "browser_crash",
            task_type=task.task_type,
            error="Browser process crashed",
            screenshot=None,
            campaign=campaign
        )

    @patch("linkedin.daemon.Task.objects.claim_next")
    @patch("linkedin.daemon.seconds_until_active", return_value=0.0)
    @patch("linkedin.tasks.scheduler.reconcile")
    def test_daemon_health_check_closes_dead_browser(
        self, mock_reconcile, mock_active, mock_claim_next, db
    ):
        # Mock claim_next to raise StopDaemon immediately to exit loop
        mock_claim_next.side_effect = StopDaemon()
        
        # Setup fake session with a live page but returns dead health check
        session = MagicMock()
        session.page = MagicMock()
        session.is_alive.return_value = False
        
        with pytest.raises(StopDaemon):
            run_daemon(session)
            
        # Verify session health check was called and closed since it was dead
        session.is_alive.assert_called_once()
        session.close.assert_called_once()
