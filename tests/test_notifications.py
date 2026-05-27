# tests/test_notifications.py
import pytest
from unittest.mock import patch, MagicMock
from django.core.management import call_command
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
import datetime
from zoneinfo import ZoneInfo

from linkedin.models import ActionLog, Campaign, Task, LinkedInProfile
from linkedin.notifications import send_text, send_photo, notify
from crm.models.deal import Deal, Outcome
from crm.models.lead import Lead
from chat.models import ChatMessage
from linkedin.enums import ProfileState


@pytest.fixture(autouse=True)
def setup_telegram_env(monkeypatch):
    """Set dummy Telegram credentials via env vars for testing."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "0000000000:AAFakeTokenForTestingOnly00000000000")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1234567890")


@patch("requests.post")
def test_send_text_success(mock_post):
    """Test send_text successfully sends HTML message to Telegram."""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"ok": True, "result": {"message_id": 123}}

    message_id = send_text("<b>Hello World</b>")

    assert message_id == 123
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/sendMessage")
    assert kwargs["json"]["chat_id"] == "-1234567890"
    assert kwargs["json"]["text"] == "<b>Hello World</b>"
    assert kwargs["json"]["parse_mode"] == "HTML"


@patch("requests.post")
def test_send_text_truncates_long_messages(mock_post):
    """Test send_text truncates messages exceeding Telegram's 4096 char limit."""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"ok": True, "result": {"message_id": 123}}

    long_text = "A" * 5000
    message_id = send_text(long_text)

    assert message_id == 123
    sent_text = mock_post.call_args[1]["json"]["text"]
    assert len(sent_text) <= 4096
    assert "…(truncated)" in sent_text


@patch("requests.post")
def test_send_photo_success(mock_post):
    """Test send_photo successfully sends photo with caption to Telegram."""
    mock_post.return_value.status_code = 200

    success = send_photo(b"fake_image_bytes", "Error occurred")

    assert success is True
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/sendPhoto")
    assert kwargs["data"]["chat_id"] == "-1234567890"
    assert kwargs["data"]["caption"] == "Error occurred"
    assert "photo" in kwargs["files"]


@patch("linkedin.notifications.send_text")
def test_notify_lead_reply(mock_send_text, fake_session):
    """Test notify formats lead_reply correctly."""
    notify(
        "lead_reply",
        public_identifier="john-doe",
        text="Hello, I want to book a call.",
        campaign=fake_session.campaign
    )

    mock_send_text.assert_called_once()
    message = mock_send_text.call_args[0][0]
    assert f"[{fake_session.campaign.name}] Lead phản hồi mới!" in message
    assert "john-doe" in message
    assert "Hello, I want to book a call." in message


@patch("linkedin.notifications.send_text")
def test_notify_deal_state_changed(mock_send_text, fake_session):
    """Test notify formats deal_state_changed correctly."""
    notify(
        "deal_state_changed",
        lead="john-doe",
        old_state="PENDING",
        new_state="CONNECTED",
        reason="Connection accepted",
        campaign=fake_session.campaign
    )

    mock_send_text.assert_called_once()
    message = mock_send_text.call_args[0][0]
    assert f"[{fake_session.campaign.name}] Trạng thái Deal cập nhật" in message
    assert "john-doe" in message
    assert "PENDING" in message
    assert "CONNECTED" in message
    assert "Connection accepted" in message


@patch("linkedin.notifications.send_text")
def test_notify_deal_state_unchanged_is_noop(mock_send_text, fake_session):
    """Test notify does not send when state didn't actually change."""
    notify(
        "deal_state_changed",
        lead="john-doe",
        old_state="PENDING",
        new_state="PENDING",
        campaign=fake_session.campaign,
    )
    mock_send_text.assert_not_called()


@patch("linkedin.notifications.send_photo")
def test_notify_browser_crash_with_screenshot(mock_send_photo, fake_session):
    """Test notify formats browser_crash with photo correctly."""
    notify(
        "browser_crash",
        task_type="connect",
        error="TargetClosedError",
        screenshot=b"screenshot_data",
        campaign=fake_session.campaign
    )

    mock_send_photo.assert_called_once()
    args = mock_send_photo.call_args[0]
    assert args[0] == b"screenshot_data"
    assert f"[{fake_session.campaign.name}] Cảnh báo: Trình duyệt bị Crash!" in args[1]
    assert "connect" in args[1]
    assert "TargetClosedError" in args[1]


@patch("linkedin.management.commands.send_daily_report.send_text")
def test_send_daily_report_command(mock_send_text, fake_session, db):
    """Test send_daily_report command successfully generates and sends stats."""
    campaign = fake_session.campaign
    lead_ct = ContentType.objects.get_for_model(Lead)

    # 1. Create a lead and a deal
    lead = Lead.objects.create(
        linkedin_url="https://linkedin.com/in/john-doe",
        public_identifier="john-doe"
    )
    deal = Deal.objects.create(
        lead=lead,
        campaign=campaign,
        state=ProfileState.CONNECTED,
        outcome=""
    )

    # 2. Record action log (connect sent)
    ActionLog.objects.create(
        linkedin_profile=fake_session.linkedin_profile,
        campaign=campaign,
        action_type=ActionLog.ActionType.CONNECT
    )

    # 3. Create a sent outgoing message (Drill-down)
    ChatMessage.objects.create(
        content_type=lead_ct,
        object_id=lead.pk,
        content="Hello, John! How are you?",
        is_outgoing=True,
        linkedin_urn="urn:li:fs_message:1"
    )

    # 4. Create an incoming message (lead reply)
    ChatMessage.objects.create(
        content_type=lead_ct,
        object_id=lead.pk,
        content="I am doing well, thank you.",
        is_outgoing=False,
        linkedin_urn="urn:li:fs_message:2"
    )

    # Run django command
    call_command("send_daily_report")

    # Verify report is sent
    mock_send_text.assert_called_once()
    report_msg = mock_send_text.call_args[0][0]

    assert "DAILY DIGEST BÁO CÁO HÀNG NGÀY" in report_msg
    assert campaign.name in report_msg
    assert "Connects: Sent 1" in report_msg
    assert "Follow-ups sent: 0" in report_msg  # ActionLog not created for follow_up yet
    assert "Tin nhắn Agent đã gửi hôm nay" in report_msg
    assert "john-doe" in report_msg
    assert "Hello, John! How are you?" in report_msg


@patch("linkedin.notifications.send_text")
def test_notify_validation_failed(mock_send_text, fake_session):
    """Test notify formats validation_failed correctly."""
    notify(
        "validation_failed",
        lead="john-doe",
        rejected_message="Hi John, nice to meet you!",
        reason="Repeated greeting word",
        campaign=fake_session.campaign
    )

    mock_send_text.assert_called_once()
    message = mock_send_text.call_args[0][0]
    assert f"[{fake_session.campaign.name}] Tin nhắn không qua kiểm duyệt AI!" in message
    assert "john-doe" in message
    assert "Repeated greeting word" in message
    assert "Hi John, nice to meet you!" in message

