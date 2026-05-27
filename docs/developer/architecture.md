# System Architecture

This document outlines the architecture of OpenOutreach, from system entry and data models to the daemon-driven workflow engine and machine learning pipeline.

---

## 1. High-Level Overview

OpenOutreach automates LinkedIn outreach through a background daemon that schedules actions continuously:

1. **Input & Discovery**: New profiles are auto-discovered as the daemon navigates LinkedIn pages (feed, search, profiles). When the candidate pool runs dry, LLM-generated search keywords are used to discover new profiles.
2. **Enrichment**: The daemon scrapes detailed profile data via LinkedIn's internal Voyager API, stores it in the CRM, and computes embeddings.
3. **Qualification**: Profiles are qualified using a Gaussian Process Regressor (GPR) with BALD active learning. The model selects the most informative profiles to query via LLM. All final qualification decisions go through the LLM; the GP is used only for candidate selection and the confidence gate.
4. **Outreach & Nurturing**: Connection requests are sent to the highest-ranked qualified profiles, and agentic follow-up conversations run after acceptance.
5. **State Tracking**: Each profile progresses through a state machine, tracked as Deal states in the CRM.

---

## 2. System Entry & Startup Flow

`manage.py` is the stock Django management entrypoint. Running `python manage.py` (no args) defaults to the `rundaemon` command.

### The `rundaemon` Command (`management/commands/rundaemon.py`)
Startup sequence:
1. **Configure Logging**: Sets log level to DEBUG and suppresses noisy third-party loggers (urllib3, httpx, pydantic_ai, openai, playwright, etc.).
2. **Ensure DB**: Runs `migrate --no-input` and executes `setup_crm` (idempotent bootstrap creating the default Site).
3. **Onboard**: Checks for `missing_keys()`. If incomplete, onboarding is triggered:
   - Uses `--onboard <config.json>` if provided (non-interactive).
   - Falls back to interactive wizard on TTY.
   - Exits with a clear error if no TTY is available.
4. **Validate**: Verifies `LLM_API_KEY`, active `LinkedInProfile`, and at least one campaign exist.
5. **Session**: Initiates `get_or_create_session(profile)` and sets the default campaign (first non-freemium).
6. **Newsletter**: Evaluates GDPR override and runs `ensure_newsletter_subscription()` (marker-guarded, runs once).
7. **Run**: Enters the main execution loop: `run_daemon(session)`.

### Other Management Commands
- `onboard`: Standalone onboarding (interactive or non-interactive with `--config-file` or individual flags).
- `setup_crm`: Idempotent CRM bootstrap.
- `add_seeds`: Adds seed LinkedIn profile URLs to a campaign.

---

## 3. Core Data Model & State Machine

The system uses Django with SQLite (by default at `data/db.sqlite3`).

### Models
- **Lead** (`crm/models/lead.py`) — One per LinkedIn profile URL.
  - `linkedin_url` (URLField, unique): Primary key for deduplication.
  - `public_identifier` (CharField, unique): Derived from URL.
  - `urn` (CharField, unique, nullable): Voyager entity URN.
  - `embedding` (BinaryField): 384-dim fastembed vector as bytes (accessed via `embedding_array` property).
  - `description` (TextField): Full parsed profile JSON.
  - `disqualified` (bool): Permanent account-level exclusion.
- **Deal** (`crm/models/deal.py`) — Tracks campaign-specific state for a Lead.
  - `lead` (FK to Lead): Reference to the lead.
  - `campaign` (FK to Campaign): Reference to the campaign.
  - `state` (CharField): State choices from `ProfileState` enum.
  - `outcome` (CharField): Outcome choices from `Outcome` enum (converted, not_interested, wrong_fit, no_budget, etc.).
  - `reason` (TextField): Free-text qualification reason.
  - `connect_attempts` (int): Number of connection attempts.
  - `backoff_hours` (int): Check pending backoff interval.
  - `profile_summary` / `chat_summary` (JSONField): Lazy, mem0-style campaign-scoped fact lists.
