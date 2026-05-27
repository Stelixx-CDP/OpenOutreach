# linkedin/daemon.py
from __future__ import annotations

import logging
import random
import time
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone
from pydantic_ai.exceptions import ModelHTTPError

from termcolor import colored

from linkedin.conf import (
    ACTIVE_END_HOUR,
    ACTIVE_START_HOUR,
    ACTIVE_TIMEZONE,
    CAMPAIGN_CONFIG,
    ENABLE_ACTIVE_HOURS,
    REST_DAYS,
)
from linkedin.diagnostics import failure_diagnostics
from linkedin.exceptions import AuthenticationError
from linkedin.ml.qualifier import BayesianQualifier, KitQualifier
from linkedin.models import Task
from linkedin.tasks.check_pending import handle_check_pending
from linkedin.tasks.connect import handle_connect
from linkedin.tasks.follow_up import handle_follow_up
from linkedin.tasks.send_approved_message import handle_send_approved_message
from linkedin.tasks.withdraw_old_invites import handle_withdraw_old_invites

logger = logging.getLogger(__name__)


def _safe_notify(event_type: str, **kwargs) -> None:
    """Send a Telegram notification, swallowing any errors."""
    try:
        from linkedin.notifications import safe_notify
        safe_notify(event_type, **kwargs)
    except Exception:
        pass


_HANDLERS = {
    Task.TaskType.CONNECT: handle_connect,
    Task.TaskType.CHECK_PENDING: handle_check_pending,
    Task.TaskType.FOLLOW_UP: handle_follow_up,
    Task.TaskType.SEND_APPROVED_MESSAGE: handle_send_approved_message,
    Task.TaskType.WITHDRAW_OLD_INVITES: handle_withdraw_old_invites,
}

HEARTBEAT_INTERVAL = 300  # 5 minutes
HEARTBEAT_SLICE = 60      # wake every minute during long sleeps
MAX_REAUTH_ATTEMPTS = 3   # stop daemon after N consecutive re-auth failures


# ── Cloud promo ──────────────────────────────────────────────────────

_CLOUD_MESSAGES = [
    "Tired of keeping your laptop open? Run your pipeline in the cloud for $49/mo",
    "You already trust the engine. Now let it run without you babysitting your laptop",
    "The AI gets smarter with every lead. Let it run 24/7 on Cloud instead of only when your laptop is open",
    "Miss a day and the pipeline stalls — follow-ups go cold, new candidates don't get discovered. Cloud keeps it running",
    "The tool got good enough that running it locally became a job. Cloud fixes that",
    "\u2601  OpenOutreach Cloud: same AI, same code, zero ops. One command and you're live",
    "\U0001f9e0 Your AI sales team, running in the cloud. $49/mo",
    "Smart founders shouldn't be acting like robots. Let the AI handle outreach while you build your product",
    "Your leads are compounding. Your laptop shouldn't be the bottleneck",
    "\u26a1 Competitors charge $50-100/mo for template bots. Cloud gives you autonomous AI discovery for $49/mo",
    "Other tools need you to build or buy contact lists. OpenOutreach discovers leads autonomously — describe your market and the AI does the rest",
    "Expandi and Waalaxy send templates. OpenOutreach's AI agent reads conversation history and writes personalized follow-ups",
    "Running Docker + VPN yourself? Cloud handles everything — dedicated server, VPN included",
    "Self-hosted setup: 30-60 min. Cloud setup: ~1 min. Same AI, same results",
    "The server costs ~$18/mo. The VPN costs ~$6/mo. You're paying $25/mo for managed ops — if your time is worth more, Cloud pays for itself",
    "Your data never leaves your machine. Cloud is just a disposable execution layer. $49/mo, cancel anytime",
    "mTLS encryption between your machine and the server. The control plane never sees your data",
    "100% open source. Inspect every line of code on GitHub. Cloud runs the exact same codebase — no black box, no lock-in",
    "Switch between self-hosted and Cloud with one command. Download your db.sqlite3 anytime — zero lock-in",
    "No annual commitment. No usage caps. No feature gating. $49/mo, cancel anytime",
    "openoutreach logs — stream live output from your cloud instance. Watch every lead, every message, every decision in real time",
    "openoutreach down saves your DB locally and destroys the server. No orphaned servers, no forgotten bills",
]

