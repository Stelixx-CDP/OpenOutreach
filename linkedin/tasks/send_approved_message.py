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

    # Check 1: WAITING_APPROVAL validation
    if deal.state != ProfileState.WAITING_APPROVAL.value:
        logger.warning(
            "send_approved_message: Deal %s is not in WAITING_APPROVAL state (current: %s) — skipping send",
            public_id, deal.state
        )
        pending.delete()
        return

    # P1 Approved Flow: sync latest chat first before sending
    from linkedin.db.chat import sync_conversation
    sync_conversation(session, public_id)

    # Check if there is any new inbound message from lead since the PendingMessage was created
    from chat.models import ChatMessage
    from django.contrib.contenttypes.models import ContentType
    ct_lead = ContentType.objects.get_for_model(type(deal.lead))
    has_new_inbound = ChatMessage.objects.filter(
        content_type=ct_lead,
        object_id=deal.lead_id,
        is_outgoing=False,
        creation_date__gt=pending.created_at
    ).exists()

    if has_new_inbound:
        logger.info(
            "send_approved_message: Lead %s sent a new inbound message since PendingMessage %s was created — aborting approved send",
            public_id, pending_message_id
        )
        # Abort approved message: delete pending record, reset state to CONNECTED, and schedule immediate follow-up to regenerate
        pending.delete()
        set_profile_state(session, public_id, ProfileState.CONNECTED.value, reason="new_inbound_after_approval", enqueue_task=False)
        enqueue_follow_up(deal.campaign_id, public_id, delay_seconds=10)
        return

    # Check 2: Rate limit check (outbound approved follow-up)
    if not session.linkedin_profile.can_execute(ActionLog.ActionType.FOLLOW_UP):
        from linkedin.tasks.scheduler import enqueue_send_approved_message, seconds_until_tomorrow

        # Do NOT modify current task in-place because daemon always overrides status to COMPLETED upon handler return.
        # Instead, create a new Task for tomorrow to keep PendingMessage intact via scheduler helper (single source of truth).
        enqueue_send_approved_message(
            campaign_id=deal.campaign_id,
            pending_message_id=pending_message_id,
            delay_seconds=seconds_until_tomorrow(),
        )
        logger.warning("send_approved_message: Profile rate limited for FOLLOW_UP — queued a new task for tomorrow")
        return

    logger.info(
        "[%s] %s approved message for %s",
        campaign, colored("\u25b6 send_approved", "green", attrs=["bold"]), public_id,
    )

    profile = build_send_profile(deal)
    message_text = pending.message_text

    # Send message via Playwright
    sent = send_raw_message(session, profile, message_text)
    if not sent:
        # Stay at CONNECTED (not QUALIFIED — QUALIFIED would re-trigger connect invitation).
        # Re-enqueue follow-up in 1h; reconcile picks it up if this also fails.
        set_profile_state(session, public_id, ProfileState.CONNECTED.value, reason="approved_send_failed", enqueue_task=False)
        enqueue_follow_up(campaign.id, public_id, delay_seconds=3600)
        logger.warning("send_approved_message for %s: send failed — re-enqueuing in 1h", public_id)
        # Delete pending message
        pending.delete()
        return

    # Record action log
    session.linkedin_profile.record_action(
        ActionLog.ActionType.FOLLOW_UP, campaign,
    )

    decision_json = pending.decision_json or {}

    # Note: Escalation check already runs BEFORE the approval gate in
    # handle_follow_up.  If a message reaches send_approved_message, the
    # deal was not escalated — so we always move to CONNECTED here.
    set_profile_state(session, public_id, ProfileState.CONNECTED.value, reason="approved_message_sent", enqueue_task=False)
    follow_up_hours = decision_json.get("follow_up_hours", 24.0)
    enqueue_follow_up(campaign.id, public_id, delay_seconds=follow_up_hours * 3600)

    # Delete the pending message record
    pending.delete()
