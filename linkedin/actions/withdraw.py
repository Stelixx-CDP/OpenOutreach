# linkedin/actions/withdraw.py
import logging
import random
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from linkedin.browser.session import AccountSession

logger = logging.getLogger(__name__)

SELECTORS = {
    "invitation_card": (
        ".invitation-card, "
        ".mn-invitation-card, "
        "li:has(button:has-text('Withdraw')), "
        "div[class*='invitation-card']:has(button:has-text('Withdraw'))"
    ),
    "withdraw_button": "button:has-text('Withdraw'), button[aria-label*='Withdraw']",
    "dialog": "div[role='dialog'], .artdeco-modal, .ip-fuse-limit-alert",
    "dialog_confirm": "button:has-text('Withdraw'), button.artdeco-button--primary, button:has-text('Confirm')",
}


def _is_older_than_3_weeks(text: str) -> bool:
    """Helper to check if the invitation time-ago text indicates > 21 days (3 weeks)."""
    text = text.lower()
    # Check for month(s) or year(s)
    if "month" in text or "year" in text:
        return True
    # Check for 3+ weeks. LinkedIn shows "3 weeks ago", "4 weeks ago", etc.
    # We want to skip "1 week ago", "2 weeks ago" (14 days).
    if "3 weeks" in text or "4 weeks" in text:
        return True
    return False


def withdraw_old_invitations(session: "AccountSession") -> int:
    """
    Navigates to the sent invitations page on LinkedIn, finds invitations
    sent more than 3 weeks ago, and withdraws them.

    Up to 10 invitations are withdrawn per run.
    """
    logger.info("Starting auto-withdraw of old invitations")
    session.ensure_browser()
    page = session.page
    
    # 1. Navigate to sent invitation manager
    sent_url = "https://www.linkedin.com/mynetwork/invitation-manager/sent/"
    page.goto(sent_url)
    session.wait()  # Allow time for page loading & JS hydration

    # Wait for the main list or a reasonable period
    try:
        page.wait_for_selector(SELECTORS["withdraw_button"], timeout=10000)
    except Exception:
        logger.info("No 'Withdraw' buttons found on the page. Assuming no pending sent invitations.")
        return 0

    # 2. Locate and process invitation cards
    withdrawn_count = 0
    max_withdraws = 10
    i = 0

    while withdrawn_count < max_withdraws:
        # Re-evaluate locator count on every iteration because DOM changes dynamically
        cards_locator = page.locator(SELECTORS["invitation_card"])
        if i >= cards_locator.count():
            break

        card = cards_locator.nth(i)
        try:
            card_text = card.inner_text()
        except Exception:
            # Card might have disappeared already
            continue

        if _is_older_than_3_weeks(card_text):
            logger.info("Found old invitation eligible for withdraw (text: %r)", card_text.replace("\n", " | "))
            
            # Find withdraw button inside this card
            btn = card.locator(SELECTORS["withdraw_button"])
            if btn.count() == 0:
                i += 1
                continue

            try:
                # Add a temporary class to the card so we can track its detachment uniquely
                card.evaluate("el => el.classList.add('withdrawing-temp')")
            except Exception as e:
                logger.error("Failed to tag card with temporary class: %s", e)
                i += 1
                continue

            try:
                # Click the withdraw button
                btn.first.click()
                session.wait()

                # Handle confirmation dialog if it pops up
                dialog = page.locator(SELECTORS["dialog"])
                if dialog.count() > 0:
                    confirm_btn = dialog.locator(SELECTORS["dialog_confirm"])
                    if confirm_btn.count() > 0:
                        confirm_btn.first.click()
                        session.wait()

                # Wait for the card tagged with 'withdrawing-temp' to be removed from the DOM (detached state)
                try:
                    page.locator(".withdrawing-temp").wait_for(state="detached", timeout=3000)
                    withdrawn_count += 1
                    logger.info("Successfully withdrew invitation #%d", withdrawn_count)
                except Exception:
                    logger.warning("Card did not disappear after withdraw, skipping to next index")
                    # Clean up class from the card if it's still there
                    try:
                        page.locator(".withdrawing-temp").evaluate("el => el.classList.remove('withdrawing-temp')")
                    except Exception:
                        pass
                    i += 1

                # Random delay 3-5 seconds to mimic human behavior
                delay = random.uniform(3.0, 5.0)
                time.sleep(delay)

            except Exception as e:
                logger.error("Failed to withdraw invitation: %s", e)
                # Ensure the class is cleaned up if clicking failed
                try:
                    page.locator(".withdrawing-temp").evaluate("el => el.classList.remove('withdrawing-temp')")
                except Exception:
                    pass
                i += 1  # Skip to next card on failure
        else:
            i += 1  # Skip to next card if not old enough

    logger.info("Finished auto-withdraw run. Withdrew %d invitations", withdrawn_count)
    return withdrawn_count


if __name__ == "__main__":
    from linkedin.browser.registry import cli_parser, cli_session

    parser = cli_parser("Withdraw old LinkedIn connection requests")
    args = parser.parse_args()
    session = cli_session(args)

    logger.info("Testing withdraw actions as %s", session)
    withdrawn = withdraw_old_invitations(session)
    logger.info("Withdrew %d invitations during test", withdrawn)