- **Campaign** (`linkedin/models.py`) — Outreach campaign settings.
  - `name` (CharField, unique): Display name.
  - `users` (M2M to User): LinkedIn accounts running this campaign.
  - `product_docs` (TextField): Product/service context for LLM.
  - `campaign_objective` (TextField): Target ICP and qualification criteria for LLM.
  - `booking_link` (URLField): Link sent in follow-up messages.
  - `is_freemium` (bool): Deprecated/unused.
  - `action_fraction` (float): Gating ratio between campaigns.
  - `seed_public_ids` (JSONField): Seed profiles to bootstrap discovery.
- **LinkedInProfile** (`linkedin/models.py`) — 1:1 with Django `auth.User`.
  - Credentials, rate limits (`connect_daily_limit`, `connect_weekly_limit`, `follow_up_daily_limit`), and session persistence (`cookie_data`).
- **SearchKeyword** (`linkedin/models.py`) — FK to Campaign. Keyword generator seeds.
- **ActionLog** (`linkedin/models.py`) — Tracks sent actions for rate limiting.
- **Task** (`linkedin/models.py`) — Background job queue.

### Profile State Machine (`linkedin/enums.py:ProfileState`)

```
(url_only) → (enriched) → QUALIFIED → READY_TO_CONNECT → PENDING → CONNECTED → COMPLETED
  (implicit)   (implicit)   (Deal)     (GP confidence gate)  (sent)   (accepted)   (followed up)
                                 ↓                                       ↓
                           FAILED (LLM rejection)                   ESCALATED (Intent=high / needs_human)
```

Pre-Deal states are implicit: a Lead with no description is `url_only`, a Lead with description is `enriched`. `ProfileState` contains: `QUALIFIED`, `READY_TO_CONNECT`, `PENDING`, `CONNECTED`, `COMPLETED`, `FAILED`, `ESCALATED`.

---

## 4. Daemon & Task Queue

The background worker (`linkedin/daemon.py`) runs an infinite loop executing tasks from the priority queue:

```
while True:
    1. Check active hours (e.g., 9h-19h, skip Sat/Sun) -> sleep if inactive
    2. claim_next() -> pop oldest pending task due by scheduled_at
    3. If no task -> reconcile() from CRM state -> sleep waiting
    4. Run handler (connect, check_pending, follow_up)
    5. rhythm.maybe_break() -> burst 45-65min, break 10-20min
```

### Task Creation and Reconciliation (`linkedin/tasks/scheduler.py`)
Task creation is strictly centralized in `tasks/scheduler.py`.
- **State Hooks**: State transitions (`set_profile_state`) trigger `on_deal_state_entered(deal)`, enqueuing the appropriate task.
- **Reconciliation**: If the queue runs dry, `reconcile(session)` is called to recover stuck tasks, seed new connection runs, and ensure active Deals have tasks scheduled.

### Task Handlers (`linkedin/tasks/`)
- **`connect.py` (`handle_connect`)**: Unified handler. Sourced via composition: `ready_source` -> `qualify_source` -> `search_source`. Sends connection request without a note.
- **`check_pending.py` (`handle_check_pending`)**: Evaluates a `PENDING` lead for connection acceptance. Uses exponential backoff with jitter, storing current interval in `deal.backoff_hours`.
- **`follow_up.py` (`handle_follow_up`)**: Synchronizes conversations and triggers the `FollowUpAgent` to decide on sending DMs or closing the deal.

---

## 5. ML Qualification Pipeline

OpenOutreach qualifies candidates using active learning with a Gaussian Process Regressor:

1. **Acquisition & Label Balance**:
   - `n_negatives > n_positives` -> **Exploit**: Pick profiles with the highest predicted qualification probability.
   - Otherwise -> **Explore**: Pick profiles with the highest BALD (Bayesian Active Learning by Belief Disagreement) score.
2. **LLM Qualification**: All qualification decisions are made by the LLM via `qualify_lead.j2`. GP scores are only used for ranking candidates to prioritize LLM calls.
3. **READY_TO_CONNECT Gate**: QUALIFIED deals must cross a GP posterior probability threshold ($P(f > 0.5) > 0.9$) to be promoted to `READY_TO_CONNECT`.
4. **Embeddings**: Uses `fastembed` (default `BAAI/bge-small-en-v1.5`, 384-dimensional) on text concatenated from headlines, summaries, and job descriptions (`linkedin/ml/profile_text.py`).

