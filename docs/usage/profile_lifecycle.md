# Profile Lifecycle

## Overview

Every LinkedIn profile flows through a fixed sequence of stages, from first
discovery on a page to agentic follow-up conversations.

```
Discovery → Enrichment + Embedding → Qualification (LLM) → QUALIFIED → READY_TO_CONNECT (GP gate) → PENDING → CONNECTED ─┬→ WAITING_APPROVAL ─┬→ CONNECTED → COMPLETED
  (url)       (voyager + fastembed)     (always LLM)         (Deal)     (GP prob > threshold)         (sent)    (accepted)  │    (requires ok)   │    (approved message)
                                                                                                                          └────────────────────┴→ ESCALATED (high intent)
```

---

## 1. Discovery

**Where:** `browser/nav.py` — `goto_page()` → `_extract_in_urls()` → `_discover_and_enrich()`

Every time the daemon navigates to a LinkedIn page (search results, profile
pages, feed), all `/in/` URLs on the page are extracted. New URLs (those
without an existing Lead) are immediately processed.

LLM-generated search keywords (`pipeline/search.py:run_search()`) drive
additional discovery when the candidate pool runs dry.

## 2. Enrichment + Embedding (eager, at discovery time)

**Where:** `browser/nav.py:_discover_and_enrich()` → `db/leads.py:create_enriched_lead()` → `Lead.get_embedding()`

For each new URL discovered:

1. **Voyager API** fetches structured profile data (name, headline, positions, education, etc.)
2. **Lead** is created with the full profile JSON in `description`
3. **Embedding** is computed (384-dim BAAI/bge-small-en-v1.5 via fastembed) and stored directly on the Lead's `embedding` BinaryField

All steps happen atomically at discovery time. Rate-limited by a randomized
`enrich_min_delay_seconds`–`enrich_max_delay_seconds` pause (default 6–10s)
per profile, capped at `enrich_max_per_page` (default 10) per discovered page.

> **Robustness fallback:** Lazy helpers (`ensure_lead_enriched`,
> `ensure_profile_embedded`) exist in `db/enrichment.py` for rare edge
> cases (manual lead creation, interrupted enrichment, DB inconsistency).
> They log a warning when triggered — this is not normal flow.

## 3. Qualification (LLM only)

**Where:** `pipeline/qualify.py:run_qualification()` (called from connect task backfill via `pools.py`)

Leads with embeddings but no Deal are the qualification pool. Candidate
selection depends on label balance:

| Condition | Strategy | Method |
|-----------|----------|--------|
| `n_negatives > n_positives` | **Exploit** — pick highest predicted probability | `qualifier.predict_probs()` |
| Otherwise | **Explore** — pick highest BALD score | `qualifier.compute_bald()` |

All qualification decisions go through the LLM via `qualify_lead.j2` prompt.
The GP model is used only for candidate selection strategy, not for auto-decisions.

### Cold start

With fewer than 2 labels or a single class, the GP model returns `None`.
The first candidate is selected in order and qualified via LLM.

### Result

- Accepted: Lead promoted → Deal (state=QUALIFIED). LLM reason stored in `Deal.reason`.
- Rejected: FAILED Deal with "Disqualified" closing reason (campaign-scoped, not `Lead.disqualified`). Reason in `Deal.reason`.

## 4. Ready to Connect (QUALIFIED → READY_TO_CONNECT)

**Where:** `pipeline/ready_pool.py:promote_to_ready()`

After qualification, profiles sit at the QUALIFIED state. Before connecting, they
must pass a GP confidence gate:

- `promote_to_ready()` loads all QUALIFIED profiles, computes P(f > 0.5) via the GP model
- Profiles with probability above `min_ready_to_connect_prob` (default 0.9) are promoted to READY_TO_CONNECT
- During cold start (GP not fitted), no profiles are promoted — the connect task keeps triggering qualifications until enough labels accumulate

## 5. Connect (READY_TO_CONNECT → PENDING)

**Where:** `tasks/connect.py:handle_connect()`

The connect handler picks the top READY_TO_CONNECT profile from the pool
(`pipeline/pools.py:find_candidate()` → `pipeline/ready_pool.py:find_ready_candidate()`).

If the pool is empty, the **backfill chain** runs via composable generators:
1. `ready_source()` — check if any QUALIFIED profiles pass the GP gate via `promote_to_ready()`
2. `qualify_source()` — qualify the next unlabeled profile via `run_qualification()`
3. `search_source()` — discover new profiles via `run_search()`

Each generator pulls from the next when empty. Each `qualify_source` iteration
produces exactly one label, preventing infinite-search-without-qualifying.

Connection request is sent without a note. Deal moves to PENDING state.
Rate-limited by `LinkedInProfile.can_execute()` / `record_action()`.

**Unreachable profile detection**: when `send_connection_request` returns
QUALIFIED (no Connect button), `connect_attempts` is incremented; after
`MAX_CONNECT_ATTEMPTS` (3), the lead is disqualified (`lead.disqualified=True`)
and the Deal is marked FAILED.

## 6. Check Pending (PENDING → CONNECTED)

