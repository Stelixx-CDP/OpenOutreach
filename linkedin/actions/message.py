# linkedin/actions/message.py
import logging
from typing import Dict, Any

from playwright.sync_api import Error as PlaywrightError, Locator
from linkedin.browser.nav import goto_page, human_type, dump_page_html

logger = logging.getLogger(__name__)

LINKEDIN_MESSAGING_URL = "https://www.linkedin.com/messaging/thread/new/"

# Selector fallback chains: semantic/ARIA first, then class-based.
# LinkedIn A/B tests UI variants per account and renames classes often.
# Each key maps to a list tried in order; first with a match wins.
SELECTOR_CHAINS = {
    # ── New thread: recipient search ──
    "connections_input": [
        'input[role="combobox"][placeholder*="name"]',
        'input[class*="msg-connections"]',
        'input[placeholder*="Type a name"]',
        'input[type="text"][aria-owns]',
    ],
    "search_result_row": [
        'ul[role="listbox"] li[role="option"]',
        'div[class*="msg-connections-typeahead__search-result-row"]',
        'li[class*="search-result"]',
    ],
    # ── Thread: compose area ──
    "compose_input": [
        'div[role="textbox"][aria-label*="Write a message"]',
        'div[role="textbox"][aria-label*="message"i]',
        'div[class*="msg-form__contenteditable"]',
        'div[contenteditable="true"]',
    ],
    "compose_send": [
        # Only match the actual Send submit button — NOT the "..." options
        # menu that sits next to "Press Enter to Send" text.
        'form.msg-form button[type="submit"]',
        '.msg-form button[type="submit"]',
        '.msg-form__footer button[type="submit"]',
        'button[type="submit"][class*="msg-form"]',
        '.msg-form__send-button',
        'button[class*="msg-form__send-button"]',
        # Avoid: button[aria-label*="Send"] and button:has-text("Send")
        # because the "..." options button near "Press Enter to Send"
        # matches both of those.
    ],
}


def _find(page, key: str, timeout: int = 5000) -> Locator:
    """Try each selector in the chain for *key*, return the first with matches.

    Raises PlaywrightError if none match within *timeout* ms.
    """
    chain = SELECTOR_CHAINS[key]
    for sel in chain:
        loc = page.locator(sel)
        try:
            loc.first.wait_for(state="attached", timeout=timeout)
            logger.debug("Selector hit for %s: %s", key, sel)
            return loc
        except (PlaywrightError, TimeoutError):
            continue
    tried = ", ".join(chain)
    raise PlaywrightError(f"No selector matched for '{key}'. Tried: {tried}")


def clean_message_punctuation(message: str) -> str:
    """Post-process message content to make it look more human.

    Replaces formal em-dashes (—) and en-dashes (–) with a friendly " - " spacing,
    preventing typical AI punctuation slop in chats.
    """
    if not message:
        return message
    # Replace em-dash (—) and en-dash (–)
    cleaned = message.replace("—", " - ").replace("–", " - ")
    # Replace multiple spaces with a single space if any were introduced
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    return cleaned.strip()


# ── Public entry point ────────────────────────────────────────────


def send_raw_message(session, profile: Dict[str, Any], message: str) -> bool:
    """Send an arbitrary message to a profile. Returns True if sent."""
    public_identifier = profile.get("public_identifier")

    # Apply punctuation cleaning to avoid AI-looking em-dashes
    message = clean_message_punctuation(message)

    if _send_message(session, profile, message):
        return True
    dump_page_html(session, profile, category="message_direct")

    if _send_message_via_api(session, profile, message):
        return True

    logger.error("All send methods failed for %s", public_identifier)
    return False


