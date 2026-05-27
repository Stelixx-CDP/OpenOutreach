# linkedin/notifications.py
"""Telegram notification hub for OpenOutreach.

All system events (lead replies, deal state changes, errors) route through
``notify()`` which formats and sends via Telegram Bot API.
Gracefully no-ops when TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set.
"""
from __future__ import annotations

import html
import logging
import os

import requests

logger = logging.getLogger(__name__)

# Telegram caps message text at 4096 chars and captions at 1024 chars.
_MAX_TEXT = 4096
_MAX_CAPTION = 1024


def _get_token() -> str | None:
    return os.environ.get("TELEGRAM_BOT_TOKEN")


def _get_chat_id() -> str | None:
    return os.environ.get("TELEGRAM_CHAT_ID")


def _truncate(text: str, limit: int) -> str:
    """Truncate *text* to *limit* chars, appending an ellipsis marker."""
    if len(text) <= limit:
        return text
    return text[: limit - 30] + "\n\n<i>…(truncated)</i>"


def send_text(html_content: str, reply_markup: dict | None = None) -> int | None:
    """Send HTML-formatted text message to Telegram. Returns message_id if successful, else None."""
    token, chat_id = _get_token(), _get_chat_id()
    if not token or not chat_id:
        logger.debug("Telegram credentials not configured — skipping notification")
        return None

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": _truncate(html_content, _MAX_TEXT),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        res_json = response.json()
        if res_json.get("ok"):
            return res_json.get("result", {}).get("message_id")
        return None
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e)
        return None


def send_photo(photo_bytes: bytes, caption: str) -> bool:
    """Send photo with caption to Telegram."""
    token, chat_id = _get_token(), _get_chat_id()
    if not token or not chat_id:
        logger.debug("Telegram credentials not configured — skipping photo notification")
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    files = {"photo": ("screenshot.png", photo_bytes, "image/png")}
    data = {
        "chat_id": chat_id,
        "caption": _truncate(caption, _MAX_CAPTION),
        "parse_mode": "HTML",
    }
    try:
        response = requests.post(url, files=files, data=data, timeout=15)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error("Failed to send Telegram photo: %s", e)
        return False


# ── Central dispatcher ───────────────────────────────────────────────


