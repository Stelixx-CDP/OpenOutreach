import re
import logging
from typing import Optional, Tuple, Any

logger = logging.getLogger(__name__)

_GREETING_RE = re.compile(r"^\s*(hey|hi|hello|greetings)\b", re.IGNORECASE)
_NAME_AFTER_GREETING_RE = re.compile(
    r"^\s*(?:hey|hi|hello)\s+([A-Za-zÀ-ÖØ-öø-ÿ'\-]+)", re.IGNORECASE
)
_FORBIDDEN_WORDS = {
    "revolutionize", "leverage", "synergy", "holistic", "robust",
    "seamless", "best-in-class", "cutting-edge", "game-changer", "ai-powered",
}

def validate_message(
    message: str,
    conversation_mode: str,
    lead_first_name_safe: Optional[str],
    seller_name: str,
) -> Tuple[bool, Optional[str]]:
    """Return (ok, reason). `reason` is a short hint fed back to the LLM on retry."""

    # Rule 1: NO_REPLY_BUMP must not start with greeting
    if conversation_mode == "NO_REPLY_BUMP" and _GREETING_RE.match(message):
        return False, (
            "Your previous attempt started with a greeting (Hey/Hi/Hello). "
            "Mode is NO_REPLY_BUMP - rewrite without any greeting, <= 20 words, "
            "no new heavy question."
        )

    # Rule 2: LEAD_REPLIED should also not start with a greeting - jump into acknowledgement
    if conversation_mode == "LEAD_REPLIED" and _GREETING_RE.match(message):
        return False, (
            "Your previous attempt started with a greeting. The thread is live - "
            "jump straight into acknowledging the lead's last point."
        )

    # Rule 3: if a name appears after greeting, it must be safe AND correct
    m = _NAME_AFTER_GREETING_RE.match(message)
    if m:
        used = m.group(1).strip()
        seller_first = seller_name.strip().split()[0]
        if used.lower() == seller_first.lower():
            return False, (
                f"You addressed the lead as '{used}', which is your OWN name. "
                "Never call the lead by your own name."
            )
        if not lead_first_name_safe:
            return False, (
                f"You used '{used}' after the greeting, but we do not have a verified first name. "
                "Use 'Hey,' or 'Hi there,' without any name."
            )
        if used.lower() != lead_first_name_safe.lower():
            return False, (
                f"You used '{used}' but the lead's verified first name is "
                f"'{lead_first_name_safe}'. Use that exact name or no name."
            )

    # Rule 4: forbidden words
    lower = message.lower()
    hit = next((w for w in _FORBIDDEN_WORDS if w in lower), None)
    if hit:
        return False, f"Your message contains the forbidden word '{hit}'. Rewrite without it."

    # Rule 5: em-dash
    if "—" in message:
        return False, "Your message contains an em-dash. Use commas or short hyphens (-) instead."

    # Rule 6: NO_REPLY_BUMP length cap (<= 20 words)
    if conversation_mode == "NO_REPLY_BUMP" and len(message.split()) > 20:
        return False, (
            f"Your message is {len(message.split())} words. NO_REPLY_BUMP must be <= 20 words."
        )

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
    """Generate a message, validate, and retry once with hard feedback on failure."""
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
            
        if attempt < max_retries:
            logger.info("Validation failed on attempt %s, retrying with feedback: %s", attempt, reason)
            prompt = (
                f"{system_prompt}\n\n"
                f"# Validation feedback (your previous message was REJECTED):\n"
                f"Error: {reason}\n"
                f"Please correct the 'message' field in your output to comply with all rules."
            )
            
    logger.warning("Validation failed after retry for %s: %s", deal.lead.public_identifier, last_decision.message)
    return last_decision
