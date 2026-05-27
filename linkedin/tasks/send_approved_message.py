# linkedin/tasks/send_approved_message.py
"""Send approved message task — sends the approved message via Playwright and schedules follow-up."""
from __future__ import annotations

import logging
from termcolor import colored

from linkedin.models import ActionLog

logger = logging.getLogger(__name__)


def handle_send_approved_message(task, session, qualifiers):
    from crm.models import Deal
    from linkedin.actions.message import send_raw_message
    from linkedin.db.deals import set_profile_state
    from linkedin.enums import ProfileState
    from linkedin.models import PendingMessage
    from linkedin.tasks.follow_up import build_send_profile
    from linkedin.tasks.scheduler import enqueue_follow_up

    payload = task.payload
    pending_message_id = payload["pending_message_id"]

    try:
        pending = PendingMessage.objects.select_related("deal__campaign", "deal__lead").get(pk=pending_message_id)
    except PendingMessage.DoesNotExist:
        logger.warning("send_approved_message: PendingMessage %s does not exist", pending_message_id)
        return

    deal = pending.deal
    campaign = deal.campaign
    public_id = deal.lead.public_identifier

    logger.info(
        "[%s] %s approved message for %s",
        campaign, colored("\u25b6 send_approved", "green", attrs=["bold"]), public_id,
    )

    profile = build_send_profile(deal)
    message_text = pending.message_text

    # Send message via Playwright
    sent = send_raw_message(session, profile, message_text)
    if not sent:
        # If sending fails, move back to QUALIFIED so it can be re-connected
        set_profile_state(session, public_id, ProfileState.QUALIFIED.value, reason="approved_send_failed")
        logger.warning("send_approved_message for %s: send failed — moving to QUALIFIED", public_id)
        # Delete pending message
        pending.delete()
        return

    # Record action log
    session.linkedin_profile.record_action(
        ActionLog.ActionType.FOLLOW_UP, campaign,
    )

    decision_json = pending.decision_json or {}
    
    # Check if we should escalate
    intent = decision_json.get("intent", "low")
    situation = decision_json.get("situation", "cold")
    should_escalate = (intent == "high" or situation == "needs_human")

    if should_escalate:
        reason = f"intent={intent}, situation={situation}"
        set_profile_state(session, public_id, ProfileState.ESCALATED.value, reason=reason)
        
        # Send escalation Telegram alert (just like in handle_follow_up)
        from chat.models import ChatMessage
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(type(deal.lead))
        last_msg = ChatMessage.objects.filter(
            content_type=ct, object_id=deal.lead_id, is_outgoing=False
        ).order_by("-creation_date").first()
        last_message_text = last_msg.content if last_msg else "(no reply yet)"

        from linkedin.notifications import safe_notify
        safe_notify(
            "escalation",
            public_id=public_id,
            intent=intent,
            situation=situation,
            last_message=last_message_text,
            linkedin_url=deal.lead.linkedin_url,
            campaign=deal.campaign,
        )
    else:
        # Move back to CONNECTED and schedule next follow-up
        set_profile_state(session, public_id, ProfileState.CONNECTED.value, reason="approved_message_sent", enqueue_task=False)
        follow_up_hours = decision_json.get("follow_up_hours", 24.0)
        enqueue_follow_up(campaign.id, public_id, delay_seconds=follow_up_hours * 3600)

    # Delete the pending message record
    pending.delete()
