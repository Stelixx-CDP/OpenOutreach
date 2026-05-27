# linkedin/tasks/follow_up.py
"""Follow-up task — runs the agentic follow-up for one CONNECTED profile."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone
from termcolor import colored

from linkedin.models import ActionLog

logger = logging.getLogger(__name__)

# Required silence between nudges scales with unanswered count:
# 1 unanswered → 3d, 2 → 6d, 3 → 9d. Skips the LLM call while open.
MIN_DAYS_PER_UNANSWERED = 3


def build_send_profile(deal) -> dict:
    """Minimal profile dict for ``send_raw_message`` and its fallbacks.

    Populated from the Lead row — all three send strategies (popup,
    direct-thread, API) now navigate by URN so no human-readable name
    is required.
    """
    lead = deal.lead
    return {
        "public_identifier": lead.public_identifier,
        "urn": lead.urn or "",
    }


def _too_soon_to_nudge(deal) -> bool:
    """Wait `unanswered_count * MIN_DAYS_PER_UNANSWERED` days between nudges."""
    from chat.models import ChatMessage
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(type(deal.lead))
    messages = ChatMessage.objects.filter(content_type=ct, object_id=deal.lead_id)

    last = messages.order_by("-creation_date").first()
    if last is None or not last.is_outgoing:
        return False

    last_reply = messages.filter(is_outgoing=False).order_by("-creation_date").first()
    nudges = messages.filter(is_outgoing=True)
    if last_reply:
        nudges = nudges.filter(creation_date__gt=last_reply.creation_date)

    required = timedelta(days=nudges.count() * MIN_DAYS_PER_UNANSWERED)
    return timezone.now() - last.creation_date < required


def should_require_approval(deal, decision) -> bool:
    """Determine if the calculated decision requires human approval."""
    if decision.action != "send_message":
        return False

    mode = deal.campaign.approval_mode
    if mode == "auto":
        return False
    if mode == "all":
        return True
    if mode == "first_touch":
        from chat.models import ChatMessage
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(type(deal.lead))
        has_outgoing = ChatMessage.objects.filter(
            content_type=ct,
            object_id=deal.lead_id,
            is_outgoing=True
        ).exists()
        return not has_outgoing
    if mode == "high_intent":
        return decision.intent in ["high", "medium"] or decision.situation == "needs_human"
    return False


def handle_follow_up(task, session, qualifiers):
    from crm.models import Deal
    from linkedin.actions.message import send_raw_message
    from linkedin.agents.follow_up import run_follow_up_agent
    from linkedin.db.deals import set_profile_state
    from linkedin.db.summaries import materialize_profile_summary_if_missing
    from linkedin.enums import ProfileState
    from linkedin.tasks.scheduler import enqueue_follow_up


    payload = task.payload
    public_id = payload["public_id"]
    campaign_id = payload["campaign_id"]

    logger.info(
        "[%s] %s %s",
        session.campaign, colored("\u25b6 follow_up", "green", attrs=["bold"]), public_id,
    )

    # Rate limit check
    if not session.linkedin_profile.can_execute(ActionLog.ActionType.FOLLOW_UP):
        enqueue_follow_up(campaign_id, public_id, delay_seconds=3600)
        return

    deal = (
        Deal.objects.filter(lead__public_identifier=public_id, campaign=session.campaign)
        .select_related("lead", "campaign")
        .first()
    )
    if deal is None:
        logger.warning("follow_up: no Deal for %s — skipping", public_id)
        return

    # CRIT-1: Guard against running follow_up on non-CONNECTED deals
    if deal.state != ProfileState.CONNECTED.value:
        logger.info("follow_up: deal %s in state %s, not CONNECTED — skipping", public_id, deal.state)
        return

    if _too_soon_to_nudge(deal):
        logger.info("[%s] follow_up %s: too soon to nudge — re-enqueuing", session.campaign, public_id)
        enqueue_follow_up(campaign_id, public_id, delay_seconds=24 * 3600)
        return

    materialize_profile_summary_if_missing(deal, session)
    decision = run_follow_up_agent(session, deal)

    if should_require_approval(deal, decision):
        from linkedin.models import PendingMessage
        pending = PendingMessage.objects.create(
            deal=deal,
            message_text=decision.message,
            decision_json={
                "action": decision.action,
                "message": decision.message,
                "outcome": decision.outcome,
                "follow_up_hours": decision.follow_up_hours,
                "intent": decision.intent,
                "situation": decision.situation,
            }
        )
        set_profile_state(session, public_id, ProfileState.WAITING_APPROVAL.value, reason="waiting_approval")
        
        from linkedin.notifications import safe_notify
        safe_notify(
            "pending_approval",
            pending_message=pending,
            campaign=deal.campaign,
        )
        return

    profile = build_send_profile(deal)

    # Only escalate if action is NOT mark_completed
    should_escalate = (
        decision.intent == "high" or decision.situation == "needs_human"
    ) and decision.action != "mark_completed"

    if should_escalate:
        reason = f"intent={decision.intent}, situation={decision.situation}"
        set_profile_state(session, public_id, ProfileState.ESCALATED.value, reason=reason)

        # Fetch last incoming message text for Telegram notification
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
            intent=decision.intent,
            situation=decision.situation,
            last_message=last_message_text,
            linkedin_url=deal.lead.linkedin_url,
            campaign=deal.campaign,
        )

        if decision.action == "send_message":
            logger.info("[%s] follow_up bridge message for escalated %s: %s", session.campaign, public_id, decision.message)
            sent = send_raw_message(session, profile, decision.message)
            if sent:
                session.linkedin_profile.record_action(
                    ActionLog.ActionType.FOLLOW_UP, session.campaign,
                )
        return

    if decision.action == "send_message":
        logger.info("[%s] follow_up message for %s: %s", session.campaign, public_id, decision.message)
        sent = send_raw_message(session, profile, decision.message)
        if not sent:
            set_profile_state(session, public_id, ProfileState.QUALIFIED.value)
            logger.warning("follow_up for %s: send failed — moving to QUALIFIED for re-connection", public_id)
            return
        session.linkedin_profile.record_action(
            ActionLog.ActionType.FOLLOW_UP, session.campaign,
        )
        enqueue_follow_up(campaign_id, public_id, delay_seconds=decision.follow_up_hours * 3600)

    elif decision.action == "mark_completed":
        set_profile_state(session, public_id, ProfileState.COMPLETED.value, outcome=decision.outcome)
        logger.info("[%s] follow_up completed for %s: outcome=%s", session.campaign, public_id, decision.outcome)

    elif decision.action == "wait":
        enqueue_follow_up(campaign_id, public_id, delay_seconds=decision.follow_up_hours * 3600)

