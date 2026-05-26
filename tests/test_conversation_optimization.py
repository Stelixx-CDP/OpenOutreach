import pytest
from typing import NamedTuple, Optional
from linkedin.agents.name_safety import extract_safe_first_name
from linkedin.agents.conversation_mode import compute_conversation_mode, ConversationMode
from linkedin.agents.output_validator import validate_message


# Mock class for ChatMessage
class MockMessage(NamedTuple):
    is_outgoing: bool


def test_extract_safe_first_name():
    assert extract_safe_first_name("Grant", "Simmons", "simmonet") == "Grant"
    assert extract_safe_first_name("", "", "simmonet") is None
    assert extract_safe_first_name(None, None, "kristanbauer") is None
    assert extract_safe_first_name("", "Kristan Bauer", "kristanbauer") == "Kristan"
    assert extract_safe_first_name("olga", "kunger", "olga-kunger-seo") == "Olga"
    assert extract_safe_first_name("", "", "john-seo") is None
    assert extract_safe_first_name("SEO", "", "seo-expert") is None
    assert extract_safe_first_name("Mary-Jane", "", "mj") == "Mary-Jane"


def test_compute_conversation_mode():
    # Empty messages -> INITIAL_OUTREACH
    assert compute_conversation_mode([]) == ConversationMode.INITIAL_OUTREACH

    # Last message outgoing -> NO_REPLY_BUMP
    msg1 = MockMessage(is_outgoing=False)
    msg2 = MockMessage(is_outgoing=True)
    assert compute_conversation_mode([msg1, msg2]) == ConversationMode.NO_REPLY_BUMP

    # Last message incoming -> LEAD_REPLIED
    msg3 = MockMessage(is_outgoing=True)
    msg4 = MockMessage(is_outgoing=False)
    assert compute_conversation_mode([msg3, msg4]) == ConversationMode.LEAD_REPLIED


def test_validate_message():
    # Rule 1 & 6: NO_REPLY_BUMP starting with greeting
    ok, reason = validate_message(
        "Hey, quick follow-up - when a client asks...",
        "NO_REPLY_BUMP",
        None,
        "Cong"
    )
    assert not ok
    assert "started with a greeting" in reason.lower()

    # Rule 1: NO_REPLY_BUMP valid
    ok, reason = validate_message(
        "Bumping this, no worries if not on your radar.",
        "NO_REPLY_BUMP",
        None,
        "Cong"
    )
    assert ok
    assert reason is None

    # Rule 3: addressing lead as seller's own name
    ok, reason = validate_message(
        "Hey Cong, impressed by your SEO journey...",
        "INITIAL_OUTREACH",
        "Olga",
        "Cong"
    )
    assert not ok
    assert "own name" in reason.lower()

    # Rule 3: using unverified name or wrong name
    ok, reason = validate_message(
        "Hey Simmonet, sorry for the buzz-word...",
        "NO_REPLY_BUMP",
        None,
        "Cong"
    )
    assert not ok
    assert "started with a greeting" in reason.lower()  # NO_REPLY_BUMP starts with greeting is caught first

    ok, reason = validate_message(
        "Hey Simmonet, sorry for the buzz-word...",
        "INITIAL_OUTREACH",
        None,
        "Cong"
    )
    assert not ok
    assert "do not have a verified first name" in reason.lower()

    # Rule 2: LEAD_REPLIED starts with greeting
    ok, reason = validate_message(
        "Hey Grant, stakeholder alignment is the silent killer.",
        "LEAD_REPLIED",
        "Grant",
        "Cong"
    )
    assert not ok
    assert "started with a greeting" in reason.lower()

    # LEAD_REPLIED valid (acknowledgement starts directly)
    ok, reason = validate_message(
        "Ha, stakeholder alignment is the silent killer. Do you walk them through it in a deck?",
        "LEAD_REPLIED",
        "Grant",
        "Cong"
    )
    assert ok
    assert reason is None

    # Rule 4: forbidden words
    ok, reason = validate_message(
        "This will revolutionize your workflow.",
        "LEAD_REPLIED",
        "Grant",
        "Cong"
    )
    assert not ok
    assert "forbidden word" in reason.lower()

    # Rule 5: em-dash
    ok, reason = validate_message(
        "We help with visibility—specifically AI search results.",
        "INITIAL_OUTREACH",
        "Grant",
        "Cong"
    )
    assert not ok
    assert "em-dash" in reason.lower()
