# linkedin/management/commands/telegram_listener.py
"""Telegram Bot long-polling listener.

Listens for commands from the configured TELEGRAM_CHAT_ID and executes them.
Currently supports: /report, /daily-report, /daily_report.

Can run standalone (``python manage.py telegram_listener``) or as a background
thread inside the daemon (see ``start_listener_thread``).
"""
from __future__ import annotations

import logging
import os
import threading
import time

import requests
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def listen_to_telegram(*, max_iterations: int | None = None) -> None:
    """Main loop for Telegram Bot Long Polling.

    Parameters
    ----------
    max_iterations:
        If set, exit after processing this many polling cycles.
        ``None`` (default) runs forever.  Used by tests.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.warning("Telegram Bot credentials not set — listener will not start.")
        return

    logger.info("Telegram Bot Listener started. Listening for updates...")

    offset = 0
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    iteration = 0

    def send_req(method: str, payload: dict):
        u = f"https://api.telegram.org/bot{token}/{method}"
        try:
            res = requests.post(u, json=payload, timeout=10)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error("Telegram API error %s: %s", method, e)
            return None

    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        try:
            params = {"timeout": 30, "offset": offset}
            response = requests.get(url, params=params, timeout=35)
            if response.status_code != 200:
                time.sleep(5)
                continue

            data = response.json()
            results = data.get("result", [])

            for update in results:
                update_id = update.get("update_id")
                offset = update_id + 1

                # 1. Handle Callback Query
                if "callback_query" in update:
                    cb = update["callback_query"]
                    cb_id = cb.get("id")
                    cb_data = cb.get("data") or ""
                    cb_message = cb.get("message", {})
                    cb_chat = cb_message.get("chat", {})
                    incoming_chat_id = str(cb_chat.get("id"))
                    cb_msg_id = cb_message.get("message_id")

                    if incoming_chat_id == str(chat_id):
                        # Acknowledge callback query
                        send_req("answerCallbackQuery", {"callback_query_id": cb_id})

                        if ":" in cb_data:
                            action, pending_id_str = cb_data.split(":", 1)
                            try:
                                pending_id = int(pending_id_str)
                            except ValueError:
                                continue

                            from linkedin.models import PendingMessage, AgentFeedback, Task
                            from linkedin.enums import ProfileState
                            from linkedin.tasks.scheduler import enqueue_follow_up
                            from django.utils import timezone
                            import html

                            pending = PendingMessage.objects.select_related("deal__campaign", "deal__lead").filter(pk=pending_id).first()
                            if not pending:
                                send_req("editMessageText", {
                                    "chat_id": chat_id,
                                    "message_id": cb_msg_id,
                                    "text": "⚠️ Tin nhắn không còn tồn tại hoặc đã được xử lý.",
                                })
                                continue

                            deal = pending.deal
                            lead_id = deal.lead.public_identifier

                            if action == "approve":
                                # Save Feedback
                                AgentFeedback.objects.create(
                                    campaign=deal.campaign,
                                    deal=deal,
                                    original_message=pending.message_text,
                                    feedback_type=AgentFeedback.FeedbackType.APPROVED,
                                )
                                # Queue send approved task
                                Task.objects.create(
                                    task_type=Task.TaskType.SEND_APPROVED_MESSAGE,
                                    scheduled_at=timezone.now(),
                                    payload={
                                        "campaign_id": deal.campaign_id,
                                        "pending_message_id": pending.id,
                                    }
                                )
                                # Update original message
                                new_text = (
                                    f"✅ <b>Đã duyệt và đang xếp lịch gửi:</b>\n"
                                    f"• Lead: <code>{lead_id}</code>\n"
                                    f"• Nội dung: <i>\"{html.escape(pending.message_text)}\"</i>"
                                )
                                send_req("editMessageText", {
                                    "chat_id": chat_id,
                                    "message_id": cb_msg_id,
                                    "text": new_text,
                                    "parse_mode": "HTML",
                                })

                            elif action == "skip":
                                # Save Feedback
                                AgentFeedback.objects.create(
                                    campaign=deal.campaign,
                                    deal=deal,
                                    original_message=pending.message_text,
                                    feedback_type=AgentFeedback.FeedbackType.REJECTED,
                                )
                                # Move deal back to CONNECTED using set_profile_state
                                from linkedin.db.deals import set_profile_state
                                class SimpleSession:
                                    def __init__(self, campaign):
                                        self.campaign = campaign

                                mock_session = SimpleSession(deal.campaign)
                                set_profile_state(mock_session, lead_id, ProfileState.CONNECTED.value, reason="skipped_by_user", enqueue_task=False)
                                from linkedin.tasks.scheduler import enqueue_follow_up
                                enqueue_follow_up(deal.campaign.id, lead_id, delay_seconds=24 * 3600)

                                # Delete pending
                                pending.delete()

                                new_text = (
                                    f"🚫 <b>Đã bỏ qua tin nhắn:</b>\n"
                                    f"• Lead: <code>{lead_id}</code>\n"
                                    f"• Nội dung bị bỏ qua: <i>\"{html.escape(pending.message_text)}\"</i>"
                                )
                                send_req("editMessageText", {
                                    "chat_id": chat_id,
                                    "message_id": cb_msg_id,
                                    "text": new_text,
                                    "parse_mode": "HTML",
                                })

                            elif action == "edit_req":
                                new_text = (
                                    f"✏️ <b>Vui lòng REPLY tin nhắn này để sửa đổi:</b>\n"
                                    f"• Lead: <code>{lead_id}</code>\n"
                                    f"• Bản gốc: <i>\"{html.escape(pending.message_text)}\"</i>"
                                )
                                send_req("editMessageText", {
                                    "chat_id": chat_id,
                                    "message_id": cb_msg_id,
                                    "text": new_text,
                                    "parse_mode": "HTML",
                                })

                # 2. Handle standard text Message or Reply
                elif "message" in update:
                    message = update["message"]
                    chat = message.get("chat", {})
                    incoming_chat_id = str(chat.get("id"))
                    text = (message.get("text") or "").strip()
                    msg_id = message.get("message_id")

                    if incoming_chat_id == str(chat_id):
                        reply_to = message.get("reply_to_message", {})
                        reply_msg_id = reply_to.get("message_id")

                        if reply_msg_id:
                            # This is a reply! Check if it's replying to a pending message
                            from linkedin.models import PendingMessage, AgentFeedback, Task
                            from django.utils import timezone
                            import html

                            pending = PendingMessage.objects.select_related("deal__campaign", "deal__lead").filter(telegram_message_id=reply_msg_id).first()
                            if pending:
                                deal = pending.deal
                                lead_id = deal.lead.public_identifier
                                original_text = pending.message_text

                                # Save AgentFeedback (edited)
                                AgentFeedback.objects.create(
                                    campaign=deal.campaign,
                                    deal=deal,
                                    original_message=original_text,
                                    corrected_message=text,
                                    feedback_type=AgentFeedback.FeedbackType.EDITED,
                                )

                                # Update PendingMessage text
                                pending.message_text = text
                                pending.save(update_fields=["message_text"])

                                # Queue send approved task
                                Task.objects.create(
                                    task_type=Task.TaskType.SEND_APPROVED_MESSAGE,
                                    scheduled_at=timezone.now(),
                                    payload={
                                        "campaign_id": deal.campaign_id,
                                        "pending_message_id": pending.id,
                                    }
                                )

                                # Update original pending message
                                new_orig_text = (
                                    f"✅ <b>Đã chỉnh sửa và đang xếp lịch gửi:</b>\n"
                                    f"• Lead: <code>{lead_id}</code>\n"
                                    f"• Bản sửa đổi: <i>\"{html.escape(text)}\"</i>\n"
                                    f"• Bản gốc: <s>\"{html.escape(original_text)}\"</s>"
                                )
                                send_req("editMessageText", {
                                    "chat_id": chat_id,
                                    "message_id": reply_msg_id,
                                    "text": new_orig_text,
                                    "parse_mode": "HTML",
                                })

                                # Send confirmation message to user
                                send_req("sendMessage", {
                                    "chat_id": chat_id,
                                    "text": "✅ Đã ghi nhận nội dung sửa đổi và xếp lịch gửi.",
                                    "reply_to_message_id": msg_id,
                                })
                                continue

                        # If not a reply, check for report commands
                        if text in ("/daily-report", "/daily_report", "/report"):
                            logger.info("Received %s command from Telegram. Sending report...", text)
                            try:
                                call_command("send_daily_report")
                            except Exception as cmd_exc:
                                logger.error("Failed to execute send_daily_report command: %s", cmd_exc)

        except requests.exceptions.RequestException:
            time.sleep(5)
        except Exception as e:
            logger.exception("Unexpected error in Telegram listener: %s", e)
            time.sleep(5)


def start_listener_thread() -> None:
    """Start the Telegram listener in a background daemon thread."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.warning("Telegram credentials missing. Background Telegram listener will not start.")
        return

    thread = threading.Thread(target=listen_to_telegram, name="TelegramListenerThread", daemon=True)
    thread.start()
    logger.info("Background Telegram listener thread started.")


class Command(BaseCommand):
    help = "Run the Telegram Bot command listener (Long Polling)"

    def handle(self, *args, **options):
        self.stdout.write("Starting Telegram Bot Command Listener...")
        try:
            listen_to_telegram()
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("Telegram Bot Command Listener stopped."))