def notify(event_type: str, **kwargs) -> None:
    """Central dispatcher for system notifications.

    Safe to call anywhere — silently no-ops when Telegram is not configured
    and never raises.
    """
    token, chat_id = _get_token(), _get_chat_id()
    if not token or not chat_id:
        return

    campaign = kwargs.get("campaign")
    if not campaign and "profile" in kwargs:
        profile = kwargs["profile"]
        if hasattr(profile, "user") and profile.user:
            campaign = profile.user.campaigns.first()
    campaign_name = campaign.name if campaign else "General"

    if event_type == "lead_reply":
        public_id = kwargs.get("public_identifier", "unknown")
        text = kwargs.get("text", "")
        escaped_text = html.escape(text)

        msg = (
            f"📩 <b>[{campaign_name}] Lead phản hồi mới!</b>\n"
            f"• <b>Lead:</b> <code>{public_id}</code>\n"
            f'• <b>Nội dung:</b> <i>"{escaped_text}"</i>'
        )
        send_text(msg)

    elif event_type == "deal_state_changed":
        lead = kwargs.get("lead", "unknown")
        old_state = kwargs.get("old_state", "")
        new_state = kwargs.get("new_state", "")
        reason = kwargs.get("reason", "")

        if old_state == new_state:
            return

        reason_suffix = f"\n• <b>Lý do:</b> <i>{html.escape(reason)}</i>" if reason else ""
        msg = (
            f"🔄 <b>[{campaign_name}] Trạng thái Deal cập nhật</b>\n"
            f"• <b>Lead:</b> <code>{lead}</code>\n"
            f"• <b>Cập nhật:</b> <code>{old_state}</code> ➡️ <b>{new_state}</b>"
            f"{reason_suffix}"
        )
        send_text(msg)

    elif event_type == "browser_crash":
        task_type = kwargs.get("task_type", "unknown")
        error = kwargs.get("error", "")
        screenshot = kwargs.get("screenshot")

        caption = (
            f"🔴 <b>[{campaign_name}] Cảnh báo: Trình duyệt bị Crash!</b>\n"
            f"• <b>Tác vụ:</b> <code>{task_type}</code>\n"
            f"• <b>Lỗi:</b> <code>{html.escape(str(error))}</code>"
        )
        if screenshot:
            send_photo(screenshot, caption)
        else:
            send_text(caption)

    elif event_type == "llm_error":
        error = kwargs.get("error", "")
        msg = (
            f"⚠️ <b>Cảnh báo: LLM API gặp lỗi!</b>\n"
            f"• <b>Lỗi:</b> <code>{html.escape(str(error))}</code>\n"
            f"• <b>Hành động:</b> Daemon tạm dừng hoạt động."
        )
        send_text(msg)

    elif event_type == "cookie_expired":
        profile = kwargs.get("profile", "unknown")
        msg = (
            f"🔑 <b>Yêu cầu đăng nhập: Phiên làm việc hết hạn!</b>\n"
            f"• <b>Tài khoản:</b> <code>{profile}</code>\n"
            f"• <b>Hành động:</b> Cần manual đăng nhập và xác thực 2FA qua VNC."
        )
        send_text(msg)

    elif event_type == "escalation":
        public_id = kwargs.get("public_id", "unknown")
        intent = kwargs.get("intent", "unknown")
        situation = kwargs.get("situation", "unknown")
        last_message = kwargs.get("last_message", "")
        linkedin_url = kwargs.get("linkedin_url", f"https://www.linkedin.com/in/{public_id}/")

        msg = (
            f"🔥 <b>[{campaign_name}] YÊU CẦU XỬ LÝ THỦ CÔNG (ESCALATION)</b>\n"
            f"• <b>Lead:</b> <code>{public_id}</code>\n"
            f"• <b>Intent:</b> <code>{intent}</code> | <b>Situation:</b> <code>{situation}</code>\n"
            f"• <b>Tin nhắn cuối từ lead:</b> <i>\"{html.escape(last_message)}\"</i>"
        )
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "📱 Open Chat", "url": linkedin_url}
                ]
            ]
        }
        send_text(msg, reply_markup=reply_markup)

    elif event_type == "pending_approval":
        pending_message = kwargs.get("pending_message")
        if pending_message:
            deal = pending_message.deal
            public_id = deal.lead.public_identifier
            msg_text = pending_message.message_text
            escaped_text = html.escape(msg_text)
            
            msg = (
                f"⏳ <b>[{campaign_name}] CHỜ DUYỆT TIN NHẮN (APPROVAL GATE)</b>\n"
                f"• <b>Lead:</b> <code>{public_id}</code>\n"
                f"• <b>Tin nhắn dự kiến gửi:</b>\n"
                f"<i>\"{escaped_text}\"</i>"
            )
            
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Duyệt & Gửi", "callback_data": f"approve:{pending_message.id}"},
                        {"text": "🚫 Bỏ qua", "callback_data": f"skip:{pending_message.id}"}
                    ],
                    [
                        {"text": "✏️ Sửa tin", "callback_data": f"edit_req:{pending_message.id}"}
                    ]
                ]
            }
            
            message_id = send_text(msg, reply_markup=reply_markup)
            if message_id:
                pending_message.telegram_message_id = message_id
                pending_message.save(update_fields=["telegram_message_id"])

    elif event_type == "auto_throttle":
        rate = kwargs.get("rate", 0.0)
        new_limit = kwargs.get("new_limit", 0)
        severity = kwargs.get("severity", "info")
        profile = kwargs.get("profile")

        profile_label = "General"
        if profile:
            if hasattr(profile, "user") and profile.user:
                profile_label = profile.user.username
            else:
                profile_label = profile.linkedin_username

        rate_percentage = int(rate * 100)

        if severity == "warning":
            msg = (
                f"🔴 <b>[{profile_label}] Auto-throttle activated!</b>\n"
                f"• <b>Acceptance rate 7d:</b> <code>{rate_percentage}%</code> (low)\n"
                f"• <b>Connect limit:</b> reduced to <code>{new_limit}</code>"
            )
        else:
            msg = (
                f"🟢 <b>[{profile_label}] Connect limit restored</b>\n"
                f"• <b>Acceptance rate 7d:</b> <code>{rate_percentage}%</code>\n"
                f"• <b>Connect limit:</b> restored to <code>{new_limit}</code>"
            )
        send_text(msg)

    elif event_type == "validation_failed":
        lead = kwargs.get("lead", "unknown")
        rejected_message = kwargs.get("rejected_message", "")
        reason = kwargs.get("reason", "")

        msg = (
            f"⚠️ <b>[{campaign_name}] Tin nhắn không qua kiểm duyệt AI!</b>\n"
            f"• <b>Lead:</b> <code>{lead}</code>\n"
            f"• <b>Lý do lỗi:</b> <i>{html.escape(reason)}</i>\n"
            f"• <b>Tin nhắn bị từ chối:</b>\n"
            f"<i>\"{html.escape(rejected_message)}\"</i>\n"
            f"• <b>Hành động:</b> Chuyển sang chế độ Chờ (24h)."
        )
        send_text(msg)


def safe_notify(event_type: str, **kwargs) -> None:
    """Wrapper that swallows exceptions — safe for use in daemon hot paths."""
    try:
        notify(event_type, **kwargs)
    except Exception:
        logger.debug("Notification failed for %s", event_type, exc_info=True)