def _send_message(session, profile: Dict[str, Any], message: str) -> bool:
    """Navigate to /messaging/thread/new/?recipient=<urn>, compose, send.

    Uses the target URN (promoted to its own Lead column in crm.0005) to
    skip the search-by-name step entirely. Post-migration 0007 the Lead
    row no longer carries first_name/last_name, so name-based search is
    not available anyway.
    """
    from linkedin.api.messaging.utils import encode_urn

    public_identifier = profile.get("public_identifier")
    target_urn = profile.get("urn")
    if not target_urn:
        logger.error("Cannot send via direct thread: no URN for %s", public_identifier)
        return False
    try:
        thread_url = f"{LINKEDIN_MESSAGING_URL}?recipient={encode_urn(target_urn)}"
        goto_page(
            session,
            action=lambda: session.page.goto(thread_url),
            expected_url_pattern="/messaging",
            timeout=30_000,
            error_message="Error opening messaging thread",
        )
        session.wait(1, 2)

        input_el = _find(session.page, "compose_input").first

        # Click to focus the compose input — LinkedIn's React handlers
        # only attach after the element receives real focus via click.
        # Without this, type() sends keystrokes but LinkedIn's JS may
        # not process them properly, causing page reload.
        input_el.click()
        session.wait(0.3, 0.5)

        # Flatten newlines → spaces before typing.  LinkedIn's default
        # "Press Enter to Send" mode treats Enter as submit, so a literal
        # \n inside the message would send it mid-sentence.
        safe_message = message.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

        # Use default typing speed (50-200ms per key from conf.py).
        # The previous 10-50ms was 5-20x faster than human and triggers
        # LinkedIn's anti-automation detection (page reload).
        human_type(input_el, safe_message)
        session.wait(0.5, 1)

        # Check if the Send button is visible (Click Send mode)
        is_send_visible = False
        try:
            send_btn = _find(session.page, "compose_send", timeout=3000).first
            is_send_visible = send_btn.is_visible()
        except Exception:
            pass

        if is_send_visible:
            logger.info("Send button is visible. Clicking Send button for %s...", public_identifier)
            send_btn.click(delay=200)
        else:
            logger.info("Send button is not visible. Pressing Enter to send for %s...", public_identifier)
            input_el.press("Enter")

        # Verify message is sent by checking if the input is cleared
        # and we are still in messaging section.
        success = False
        for _ in range(10):  # Wait up to 5 seconds
            session.wait(0.5, 0.5)
            # URL check: if not in messaging, send failed or redirected
            if "/messaging" not in session.page.url:
                logger.warning("Left messaging page unexpectedly: %s", session.page.url)
                break
            try:
                text = input_el.inner_text() or ""
                if not text.strip():
                    success = True
                    break
            except Exception:
                # Element detached, indicating page state change
                success = True
                break

        # Fallback in case "Click Send" was active but Send button rendered late
        if not success:
            try:
                send_btn = _find(session.page, "compose_send", timeout=3000).first
                if send_btn.is_visible():
                    logger.info("Retrying Send button click for %s...", public_identifier)
                    send_btn.click(delay=200)
                    session.wait(1)
                    text = input_el.inner_text() or ""
                    if not text.strip():
                        success = True
            except Exception:
                pass

        if success:
            logger.info("Message sent to %s (direct thread)", public_identifier)
            return True
        else:
            logger.warning("Message input not cleared after send to %s (UI fail)", public_identifier)
            return False

    except (PlaywrightError, TimeoutError) as e:
        logger.error("Failed to send message to %s (direct thread) → %s", public_identifier, e)
        return False


def _send_message_via_api(session, profile: Dict[str, Any], message: str) -> bool:
    """Last-resort fallback: send via Voyager Messaging API.

    Requires profile dict to contain 'urn' (target profile URN).
    """
    from linkedin.api.client import PlaywrightLinkedinAPI
    from linkedin.api.messaging import send_message
    from linkedin.actions.conversations import find_conversation_urn, find_conversation_urn_via_navigation

    public_identifier = profile.get("public_identifier")
    target_urn = profile.get("urn")
    if not target_urn:
        logger.error("API send failed for %s → no URN in profile dict", public_identifier)
        return False

    mailbox_urn = session.self_profile["urn"]
    api = PlaywrightLinkedinAPI(session=session)

    conversation_urn = find_conversation_urn(api, target_urn, mailbox_urn)
    if not conversation_urn:
        conversation_urn = find_conversation_urn_via_navigation(session, target_urn)
    if not conversation_urn:
        logger.error("API send failed for %s → no conversation found", public_identifier)
        return False

    try:
        send_message(api, conversation_urn, message, mailbox_urn)
        logger.info("Message sent to %s (API fallback)", public_identifier)
        return True
    except Exception as e:
        logger.error("API send failed for %s → %s", public_identifier, e)
        return False


if __name__ == "__main__":
    from linkedin.browser.registry import cli_parser, cli_session

    parser = cli_parser("Debug LinkedIn messaging search results")
    parser.add_argument("--name", required=True, help="Full name to search for")
    args = parser.parse_args()
    session = cli_session(args)
    session.ensure_browser()

    logger.info("Searching for '%s' ...", args.name)

    goto_page(
        session,
        action=lambda: session.page.goto(LINKEDIN_MESSAGING_URL),
        expected_url_pattern="/messaging",
        timeout=30_000,
        error_message="Error opening messaging",
    )

    conn_input = _find(session.page, "connections_input").first
    conn_input.fill("")
    session.wait(0.5, 1)
    human_type(conn_input, args.name, min_delay=10, max_delay=50)
    session.wait(3, 4)

    rows = _find(session.page, "search_result_row")
    count = rows.count()
    logger.info("=== Found %d result rows ===", count)
    for i in range(min(count, 3)):
        row = rows.nth(i)
        logger.debug("--- Row %d inner_text ---", i)
        logger.debug(row.inner_text(timeout=5_000))
        logger.debug("--- Row %d outer_html ---", i)
        logger.debug(row.evaluate("el => el.outerHTML"))
