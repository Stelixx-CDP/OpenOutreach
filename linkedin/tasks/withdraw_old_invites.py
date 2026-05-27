# linkedin/tasks/withdraw_old_invites.py
"""Task handler for withdrawing old pending connection requests.

Invokes the browser UI action to navigate to sent invitation manager and withdraw.
"""
from __future__ import annotations

import logging
from termcolor import colored

from linkedin.actions.withdraw import withdraw_old_invitations

logger = logging.getLogger(__name__)


def handle_withdraw_old_invites(task, session, qualifiers):
    """
    Handler for withdrawing old invitations. Runs the UI action
    and logs the number of withdrawn invitations.
    """
    profile = session.linkedin_profile
    profile_label = profile.user.username if (profile and profile.user) else (profile.linkedin_username if profile else "General")

    logger.info(
        "[%s] %s",
        profile_label,
        colored("\u25b6 withdraw_old_invites", "yellow", attrs=["bold"]),
    )

    withdrawn_count = withdraw_old_invitations(session)
    logger.info(
        "[%s] Withdrew %d old invitations.",
        profile_label,
        withdrawn_count,
    )
