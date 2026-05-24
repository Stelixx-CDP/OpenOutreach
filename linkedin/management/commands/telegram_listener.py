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

    logger.info("Telegram Bot Listener started. Listening for commands...")

    offset = 0
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    iteration = 0

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

                message = update.get("message", {})
                chat = message.get("chat", {})
                incoming_chat_id = str(chat.get("id"))
                text = (message.get("text") or "").strip()

                # Only process commands from the configured TELEGRAM_CHAT_ID
                if incoming_chat_id == str(chat_id):
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