_CLOUD_COLORS = ["cyan", "green", "yellow", "magenta"]

_CLOUD_CTAS = [
    "curl -fsSL https://openoutreach.app/install | sh",
    "curl -fsSL https://openoutreach.app/install | sh && openoutreach signup",
    "https://openoutreach.app",
]


class _CloudPromoRotator:
    """Logs a Cloud promo message at most once every *interval* seconds."""

    def __init__(self, interval: float = 120):
        self._interval = interval
        self._last = 0.0

    def maybe_log(self):
        now = time.monotonic()
        if now - self._last < self._interval:
            return
        self._last = now
        msg = random.choice(_CLOUD_MESSAGES)
        color = random.choice(_CLOUD_COLORS)
        cta = random.choice(_CLOUD_CTAS)
        logger.info(
            colored(msg + " \u2192 ", color, attrs=["bold"])
            + colored(cta, "white", attrs=["bold"]),
        )


# ── Heartbeat ────────────────────────────────────────────────────────


class Heartbeat:
    """Logs an ``alive — <context>`` line at most once every *interval* seconds.

    The first call won't log (``_last`` starts at now) — quiet gaps begin
    counting from daemon start, not the Unix epoch.
    """

    def __init__(self, interval: float = HEARTBEAT_INTERVAL):
        self._interval = interval
        self._last = time.monotonic()

    def maybe_log(self, context: str) -> None:
        now = time.monotonic()
        if now - self._last < self._interval:
            return
        self._last = now
        logger.info(colored("alive", "cyan") + " — %s", context)


def sleep_with_heartbeat(seconds: float, heartbeat: Heartbeat, context: str) -> None:
    """``time.sleep(seconds)`` that wakes every ``HEARTBEAT_SLICE`` seconds to
    let *heartbeat* fire. Use for any idle sleep longer than the heartbeat
    interval so the daemon never goes silent for more than 5 minutes.
    """
    end = time.monotonic() + seconds
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(HEARTBEAT_SLICE, remaining))
        heartbeat.maybe_log(context)


# ── Human-rhythm pacing ──────────────────────────────────────────────


