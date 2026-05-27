import re
import logging
from typing import Optional, Tuple, Any, List

logger = logging.getLogger(__name__)

_GREETING_RE = re.compile(r"^\s*(hey|hi|hello|greetings)\b", re.IGNORECASE)
_NAME_AFTER_GREETING_RE = re.compile(
    r"^\s*(?:hey|hi|hello)\s+([A-Za-zÀ-ÖØ-öø-ÿ'\-]+)", re.IGNORECASE
)
_FORBIDDEN_WORDS = {
    "revolutionize", "leverage", "synergy", "holistic", "robust",
    "seamless", "best-in-class", "cutting-edge", "game-changer", "ai-powered",
}
# Pre-compile a single regex for all forbidden words (word boundary at start).
# Using \b only at the start of the word prevents substring false positives
# (e.g. "seam" won't match "seamless"), while still catching inflected forms
# like "leveraging" or "revolutionized".
_FORBIDDEN_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _FORBIDDEN_WORDS) + r")",
    re.IGNORECASE,
)

def validate_message(
    message: str,
    conversation_mode: str,
    lead_first_name_safe: Optional[str],
    seller_name: str,
) -> Tuple[bool, Optional[str]]:
    """Return (ok, reason). `reason` is a short hint fed back to the LLM on retry.

    Collects ALL violations in a single pass so the LLM can fix everything
    in one retry instead of playing whack-a-mole.
    """
    errors: List[str] = []

    # Rule 1: NO_REPLY_BUMP must not start with greeting
    if conversation_mode == "NO_REPLY_BUMP" and _GREETING_RE.match(message):
        errors.append(
            "Your previous attempt started with a greeting (Hey/Hi/Hello). "
            "Mode is NO_REPLY_BUMP - rewrite without any greeting, <= 20 words, "
            "no new heavy question."
        )

    # Rule 2: LEAD_REPLIED should also not start with a greeting - jump into acknowledgement
    if conversation_mode == "LEAD_REPLIED" and _GREETING_RE.match(message):
        errors.append(
            "Your previous attempt started with a greeting. The thread is live - "
            "jump straight into acknowledging the lead's last point."
        )

    # Rule 3: if a name appears after greeting, it must be safe AND correct
    m = _NAME_AFTER_GREETING_RE.match(message)
    if m:
        used = m.group(1).strip()
        seller_first = seller_name.strip().split()[0]
        if used.lower() == seller_first.lower():
            errors.append(
                f"You addressed the lead as '{used}', which is your OWN name. "
                "Never call the lead by your own name."
            )
        elif not lead_first_name_safe:
            errors.append(
                f"You used '{used}' after the greeting, but we do not have a verified first name. "
                "Use 'Hey,' or 'Hi there,' without any name."
            )
        elif used.lower() != lead_first_name_safe.lower():
            errors.append(
                f"You used '{used}' but the lead's verified first name is "
                f"'{lead_first_name_safe}'. Use that exact name or no name."
            )

    # Rule 4: forbidden words (word-boundary match to prevent substring false positives)
    hits = _FORBIDDEN_RE.findall(message)
    if hits:
        unique_hits = sorted(set(h.lower() for h in hits))
        errors.append(
            f"Your message contains forbidden word(s): {', '.join(repr(h) for h in unique_hits)}. "
            "Rewrite without them."
        )

    # Rule 5: em-dash and en-dash
    has_em = "\u2014" in message  # em-dash
    has_en = "\u2013" in message  # en-dash
    if has_em or has_en:
        dash_types = []
        if has_em:
            dash_types.append("em-dash (\u2014)")
        if has_en:
            dash_types.append("en-dash (\u2013)")
        errors.append(
            f"Your message contains {' and '.join(dash_types)}. "
            "Use commas or short hyphens (-) instead."
        )

    # Rule 6: NO_REPLY_BUMP length cap (<= 20 words)
    if conversation_mode == "NO_REPLY_BUMP" and len(message.split()) > 20:
        errors.append(
            f"Your message is {len(message.split())} words. NO_REPLY_BUMP must be <= 20 words."
        )

    if errors:
        return False, " | ".join(errors)
    return True, None


def generate_with_retry(
    session,
    deal,
    system_prompt: str,
    conversation_mode: str,
    lead_first_name_safe: Optional[str],
    seller_name: str,
    max_retries: int = 1,
) -> Any:
    """Generate a message, validate, and retry once with hard feedback on failure.

    If validation still fails after all retries, converts the decision to a
    safe ``wait`` action (24h) and sends a Telegram notification instead of
    returning a dirty message to the lead.
    """
    from pydantic_ai import Agent
    from linkedin.llm import get_llm_model, run_agent_sync
    from linkedin.agents.follow_up import FollowUpDecision
    
    agent = Agent(
        get_llm_model(),
        output_type=FollowUpDecision,
        model_settings={"temperature": 0.7, "timeout": 60},
    )
    
    prompt = system_prompt
    last_decision = None
    last_reason = None
    
    for attempt in range(max_retries + 1):
        result = run_agent_sync(agent.run(prompt))
        last_decision = result.output
        if not last_decision:
            raise RuntimeError("LLM returned unparseable response for follow-up")
            
        if last_decision.action != "send_message":
            return last_decision
            
        ok, reason = validate_message(
            last_decision.message or "", conversation_mode, lead_first_name_safe, seller_name
        )
        if ok:
            return last_decision
        
        last_reason = reason
            
        if attempt < max_retries:
            logger.info("Validation failed on attempt %s, retrying with feedback: %s", attempt, reason)
            prompt = (
                f"{system_prompt}\n\n"
                f"# Validation feedback (your previous message was REJECTED):\n"
                f"Error: {reason}\n"
                f"Please correct the 'message' field in your output to comply with all rules."
            )
    
    # All retries exhausted - DO NOT return the dirty message.
    # Convert to a safe "wait" action and notify via Telegram.
    public_id = deal.lead.public_identifier
    logger.warning(
        "Validation failed after %d retries for %s. Converting to wait. Reason: %s",
        max_retries, public_id, last_reason,
    )
    
    _notify_validation_failure(deal, last_decision, last_reason)
    
    return FollowUpDecision(
        action="wait",
        message=None,
        outcome=None,
        follow_up_hours=24,
    )


def _notify_validation_failure(deal, decision, reason: str) -> None:
    """Send a Telegram alert when validation fails after all retries."""
    try:
        from linkedin.notifications import safe_notify
        safe_notify(
            "validation_failed",
            lead=deal.lead.public_identifier,
            rejected_message=decision.message[:200] if decision.message else "(empty)",
            reason=reason[:300],
        )
    except Exception:
        logger.exception("Failed to send validation failure notification")
