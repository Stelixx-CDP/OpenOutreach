# linkedin/safety.py
"""Safety metrics and auto-throttling logic for protecting LinkedIn accounts."""
from __future__ import annotations

import datetime
import logging
from django.utils import timezone

from crm.models import Deal
from linkedin.enums import ProfileState
from linkedin.models import ActionLog

logger = logging.getLogger(__name__)


def compute_acceptance_rate_7d(profile) -> float:
    """Calculate the connect acceptance rate over the last 7 days for the profile's campaigns."""
    now = timezone.now()
    seven_days_ago = now - datetime.timedelta(days=7)

    # 1. Total connects sent by this profile in the last 7 days
    sent_7d = ActionLog.objects.filter(
        linkedin_profile=profile,
        action_type=ActionLog.ActionType.CONNECT,
        created_at__range=(seven_days_ago, now)
    ).count()

    if sent_7d == 0:
        return None

    # 2. Deals in campaign associated with this profile's user that were accepted
    accepted_7d = Deal.objects.filter(
        campaign__users=profile.user,
        state__in=[
            ProfileState.CONNECTED.value,
            ProfileState.COMPLETED.value,
            ProfileState.ESCALATED.value,
            ProfileState.WAITING_APPROVAL.value
        ],
        creation_date__range=(seven_days_ago, now)
    ).count()

    return accepted_7d / sent_7d


def auto_throttle_check(profile) -> None:
    """Check the 7-day acceptance rate and throttle or restore connect limits accordingly."""
    rate_7d = compute_acceptance_rate_7d(profile)
    if rate_7d is None:
        return

    # Ensure original limit is initialized and synchronized with manual updates
    if not profile.original_connect_daily_limit or profile.connect_daily_limit > profile.original_connect_daily_limit:
        profile.original_connect_daily_limit = profile.connect_daily_limit
        profile.save(update_fields=["original_connect_daily_limit"])

    original_limit = profile.original_connect_daily_limit
    current_limit = profile.connect_daily_limit

    from linkedin.notifications import safe_notify

    if rate_7d < 0.15:
        # Throttle: Halve limit (min 5)
        new_limit = max(5, current_limit // 2)
        if new_limit != current_limit:
            profile.connect_daily_limit = new_limit
            profile.save(update_fields=["connect_daily_limit"])
            logger.warning(
                "Auto-throttle connect limit reduced from %d to %d (acceptance rate: %.1f%%)",
                current_limit, new_limit, rate_7d * 100
            )
            safe_notify(
                "auto_throttle",
                profile=profile,
                rate=rate_7d,
                new_limit=new_limit,
                severity="warning"
            )
    elif rate_7d > 0.30 and current_limit < original_limit:
        # Restore: Gradually increase by 2 (max original_limit)
        new_limit = min(original_limit, current_limit + 2)
        if new_limit != current_limit:
            profile.connect_daily_limit = new_limit
            profile.save(update_fields=["connect_daily_limit"])
            logger.info(
                "Auto-throttle connect limit restored from %d to %d (acceptance rate: %.1f%%)",
                current_limit, new_limit, rate_7d * 100
            )
            safe_notify(
                "auto_throttle",
                profile=profile,
                rate=rate_7d,
                new_limit=new_limit,
                severity="info"
            )