class _HumanRhythmBreak:
    """Wall-clock burst timer that injects a random break between bursts.

    Call ``reset()`` after idle sleeps (active-hours pause, waiting for
    the next scheduled task) so the burst timer tracks real work, not
    wall-clock. Call ``maybe_break()`` after each successful task —
    it sleeps a random break duration when the current burst is done.
    """

    def __init__(self, heartbeat: Heartbeat):
        self._heartbeat = heartbeat
        self._new_burst()

    def _new_burst(self):
        self._burst_start = time.monotonic()
        self._burst_duration = random.uniform(
            CAMPAIGN_CONFIG["burst_min_seconds"],
            CAMPAIGN_CONFIG["burst_max_seconds"],
        )

    def reset(self):
        """Start a fresh burst without taking a break. Use after idle gaps."""
        self._new_burst()

    def maybe_break(self):
        """Sleep a random break and start a new burst if the current one is done."""
        if time.monotonic() - self._burst_start < self._burst_duration:
            return
        break_seconds = random.uniform(
            CAMPAIGN_CONFIG["break_min_seconds"],
            CAMPAIGN_CONFIG["break_max_seconds"],
        )
        logger.info("Taking a %dm break", int(break_seconds // 60))
        sleep_with_heartbeat(
            break_seconds,
            self._heartbeat,
            f"on break, {int(break_seconds // 60)}m total",
        )
        self._new_burst()


def _build_qualifiers(campaigns, cfg, kit_model=None):
    """Create a qualifier for every campaign, keyed by campaign PK."""
    from crm.models import Lead

    qualifiers: dict[int, BayesianQualifier | KitQualifier] = {}
    n_regular = 0
    for campaign in campaigns:
        if campaign.is_freemium:
            if kit_model is None:
                continue
            qualifiers[campaign.pk] = KitQualifier(kit_model)
        else:
            q = BayesianQualifier(
                seed=42,
                n_mc_samples=cfg["qualification_n_mc_samples"],
                campaign=campaign,
            )
            X, y = Lead.get_labeled_arrays(campaign)
            if len(X) > 0:
                q.warm_start(X, y)
                logger.info(
                    colored("GP qualifier warm-started", "cyan")
                    + " on %d labelled samples (%d positive, %d negative)"
                    + " for campaign %s",
                    len(y), int((y == 1).sum()), int((y == 0).sum()), campaign,
                )
            qualifiers[campaign.pk] = q
            n_regular += 1

    return qualifiers


# ------------------------------------------------------------------
# Active-hours schedule guard
# ------------------------------------------------------------------


def seconds_until_active() -> float:
    """Return seconds to wait before the next active window, or 0 if active now."""
    if not ENABLE_ACTIVE_HOURS:
        return 0.0
    tz = ZoneInfo(ACTIVE_TIMEZONE)
    now = timezone.localtime(timezone=tz)

    if now.weekday() not in REST_DAYS and ACTIVE_START_HOUR <= now.hour < ACTIVE_END_HOUR:
        return 0.0

    # Find the next active start: try today first, then subsequent days
    candidate = timezone.make_aware(
        now.replace(hour=ACTIVE_START_HOUR, minute=0, second=0, microsecond=0, tzinfo=None),
        timezone=tz,
    )
    if candidate <= now:
        candidate += timedelta(days=1)
    while candidate.weekday() in REST_DAYS:
        candidate += timedelta(days=1)
    return (candidate - now).total_seconds()


# ------------------------------------------------------------------
# Task queue worker
# ------------------------------------------------------------------


def run_daemon(session):
    from linkedin.models import Campaign

    cfg = CAMPAIGN_CONFIG

    qualifiers = _build_qualifiers(
        session.campaigns, cfg, kit_model=None,
    )

    campaigns = session.campaigns
    if not campaigns:
        logger.error("No campaigns found — cannot start daemon")
        return

    logger.info(
        colored("Daemon started", "green", attrs=["bold"])
        + " — %d campaigns, task queue worker",
        len(campaigns),
    )

    cloud_promo = _CloudPromoRotator(interval=60)
    heartbeat = Heartbeat()
    rhythm = _HumanRhythmBreak(heartbeat)

    # Single-threaded: one task at a time, no concurrent enqueuing,
    # so sleeping until the next scheduled_at is safe.
    _reauth_failures = 0
    _last_throttle_check = None
    while True:
        pause = seconds_until_active()
        if pause > 0:
            h, m = int(pause // 3600), int(pause % 3600 // 60)
            logger.info("Outside active hours — sleeping %dh%02dm", h, m)
            sleep_with_heartbeat(
                pause, heartbeat, f"outside active hours, {h}h{m:02d}m left",
            )
            rhythm.reset()
            continue

        if session.page and not session.is_alive():
            logger.warning("Browser is dead/unresponsive during health check — closing session to recover")
            try:
                session.close()
            except Exception as e:
                logger.debug("Error closing unresponsive session: %s", e)

        task = Task.objects.claim_next()
        if task is None:
            # Run safety checks (at most once every 24 hours)
            now = timezone.now()
            if _last_throttle_check is None or (now - _last_throttle_check).total_seconds() > 86400:
                try:
                    from linkedin.safety import auto_throttle_check
                    auto_throttle_check(session.linkedin_profile)
                    _last_throttle_check = now
                except Exception as safety_exc:
                    logger.error("Failed to run safety auto-throttle check: %s", safety_exc)

            # Nothing ready — reconcile the queue from CRM state. Any deal
            # stuck without a pending task (e.g. because a prior handler
            # crashed) gets a fresh task here; this is the retry mechanism.
            from linkedin.tasks.scheduler import reconcile
            reconcile(session)

            wait = Task.objects.seconds_to_next()
            if wait is None:
                logger.info("Queue empty after reconcile — sleeping 1h")
                sleep_with_heartbeat(3600, heartbeat, "queue empty")
            elif wait > 0:
                logger.info("Next task in %.1fs — sleeping", wait)
                sleep_with_heartbeat(wait, heartbeat, "waiting for task")
            rhythm.reset()
            continue

        campaign_id = task.payload.get("campaign_id")
        campaign = None
        if campaign_id:
            campaign = Campaign.objects.filter(pk=campaign_id).first()
        elif task.task_type == Task.TaskType.WITHDRAW_OLD_INVITES:
            # Fallback to the first campaign associated with the user of this session
            campaign = Campaign.objects.filter(users=session.linkedin_profile.user).first()

        if not campaign:
            logger.error("Campaign %s not found for task %s", campaign_id, task.task_type)
            task.mark_failed()
            continue

        session.campaign = campaign
        task.mark_running()

        handler = _HANDLERS.get(task.task_type)
        if handler is None:
            logger.error("Unknown task type: %s", task.task_type)
            task.mark_failed()
            continue

        from playwright.sync_api import Error as PlaywrightError
        MAX_BROWSER_RETRIES = 2
        try:
            for attempt in range(MAX_BROWSER_RETRIES + 1):
                try:
                    with failure_diagnostics(session):
                        handler(task, session, qualifiers)
                    break
                except (PlaywrightError, TimeoutError) as e:
                    if attempt < MAX_BROWSER_RETRIES:
                        logger.warning(
                            "Browser/Playwright error during task %s (attempt %d/%d): %s. Re-launching session...",
                            task, attempt + 1, MAX_BROWSER_RETRIES, e
                        )
                        try:
                            session.close()
                        except Exception:
                            pass
                        try:
                            session.ensure_browser()
                        except Exception as re_err:
                            logger.exception("Failed to re-initialize browser session: %s", re_err)
                    else:
                        raise
        except AuthenticationError:
            logger.warning("Session expired during %s — re-authenticating", task)
            _safe_notify("cookie_expired", profile=session.linkedin_profile.linkedin_username)
            _reauth_failures += 1
            if _reauth_failures > MAX_REAUTH_ATTEMPTS:
                logger.error(
                    colored("Daemon stopped — re-authentication failed %d times", "red", attrs=["bold"]),
                    _reauth_failures,
                )
                _safe_notify("browser_crash", task_type=task.task_type,
                             error=f"Re-authentication failed {_reauth_failures} consecutive times. "
                                   f"Account may be locked or password incorrect.",
                             campaign=session.campaign)
                task.mark_failed()
                return
            try:
                session.reauthenticate()
                _reauth_failures = 0
            except Exception:
                logger.exception("Re-authentication failed for %s", task)
            # Either way, mark this task FAILED; reconcile will re-create a
            # fresh task for the deal on the next idle cycle.
            task.mark_failed()
            continue
        except ModelHTTPError as e:
            task.mark_failed()
            logger.error(
                colored("Daemon stopped — LLM API error", "red", attrs=["bold"])
                + "\n%s\nCheck llm_provider, ai_model, llm_api_key, and llm_api_base in Admin → Site Configuration.", e,
            )
            _safe_notify("llm_error", error=str(e))
            return
        except ValueError as e:
            error_msg = str(e)
            if any(keyword in error_msg for keyword in ("LLM_API_KEY", "AI_MODEL", "LLM_API_BASE", "LLM provider")):
                task.mark_failed()
                logger.error(
                    colored("Daemon stopped — LLM configuration error", "red", attrs=["bold"])
                    + "\n%s\nUpdate Site Configuration in Admin.", error_msg,
                )
                _safe_notify("llm_error", error=error_msg)
                return
            # Non-LLM ValueError — fall through to generic handling
            task.mark_failed()
            logger.exception("Task %s failed", task)
            screenshot_bytes = None
            try:
                if session.page and not session.page.is_closed():
                    screenshot_bytes = session.page.screenshot(timeout=5000)
            except Exception:
                pass
            _safe_notify(
                "browser_crash",
                task_type=task.task_type,
                error=error_msg,
                screenshot=screenshot_bytes,
                campaign=session.campaign,
            )
            continue
        except Exception as e:
            task.mark_failed()
            logger.exception("Task %s failed", task)
            screenshot_bytes = None
            try:
                if session.page and not session.page.is_closed():
                    screenshot_bytes = session.page.screenshot(timeout=5000)
            except Exception:
                pass
            _safe_notify(
                "browser_crash",
                task_type=task.task_type,
                error=str(e),
                screenshot=screenshot_bytes,
                campaign=session.campaign,
            )
            continue

        task.mark_completed()
        _reauth_failures = 0
        cloud_promo.maybe_log()
        rhythm.maybe_break()