---

## 6. Codebase Modules

### 1. Actions (`linkedin/actions/`)
Browser actions that orchestrate the browser via Playwright:
- `connect.py`: Direct connect button targeting, falls back to "More" menu. Sends no note.
- `status.py`: Resolves connection degree via API decor or UI fallback.
- `message.py`: Sends DMs using popup, thread navigation, or Voyager API.
- `conversations.py`: Syncs conversation history.
- `search.py`: Handles search results and profile visits.

### 2. API Client (`linkedin/api/`)
- `client.py` (`PlaywrightLinkedinAPI`): Evaluates raw JavaScript `fetch` calls directly inside the browser context, inheriting cookies and headers.
- `voyager.py`: Decodes Voyager API responses into structured dataclasses.
- `messaging/`: Handles GraphQL messaging and conversation sync.

### 3. Browser (`linkedin/browser/`)
- `session.py` (`AccountSession`): Manages Playwright page, context, browser, and user profile state.
- `login.py`: Automates credential login, handling cookie refresh.
- `nav.py`: Provides page navigation and human-like typing helpers.

### 4. Database Operations (`linkedin/db/`)
- `leads.py` / `deals.py`: Data layer CRUD.
- `chat.py`: Syncs message history and updates summaries.
- `summaries.py`: Houses the mem0 fact extraction logic:
  - `profile_summary`: Scrapes profile facts on first follow-up.
  - `chat_summary`: Extracts conversation facts incrementally and reconciles them via an LLM update prompt (ADD/UPDATE/DELETE/NONE actions).

### 5.5. Conversation Optimization Pipeline

The follow-up agent's output passes through a multi-stage validation and retry pipeline before any message reaches a lead:

1. **Conversation Mode Detection** (`agents/conversation_mode.py`): Classifies the conversation as `INITIAL_OUTREACH`, `LEAD_REPLIED`, or `NO_REPLY_BUMP` based on the last message direction.
2. **Name Safety** (`agents/name_safety.py`): Extracts a verified first name from the lead's profile, guarding against using the seller's own name or unverified names.
3. **Output Validation** (`agents/output_validator.py`): Checks the LLM-generated message against rules:
   - No greetings in `NO_REPLY_BUMP` or `LEAD_REPLIED` modes.
   - Name correctness (not the seller's name, must be verified).
   - Forbidden corporate jargon (word-boundary matching to prevent substring false positives).
   - No em-dashes or en-dashes.
   - Word count cap for bumps (<= 20 words).
   - All violations are accumulated in a single pass so the retry prompt can address everything at once.
4. **Retry with Feedback** (`output_validator.py:generate_with_retry`): If validation fails, the original prompt is augmented with error feedback and the LLM is called again (max 1 retry).
5. **Safe Fallback**: If validation still fails after retry, the decision is converted to a `wait` action (24h) and a Telegram notification is sent. No dirty message ever reaches a lead.
6. **Hours Clamping**: `follow_up_hours` is clamped to [1, 168] to prevent LLM hallucinations (e.g. 0.01h or 9999h).

---

## 8. Error Handling & Diagnostics

- **Fail-Fast**: The daemon crashes on unexpected exceptions. Only expected network or rate limit errors are caught.
- **Diagnostics**: `failure_diagnostics()` captures screenshots, page DOM content, and tracebacks into `/tmp/openoutreach-diagnostics/` when a task fails.
- **Browser Recovery (Phase 3)**: Browser crashes are detected and recovered automatically:
  - `AccountSession.is_alive()` runs a trivial JS evaluation (`1 + 1`) to check browser health before claiming new tasks.
  - If the browser is unresponsive, `session.close()` cleans up the dead session before proceeding.
  - Task handlers are wrapped in a retry loop (max 2 retries) for Playwright errors (`TargetClosedError`, `TimeoutError`, `Error`).
  - Each retry: log warning, close session, `ensure_browser()` to re-launch Chrome, re-run handler.
  - If all retries fail: capture screenshot, send Telegram alert via `safe_notify("browser_crash", ...)`, mark task as `FAILED`.

