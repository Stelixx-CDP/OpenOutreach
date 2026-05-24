# tests/test_telegram_listener.py
import pytest
from unittest.mock import patch, MagicMock

from linkedin.management.commands.telegram_listener import listen_to_telegram


@pytest.fixture(autouse=True)
def setup_telegram_env(monkeypatch):
    """Setup dummy telegram env vars for listener tests."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "0000000000:AAFakeTokenForTestingOnly00000000000")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1234567890")


@patch("requests.get")
@patch("linkedin.management.commands.telegram_listener.call_command")
def test_telegram_listener_executes_daily_report_on_correct_chat(mock_call_command, mock_get):
    """Test listener calls send_daily_report when command is received from correct chat."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": [
            {
                "update_id": 100,
                "message": {
                    "chat": {"id": -1234567890},
                    "text": "/daily-report"
                }
            }
        ]
    }
    mock_get.return_value = mock_response

    # Use max_iterations=1 to exit after one polling cycle
    listen_to_telegram(max_iterations=1)

    mock_call_command.assert_called_once_with("send_daily_report")


@patch("requests.get")
@patch("linkedin.management.commands.telegram_listener.call_command")
def test_telegram_listener_ignores_incorrect_chat(mock_call_command, mock_get):
    """Test listener ignores commands coming from unauthorized chat IDs."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": [
            {
                "update_id": 100,
                "message": {
                    "chat": {"id": 99999999},  # Unauthorized chat ID
                    "text": "/daily-report"
                }
            }
        ]
    }
    mock_get.return_value = mock_response

    listen_to_telegram(max_iterations=1)

    mock_call_command.assert_not_called()


@patch("requests.get")
@patch("linkedin.management.commands.telegram_listener.call_command")
def test_telegram_listener_accepts_alternative_commands(mock_call_command, mock_get):
    """Test listener accepts /report and /daily_report commands."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": [
            {
                "update_id": 101,
                "message": {
                    "chat": {"id": -1234567890},
                    "text": "/report"
                }
            }
        ]
    }
    mock_get.return_value = mock_response

    listen_to_telegram(max_iterations=1)

    mock_call_command.assert_called_once_with("send_daily_report")