**Where:** `tasks/check_pending.py:handle_check_pending()`

Checks **one** PENDING profile per task execution via `get_connection_status()`.
Uses **exponential backoff** with multiplicative jitter per profile:

- Initial interval: `check_pending_recheck_after_hours` (default 24h)
- Doubles each time the profile is still pending
- Stored in `deal.backoff_hours`

On acceptance → enqueues `follow_up` task.

## 7. Follow Up (CONNECTED → COMPLETED)

**Where:** `tasks/follow_up.py:handle_follow_up()` → `agents/follow_up.py:run_follow_up_agent()`

**Full documentation:** [follow_up_agent.md](./follow_up_agent.md)

Runs an agentic follow-up conversation as a **self-rescheduling loop**: each
invocation syncs the conversation, builds context from profile/chat fact
summaries plus a verbatim message window, and asks the LLM for a structured
`FollowUpDecision`:

| Action | Effect |
|--------|--------|
| `send_message` | Send DM (3 fallback strategies), record action, re-enqueue |
| `wait` | Re-enqueue without sending (check back in `follow_up_hours`) |
| `mark_completed` | Close the Deal (booked, declined, or gone cold) |

If the campaign's `approval_mode` requires it, the message is not sent directly. Instead, the Deal moves to `WAITING_APPROVAL`, storing the text in `PendingMessage` until reviewed by an admin.

The loop continues until the agent returns `mark_completed` or the deal is closed. Default re-check
interval is 72 hours if the agent doesn't specify one. Rate-limited to
`follow_up_daily_limit` (default 30) per LinkedIn account.

## 8. Approval & Escalation (WAITING_APPROVAL / ESCALATED)

When a follow-up message is generated, if the campaign requires manual approval (via `Campaign.approval_mode` set to `all`, `first_touch`, or `high_intent`), the Deal state moves to `WAITING_APPROVAL`.
- **Pending Message**: A `PendingMessage` is created. Interactive alerts are sent to Telegram with inline action buttons (`Approve`, `Skip`, `Edit`).
- **Feedback Loop**: When corrected by the admin, the edits are saved in `AgentFeedback` and are loaded as style corrections for future message generations.
- **Escalation**: If the conversation's intent is classified as `high` or the situation is `needs_human`, the Deal state transitions to `ESCALATED`, and automation is paused until manual resolution.

## 9. Terminal States

- **COMPLETED** — conversation completed by the agent (booked, declined, or went cold)
- **FAILED** — unrecoverable error at any state, or LLM rejection (campaign-scoped "Disqualified" closing reason)

## 10. Account Safety & Protection

To protect the LinkedIn profile from bans, the daemon schedules safety actions:
- **Auto-throttle Connect Limits**: Halves `connect_daily_limit` (floor 5) if the 7-day connection acceptance rate falls below 15%; recovers (+2 per check, up to the original limit) if it exceeds 30%. Checked daily.
- **Auto-withdraw Old Invitations**: Weekly task (`withdraw_old_invites`) navigates to sent invitations on LinkedIn and withdraws pending invitations older than 3 weeks (up to 10 per batch, staggered).

---

## State Diagram

```
                    ┌─────────────┐
                    │  Discovered │  Lead created (url-only or enriched)
                    │  (implicit) │  Embedding stored on Lead
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Qualification│  LLM query (always)
                    └──┬───────┬──┘
                       │       │
              rejected │       │ accepted
                       │       │
            ┌──────────▼┐  ┌───▼────────┐
            │  FAILED    │  │  QUALIFIED │  Deal created
            │(Disqualif.)│  └────┬───────┘
            └────────────┘       │
                                 │ GP confidence gate (P(f>0.5) > threshold)
                          ┌──────▼──────────────┐
                          │  READY_TO_CONNECT   │  GP model confident
                          └──────┬──────────────┘
                                 │ send_connection_request()
                          ┌──────▼──────┐
                          │   PENDING   │  Waiting for acceptance
                          └──────┬──────┘
                                 │ connection accepted
                           ┌──────▼──────┐
                           │  CONNECTED  │◄─────────────────────────────┐
                           └──────┬──────┘                              │
                                  │ run_follow_up_agent()               │
                                  ├───────────────────────────────┐     │
                                  │ (if approval required)        │     │ skip /
                                  ▼                               ▼     │ approve
                           ┌──────────────┐              ┌────────┴─────┴┐
                           │  COMPLETED   │              │WAITING_APPROV.│
                           └──────────────┘              └────────┬──────┘
                                                                  │ intent=high /
                                                                  │ needs_human
                                                                  ▼
                                                         ┌──────────────┐
                                                         │  ESCALATED   │
                                                         └──────────────┘

                           ┌─────────────┐
                           │   FAILED    │  Error at any state
                           └─────────────┘
```

## Freemium Campaigns

Freemium campaigns skip qualification, READY_TO_CONNECT, and search entirely.
They query `Lead` for any embedded lead without a Deal in their
campaign (excluding permanently disqualified leads), ranked by `KitQualifier`.
Profiles go straight to connect, with delay scaled by `action_fraction` to
maintain a target ratio of freemium vs regular connections.
