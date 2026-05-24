# [Final] Idea and Implementation Plan — OpenOutreach × Geolify.ai GTM

> **Tài liệu này là Source of Truth** cho toàn bộ quá trình nâng cấp OpenOutreach.
> Tổng hợp từ debate giữa plan Gemini 3.5 (8 phases tuần tự) và đề xuất độc lập (3-tier architecture).
>
> **Updated:** 2026-05-24
> **Owner:** @Gnoc Ng

---

## Phần I: Debate — Gemini 3.5 vs Đề xuất Độc lập

### Bối cảnh 2 plan

| | Gemini 3.5 | Đề xuất Độc lập |
|---|---|---|
| **Cấu trúc** | 8 Phases tuần tự, flat | 3 Tầng (Nhìn Thấy → Kiểm Soát → Mở Rộng) |
| **Góc nhìn** | Feature-driven: liệt kê feature cần thêm | Problem-driven: chẩn đoán 4 vấn đề gốc rồi mới đề giải pháp |
| **Scope** | Chỉ LinkedIn automation | LinkedIn + Content + Reddit + Multi-channel |
| **Verification** | ✅ Có test plan chi tiết cho từng phase | ❌ Thiếu verification plan cụ thể |

### 9 điểm debate

#### 1. Telegram Notifications
| Gemini 3.5 | Đề xuất Độc lập | Verdict |
|---|---|---|
| Phase 1 — daily report + error alerts | Tier 1A — mở rộng thêm alert khi lead reply, deal state change | **Merge:** Lấy scope rộng hơn của Độc lập + verification plan chi tiết của Gemini |

Cả hai đồng ý đây là ưu tiên #1 tuyệt đối. Đề xuất Độc lập bổ sung thêm "alert mỗi khi lead reply" — đây là insight quan trọng vì bài học Laurent cho thấy: biết lead reply trễ = mất momentum.

**→ Final: Phase 1, scope mở rộng**

---

#### 2. Self-healing & Error Recovery
| Gemini 3.5 | Đề xuất Độc lập | Verdict |
|---|---|---|
| Phase 4 (thứ tự thấp) | Tier 1 (ưu tiên cao) — gộp vào Account Safety cùng auto-throttle | **Đưa lên Phase 2** |

**Lý do đưa lên:** VPS Nhật chạy 24/7, Chrome crash là chuyện **chắc chắn xảy ra**. Mỗi crash = task FAILED = mất lead. Hệ thống hiện tại (`daemon.py` line 339) chỉ `task.mark_failed()` + `logger.exception()` rồi `continue` — không retry, không alert. Cần fix **trước** khi scale volume.

**→ Final: Phase 2, tách riêng khỏi Account Safety vì cần làm sớm**

---

#### 3. Intent Detection
| Gemini 3.5 | Đề xuất Độc lập | Verdict |
|---|---|---|
| Phase 5 — thêm `intent: high/low/none` | Tier 1B — thêm cả `intent` VÀ `situation` (7 giá trị) | **Lấy `situation` của Độc lập, đơn giản hóa còn 5 giá trị** |

**Debate:**
- Gemini 3.5 chỉ thêm 3 mức intent. Nhưng intent chưa đủ — cần biết **bối cảnh** để quyết định hành động.
- Ví dụ thực tế: Laurent reply "the code did not work" → intent = `low` hoặc `none`, nhưng situation = `reporting_issue`. Hành động đúng không phải "AI tiếp tục Mom Test" mà là "ESCALATE cho human fix bug".
- `situation` giúp phân biệt các tình huống mà mỗi tình huống cần handling khác nhau.
- Đơn giản hóa từ 7 → 5: `engaging`, `curious`, `needs_human`, `objecting`, `cold`

**→ Final: Phase 3, `intent` (3 mức) + `situation` (5 mức)**

---

#### 4. Auto-withdraw Old Invites
| Gemini 3.5 | Đề xuất Độc lập | Verdict |
|---|---|---|
| Phase 2 (ưu tiên cao, tách riêng) | Gộp vào Account Safety (2C) cùng auto-throttle, health monitor | **Gộp vào Account Safety** |

**Lý do gộp:** Auto-withdraw đơn lẻ chỉ giải quyết 1/3 vấn đề account safety. Cần gộp cùng auto-throttle (dynamic rate limiting) và health monitor thành một module thống nhất.

**→ Final: Nằm trong Phase 6 (Account Safety), không tách riêng**

---

#### 5. Approval Gate
| Gemini 3.5 | Đề xuất Độc lập | Verdict |
|---|---|---|
| Phase 3 — Boolean on/off (`require_approval_for_outreach`) | Tier 2A — 4 chế độ (`auto`, `first_touch_only`, `high_intent_only`, `all`) | **Lấy 4 chế độ của Độc lập** |

**Debate:**
- Boolean on/off của Gemini quá cứng: ON = approve MỌI message (30+/ngày, không khả thi), OFF = không approve gì.
- `first_touch_only` là sweet spot: approve message đầu tiên cho mỗi lead (first impression), sau đó AI tự do. Bạn chỉ cần approve ~10-15 messages/ngày thay vì 30+.
- `high_intent_only` hữu ích khi đã tin tưởng AI: chỉ can thiệp khi có hot lead hoặc tình huống đặc biệt.

**→ Final: Phase 4, 4 chế độ approval**

---

#### 6. Agent Feedback Loop
| Gemini 3.5 | Đề xuất Độc lập | Verdict |
|---|---|---|
| ❌ **Không có** | Tier 2B — lưu corrections, inject vào prompt | **Thêm vào, gộp cùng Approval Gate** |

**Lý do thêm:** Khi bạn Edit message trong Approval Gate, thông tin đó hiện tại bị **mất**. Agent không learn từ corrections. Feedback Loop biến mỗi lần edit thành training signal — inject 3-5 recent corrections vào prompt → in-context learning, **zero cost**.

**→ Final: Gộp vào Phase 4 (Approval Gate + Feedback Loop)**

---

#### 7. Link Tracking
| Gemini 3.5 | Đề xuất Độc lập | Verdict |
|---|---|---|
| Phase 7 (thứ tự thấp, Dub.co fallback) | Tier 1C (ưu tiên cao) | **Đưa lên Phase 5, bỏ Dub.co** |

**Debate:**
- Gemini xếp tracking ở Phase 7 (gần cuối) — sai vì **bạn cần đo lường CTR từ ngày đầu**.
- Không có tracking, bạn chỉ biết "lead đã reply" chứ không biết "lead đã click audit link". Click mà không reply = vẫn là engagement signal mạnh.
- Bỏ Dub.co — local redirect đủ đơn giản, không cần thêm external dependency.

**→ Final: Phase 5, local redirect only**

---

#### 8. Smart Active Hours (timezone-based)
| Gemini 3.5 | Đề xuất Độc lập | Verdict |
|---|---|---|
| Phase 6 — hard rules + soft rules timezone | ❌ **Bỏ** — ROI thấp | **Bỏ khỏi plan** |

**Lý do bỏ:**
- Đã có `ENABLE_ACTIVE_HOURS` (9h-19h, skip weekend) — đủ cho hard rules.
- Follow-up agent tự quyết `follow_up_hours`. Thêm timezone logic = override agent decision.
- Target audience US/UK/AU — timezone overlap VN active hours OK cho LinkedIn async messaging.
- Data từ Lemlist, Expandi: send time impact < 5% lên reply rate.
- Effort ~3 ngày cho ROI rất thấp.

**→ Final: Bỏ. Giữ ACTIVE_HOURS defaults.**

---

#### 9. Content Automation + Reddit + Multi-channel
| Gemini 3.5 | Đề xuất Độc lập | Verdict |
|---|---|---|
| ❌ **Hoàn toàn không đề cập** | Tier 3 — Content + Reddit + Multi-account | **Thêm cả 3** |

**Lý do thêm Content Automation (quan trọng nhất):**
- SSI "Engage with insights" = **0.7/25** — profile gần như invisible
- Pilot doc: "daemon push connects mà profile không post/comment → pattern bất thường → flag risk"
- Content engagement trước connection request = **warm outreach** → acceptance rate tăng 30-50%

**→ Final: Phase 7 (Content), Phase 8 (Reddit), Phase 9 (Multi-account), Phase 10 (CDP)**

---

### Tổng kết Debate

| Gemini 3.5 Phase | Final Phase | Thay đổi |
|---|---|---|
| Phase 1: Telegram | **Phase 1** | Giữ nguyên, mở rộng scope |
| Phase 4: Self-healing | **Phase 2** | ⬆️ Lên 2 bậc |
| Phase 5: Intent Detection | **Phase 3** | ⬆️ Lên 2 bậc, thêm `situation` |
| Phase 3: Approval Gate | **Phase 4** | ↓ 1 bậc, thêm 4 chế độ + feedback loop |
| Phase 7: Link Tracking | **Phase 5** | ⬆️ Lên 2 bậc, bỏ Dub.co |
| Phase 2: Auto-withdraw | **Phase 6** (gộp) | ↓ Gộp vào Account Safety + auto-throttle |
| Phase 6: Smart Hours | **Bỏ** | ROI quá thấp |
| Phase 8: CDP | **Phase 10** | ↓ Cuối cùng |
| *(mới)* Content Automation | **Phase 7** | ➕ Từ Đề xuất Độc lập |
| *(mới)* Reddit Presence | **Phase 8** | ➕ Từ Đề xuất Độc lập |
| *(mới)* Multi-account | **Phase 9** | ➕ Từ Đề xuất Độc lập |
| *(mới)* Agent Feedback Loop | Gộp Phase 4 | ➕ Từ Đề xuất Độc lập |
| *(mới)* Auto-throttle | Gộp Phase 6 | ➕ Từ Đề xuất Độc lập |

---

## Phần II: Implementation Plan — 10 Phases, 3 Tầng

### Tổng quan Timeline

```
Tầng 1 — NHÌN THẤY (Phase 1-3, ~8-10 ngày)
├── Phase 1: Telegram Notifications       ~3-4d
├── Phase 2: Self-healing & Recovery       ~2-3d
└── Phase 3: Intent + Situation Detection  ~3d

Tầng 2 — KIỂM SOÁT (Phase 4-6, ~9-12 ngày)
├── Phase 4: Approval Gate + Feedback Loop ~4-5d
├── Phase 5: Link Tracking                 ~2-3d
└── Phase 6: Account Safety                ~3-4d

Tầng 3 — MỞ RỘNG (Phase 7-10, ~17-24 ngày)
├── Phase 7: Content Automation            ~5-7d
├── Phase 8: Reddit Presence               ~5-7d
├── Phase 9: Multi-account Support         ~3-5d
└── Phase 10: Stelixx CDP Integration      ~4-5d
```

---

### Phase 1: Telegram Notifications — "Bật đèn lên"

**Mục tiêu:** Biết chuyện gì đang xảy ra mà không cần SSH vào VPS.

**Thiết kế:**

Tạo module `linkedin/notifications.py`:
- `send_text(html)` — gửi tin nhắn HTML qua Bot API
- `send_photo(photo_bytes, caption)` — gửi screenshot
- `notify(event_type, **kwargs)` — dispatcher trung tâm

**Events:**

| Event | Trigger point | Format |
|-------|--------------|--------|
| Lead reply (bất kỳ) | `db/chat.py` sync_conversation | 📩 `[Campaign] Lead replied: "preview..."` |
| Deal state change | `db/deals.py` set_profile_state | ✅ `john-doe → CONNECTED` |
| Browser crash | `daemon.py` exception handler | 🔴 `Browser crash` + screenshot |
| LLM error | `daemon.py` ModelHTTPError | ⚠️ `OpenRouter 429 — task failed` |
| Cookie expired | `browser/session.py` auth check | 🔑 `Login expired — manual 2FA needed` |
| Daily digest | Django command `send_daily_report` (cron 20:00 VN) | 📊 Funnel summary |

**Daily Digest content:**
- Connects: sent / accepted / pending total
- Follow-up: messages sent / replies received
- Leads: new discovered / qualified / disqualified
- Hot leads (replied today, chưa xử lý)
- LLM calls count + estimated cost
- Account health: acceptance rate 7d, pending count
- **💬 Drill-down tin nhắn đã gửi hôm nay:** Danh sách chi tiết các tin nhắn Agent đã gửi trong ngày (tên lead, thời gian gửi, và nội dung tin nhắn cụ thể) giúp bạn kiểm duyệt trực quan văn phong của Agent mà không cần mở LinkedIn.

**Files cần tạo/sửa:**
- `[NEW]` `linkedin/notifications.py` — core module
- `[NEW]` `linkedin/management/commands/send_daily_report.py`
- `[MODIFY]` `linkedin/daemon.py` — hook notify vào exception handlers
- `[MODIFY]` `linkedin/db/chat.py` — hook notify khi sync incoming message
- `[MODIFY]` `linkedin/db/deals.py` — hook notify khi state change
- `[MODIFY]` `.env.example` — TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

**Verification:**

*Automated Tests (`tests/test_notifications.py`):*
- Mock `httpx.post` → verify payload: chat_id, HTML text format, photo binary
- Test `call_command('send_daily_report')` với mock DB → verify query correctness

*Manual Verification:*
- Setup test bot → `python manage.py send_daily_report` → check Telegram message format
- Kill Chrome process → verify crash alert arrives < 60s with screenshot

**Effort:** ~3-4 ngày

---

### Phase 2: Self-healing & Browser Recovery — "Không chết vì crash"

**Mục tiêu:** Browser crash = auto-retry, không phải FAILED ngay lập tức.

**Hiện trạng mã nguồn:**
- `linkedin/diagnostics.py` có `failure_diagnostics` context manager — chụp screenshot + save HTML khi lỗi, rồi **raise lên**
- `daemon.py` (line 339): catch Exception → `task.mark_failed()` → `continue` — **không retry**
- `reconcile()` sẽ tạo lại task ở idle cycle tiếp theo, nhưng Chrome có thể vẫn dead

**Thiết kế:**

Sửa `daemon.py` task execution loop:
```python
MAX_BROWSER_RETRIES = 2
RETRYABLE_ERRORS = (TargetClosedError, TimeoutError, BrowserError)

for attempt in range(MAX_BROWSER_RETRIES + 1):
    try:
        with failure_diagnostics(session):
            handler(task, session, qualifiers)
        break  # success
    except RETRYABLE_ERRORS as e:
        if attempt < MAX_BROWSER_RETRIES:
            logger.warning("Browser error (attempt %d/%d), recovering...",
                          attempt + 1, MAX_BROWSER_RETRIES)
            session.close()
            session.ensure_browser()
            continue
        else:
            screenshot = capture_last_screenshot(session)
            notify("browser_crash", error=str(e), screenshot=screenshot)
            task.mark_failed()
```

**Browser health check:** Trước `claim_next()`, kiểm tra `session.page` còn responsive:
```python
def is_alive(self) -> bool:
    """Check if browser page is still responsive."""
    if self.page is None:
        return False
    try:
        self.page.evaluate("1 + 1")
        return True
    except Exception:
        return False
```

**Files cần sửa:**
- `[MODIFY]` `linkedin/daemon.py` — retry logic + health check
- `[MODIFY]` `linkedin/browser/session.py` — `is_alive()` method

**Verification:**

*Automated Tests:*
- Mock `TargetClosedError` → verify retry 2 lần → verify `session.close()` + `ensure_browser()` called
- Mock lỗi 3 lần liên tục → verify `task.mark_failed()` + `notify()` called

*Manual Verification:*
- Daemon đang chạy → `pkill chrome` → observe: browser recovers + task retries
- Verify Telegram alert nếu retry exhausted

**Effort:** ~2-3 ngày

---

### Phase 3: Conversation Intelligence — Intent + Situation

**Mục tiêu:** Agent báo cáo bối cảnh, hệ thống biết khi nào cần escalate cho human.

**Hiện trạng mã nguồn:**
- `FollowUpDecision` chỉ có: `action`, `message`, `outcome`, `follow_up_hours`
- Không phân biệt lead "đang hứng thú" vs "đang report bug" vs "im lặng"
- Không có cơ chế escalate cho human

**Thiết kế:**

Mở rộng `FollowUpDecision`:
```python
class FollowUpDecision(BaseModel):
    action: Literal["send_message", "mark_completed", "wait"]
    message: str | None = None
    outcome: Literal[...] | None = None
    follow_up_hours: float

    # MỚI
    intent: Literal["high", "medium", "low"] = Field(
        description="high=wants demo/call/trial, medium=interested, low=no signal"
    )
    situation: Literal[
        "engaging",     # tích cực hỏi/trả lời
        "curious",      # tò mò nhưng chưa commit
        "needs_human",  # báo bug, yêu cầu người thật, AI không handle được
        "objecting",    # concern/phản đối cụ thể
        "cold",         # im lặng hoặc reply không thực chất
    ] = Field(
        description="Current conversation dynamic — determines who handles next"
    )
```

**Thêm state `ESCALATED`** vào ProfileState:
```
CONNECTED → ESCALATED (intent=high hoặc situation=needs_human)
ESCALATED → CONNECTED (admin resume via Telegram/Django Admin)
```

**Escalation logic** trong `tasks/follow_up.py`:
```python
if decision.intent == "high" or decision.situation == "needs_human":
    set_profile_state(deal, ProfileState.ESCALATED)
    notify("escalation", deal=deal, intent=decision.intent, 
           situation=decision.situation, last_message=...)
    # Nếu action=send_message, vẫn gửi message đó (bridge message)
    # nhưng không schedule follow-up task tiếp
```

**Sửa prompt** `follow_up_agent.j2`:
```
## Classification
For every response, also classify:
- **intent**: high (wants demo/call/trial), medium (interested), low (no signal)
- **situation**: engaging, curious, needs_human, objecting, cold

If situation=needs_human: your message should acknowledge and bridge to the 
human team. Do not try to handle bugs, technical issues, or meeting requests yourself.
```

**Telegram escalation format:**
```
🔥 [Agency] HIGH INTENT — john-doe

Intent: high | Situation: engaging
Last: "This looks great, can we do a quick call this week?"

[📱 Open Chat]  [⏸️ Keep Paused]  [▶️ Resume AI]
```

**Files cần tạo/sửa:**
- `[MODIFY]` `linkedin/agents/follow_up.py` — thêm intent + situation fields
- `[MODIFY]` `linkedin/templates/prompts/follow_up_agent.j2` — classification instructions
- `[MODIFY]` `linkedin/tasks/follow_up.py` — escalation logic
- `[MODIFY]` `linkedin/enums.py` — thêm ESCALATED state
- `[MODIFY]` `linkedin/db/deals.py` — handle ESCALATED transitions
- `[NEW]` DB migration

**Verification:**

*Automated Tests:*
- Fixture "Can we hop on a call?" → verify intent=high, situation=engaging
- Fixture "The code didn't work" → verify situation=needs_human
- Fixture "Thanks, will check" → verify intent=low, situation=curious
- Verify intent=high → Deal.state = ESCALATED + notify called

*Manual Verification:*
- Test account gửi "I'd love a demo" → verify Telegram 🔥 alert + deal paused
- Resume via Telegram → verify AI re-engages

**Effort:** ~3 ngày

---

### Phase 4: Approval Gate + Agent Feedback Loop — "Kiểm soát chất lượng"

**Mục tiêu:** Review message trước khi gửi + AI học từ corrections.

**Thiết kế — Approval Gate:**

Thêm field vào Campaign:
```python
class Campaign(models.Model):
    approval_mode = models.CharField(max_length=20, choices=[
        ("auto", "Auto — AI gửi tự do"),
        ("first_touch", "First Touch — Approve message đầu tiên mỗi lead"),
        ("high_intent", "High Intent — Approve khi intent ≥ medium hoặc needs_human"),
        ("all", "All — Approve mọi message"),
    ], default="auto")
```

**Logic:**
```python
def should_require_approval(deal, decision) -> bool:
    mode = deal.campaign.approval_mode
    if mode == "auto": return False
    if mode == "all": return True
    if mode == "first_touch":
        return not has_outgoing_messages(deal)
    if mode == "high_intent":
        return decision.intent in ("high", "medium") or decision.situation == "needs_human"
```

Khi cần approval:
1. Lưu `PendingMessage` (deal FK, message_text, decision JSON)
2. Deal → `WAITING_APPROVAL`
3. Telegram inline keyboard: `[✅ Send] [✏️ Edit] [🚫 Skip]`
4. Webhook endpoint nhận callback → execute

**Thiết kế — Feedback Loop:**

Model:
```python
class AgentFeedback(models.Model):
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE)
    original_message = models.TextField()
    corrected_message = models.TextField(blank=True)
    feedback_type = models.CharField(choices=[
        ("approved", "Approved"), ("edited", "Edited"), ("rejected", "Rejected"),
    ])
    created_at = models.DateTimeField(auto_now_add=True)
```

Inject 5 most recent `feedback_type="edited"` corrections (same campaign) vào prompt:
```jinja2
{% if recent_corrections %}
## Style Corrections (learn from these)
{% for fb in recent_corrections %}
- Original: "{{ fb.original_message }}"
  Corrected: "{{ fb.corrected_message }}"
{% endfor %}
{% endif %}
```

**Files cần tạo/sửa:**
- `[MODIFY]` `linkedin/models.py` — PendingMessage, AgentFeedback models, approval_mode trên Campaign, WAITING_APPROVAL state
- `[MODIFY]` `linkedin/tasks/follow_up.py` — approval check + pending save
- `[MODIFY]` `linkedin/agents/follow_up.py` — inject corrections
- `[MODIFY]` `linkedin/templates/prompts/follow_up_agent.j2` — corrections section
- `[NEW]` `linkedin/api/telegram_webhook.py` — webhook endpoint
- `[MODIFY]` `linkedin/urls.py` — webhook route
- `[NEW]` DB migration

**Verification:**

*Automated Tests:*
- Campaign `first_touch` → first message → verify WAITING_APPROVAL + notify
- Same deal, second message → verify auto-send
- Mock callback "approved" → verify sent + state restored
- Mock callback "edited" → verify AgentFeedback created + corrected version sent
- Verify corrections appear in rendered prompt

*Manual Verification:*
- first_touch campaign → run follow_up → Telegram inline keyboard appears
- Edit message → verify corrected version sent
- Next message same lead → auto-sent (no prompt)

**Effort:** ~4-5 ngày

---

### Phase 5: Link Tracking — "Đo lường engagement"

**Mục tiêu:** Biết lead nào click audit link.

**Thiết kế:**

Model:
```python
class ClickEvent(models.Model):
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE)
    short_code = models.CharField(max_length=12, unique=True, db_index=True)
    destination_url = models.URLField()
    clicked_at = models.DateTimeField(null=True)
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

Redirect view:
```python
def redirect_click(request, short_code):
    click = get_object_or_404(ClickEvent, short_code=short_code)
    click.clicked_at = timezone.now()
    click.ip_address = get_client_ip(request)
    click.user_agent = request.META.get("HTTP_USER_AGENT", "")
    click.save()
    notify("link_clicked", deal=click.deal)
    return HttpResponseRedirect(click.destination_url)
```

Helper thay URL trong message trước khi gửi:
```python
def trackify_message(message: str, deal: Deal) -> str:
    booking = deal.campaign.booking_link
    if not booking or booking not in message:
        return message
    click = ClickEvent.objects.create(
        deal=deal, short_code=generate_short_code(), destination_url=booking)
    return message.replace(booking, f"{TRACKING_BASE_URL}/r/{click.short_code}/")
```

**Config:** `TRACKING_BASE_URL` trong `.env`.

**Files cần tạo/sửa:**
- `[NEW]` `linkedin/tracking.py` — ClickEvent model, trackify helper, generate_short_code
- `[NEW]` `linkedin/views.py` — redirect view
- `[MODIFY]` `linkedin/urls.py` — `/r/<short_code>/` route
- `[MODIFY]` `linkedin/tasks/follow_up.py` — call trackify_message before send
- `[NEW]` DB migration

**Verification:**

*Automated Tests:*
- trackify_message replaces booking_link → `/r/<code>/`
- GET `/r/<code>/` → 302 + ClickEvent.clicked_at updated + notify called
- Message without booking_link → unchanged

*Manual Verification:*
- TRACKING_BASE_URL → send test → click link → verify redirect + Telegram alert

**Effort:** ~2-3 ngày

---

### Phase 6: Account Safety — "Tự bảo vệ"

**Mục tiêu:** Bảo vệ account proactively.

**3 components:**

#### 6A. Auto-withdraw Old Invites
- Weekly task: navigate `mynetwork/invitation-manager/sent/` → withdraw > 21 ngày
- Max 10 withdrawals/batch, delays 3-5s giữa clicks
- Scheduler: 1 lần/tuần

#### 6B. Health Monitor
- Mỗi ngày compute: acceptance rate 7d, pending count, reply rate
- Include trong daily digest (Phase 1)
- Alert nếu metrics vượt threshold

#### 6C. Auto-throttle (MỚI)
```python
def auto_throttle_check(profile):
    rate_7d = compute_acceptance_rate_7d(profile)
    original_limit = 12

    if rate_7d < 0.15:
        new_limit = max(5, profile.connect_daily_limit // 2)
        profile.connect_daily_limit = new_limit
        profile.save()
        notify("auto_throttle", rate=rate_7d, new_limit=new_limit, severity="warning")
    elif rate_7d > 0.30 and profile.connect_daily_limit < original_limit:
        new_limit = min(original_limit, profile.connect_daily_limit + 2)
        profile.connect_daily_limit = new_limit
        profile.save()
        notify("auto_throttle", rate=rate_7d, new_limit=new_limit, severity="info")
```

**Files cần tạo/sửa:**
- `[NEW]` `linkedin/actions/withdraw.py` — withdraw action
- `[NEW]` `linkedin/safety.py` — auto_throttle + health metrics
- `[MODIFY]` `linkedin/tasks/scheduler.py` — schedule weekly withdraw
- `[MODIFY]` `linkedin/daemon.py` — call auto_throttle_check daily

**Verification:**

*Automated Tests:*
- Mock acceptance rate < 15% → verify limit halved + notify
- Mock rate > 30% → verify limit restored gradually
- Withdraw: mock HTML invite page → verify correct invites selected

*Manual Verification:*
- VNC: observe withdraw clicking correct buttons
- Set rate threshold → verify throttle kicks in + Telegram alert

**Effort:** ~3-4 ngày

---

### Phase 7: Content Automation — "Warm up trước khi cold DM"

**Mục tiêu:** Tăng profile visibility + SSI trước/song song với outreach.

**Tại sao cần:** 
* SSI "Engage with insights" = 0.7/25 → profile trông như ghost → low acceptance rate.
* **Tài liệu tham khảo & Phân tích:** Xem thêm [Nghiên cứu Case Study Chris Donnelly về Personal Brand](file:///Users/gn/Documents/Gnoc/Github/Stelixx%20CDP/OpenOutreach/_docs/research_donnellychris_personal_brand.md) để áp dụng nguyên lý 5 trụ cột thương hiệu và hệ thống inbound leads tự động vào thiết kế prompt sinh bài viết tự động (Post Scheduler).

**3 lớp:**

#### 7A. Auto-engage (Low risk)
- Daemon scan feed → like/react 10-15 posts/ngày từ SEO/GEO niche
- Ưu tiên posts từ leads trong pipeline (warm up trước connect request)
- Voyager API endpoint cho reactions

#### 7B. Comment Assistant (Semi-auto)
- AI draft 1-2 sentence comments trên relevant posts
- Queue vào `PendingComment` → Telegram approve → bot posts
- Target: 3-5 comments/ngày

#### 7C. Post Scheduler (Manual-heavy)
- AI draft posts từ Geolify insights
- Schedule qua Django Admin → daemon auto-post
- Target: 2-3 posts/tuần

**Warm outreach workflow:**
```
Day 1-3: Like/react posts của target lead
Day 2-4: Comment 1-2 posts
Day 5:   Connection request → lead đã thấy tên → "warm" connection
```

**Files cần tạo:**
- `[NEW]` `linkedin/content/engage.py` — auto-like, feed scanning
- `[NEW]` `linkedin/content/comments.py` — comment drafting + posting
- `[NEW]` `linkedin/content/posts.py` — post scheduling
- `[NEW]` `linkedin/content/models.py` — PendingComment, ScheduledPost
- `[MODIFY]` `linkedin/daemon.py` — integrate content into loop

**Effort:** ~5-7 ngày

---

### Phase 8: Reddit Presence — "Kênh GTM thứ 2"

**Mục tiêu:** Organic presence trên Reddit, capture inbound.

**Approach: Content-driven ONLY — không auto-DM, không spam.**

#### 8A. Monitor + Alert
- Reddit API polling (OAuth) — keywords: "GEO", "AI search visibility", "ChatGPT SEO"
- Subreddits: r/SEO, r/bigseo, r/digital_marketing, r/SaaS
- Telegram alert khi relevant thread found

#### 8B. Reply Assistant
- AI draft replies → bạn review + post THỦ CÔNG
- Focus: answer genuinely, mention Geolify khi naturally relevant

**Files cần tạo:**
- `[NEW]` `reddit/` Django app
- `[NEW]` `reddit/monitor.py`, `reddit/suggest.py`, `reddit/models.py`
- `[NEW]` `reddit/management/commands/reddit_monitor.py`

**Effort:** ~5-7 ngày

---

### Phase 9: Multi-account Support

**Mục tiêu:** Scale bằng nhiều LinkedIn accounts.

- Daemon round-robin qua multiple active LinkedInProfile objects
- Mỗi account browser context riêng
- Per-account rate limiting (đã có)

**Files:** `linkedin/daemon.py`, `linkedin/browser/session.py`, `linkedin/browser/registry.py`

**Effort:** ~3-5 ngày

---

### Phase 10: Stelixx CDP Integration

**Mục tiêu:** 2-way data sync.

- **Outbound:** Webhook push events (deal state, messages) → HMAC-SHA256 signed
- **Inbound:** CSV import LinkedIn URLs via Django Admin

**Files:** `[NEW]` `linkedin/webhook.py`, `[MODIFY]` `linkedin/admin.py`, `.env.example`

**Verification:**
- Webhook.site → change deal → verify payload + signature
- Django Admin → upload CSV 5 URLs → verify 5 Leads + 5 Deals, no duplicates

**Effort:** ~4-5 ngày

---

## Phần III: Tổng hợp

### Effort & Timeline

| Phase | Effort | Tầng |
|-------|--------|------|
| 1. Telegram Notifications | 3-4d | Nhìn Thấy |
| 2. Self-healing | 2-3d | Nhìn Thấy |
| 3. Intent + Situation | 3d | Nhìn Thấy |
| 4. Approval Gate + Feedback | 4-5d | Kiểm Soát |
| 5. Link Tracking | 2-3d | Kiểm Soát |
| 6. Account Safety | 3-4d | Kiểm Soát |
| 7. Content Automation | 5-7d | Mở Rộng |
| 8. Reddit Presence | 5-7d | Mở Rộng |
| 9. Multi-account | 3-5d | Mở Rộng |
| 10. CDP Integration | 4-5d | Mở Rộng |
| **Tổng** | **~35-46 ngày** | |

### Go/No-Go Gates

```
Start: Quick Wins (booking_link, seeds, campaign_objective)
  ↓
Phase 1-3 (Tầng 1)
  ↓
Gate 1: Pilot 1 tuần ổn? Acceptance ≥ 15%?
  → Yes: Phase 4-6 (Tầng 2)
  → No:  Debug ICP, message quality, profile
  ↓
Gate 2: Reply rate ≥ 10%? CTR ≥ 5%?
  → Yes: Phase 7-10 (Tầng 3)
  → No:  Iterate prompt, corrections, throttle
```

### Những gì KHÔNG làm

| Item | Lý do |
|------|-------|
| Smart Active Hours (timezone) | Agent tự quyết pace. Impact < 5%. |
| Connection request với note | No-note ≥ templated notes (data proven). |
| LLM fine-tuning | In-context learning đủ cho 1-account scale. |
| Dashboard web riêng | Telegram digest + Django Admin đủ. |
| Dub.co integration | Local redirect đủ đơn giản. |
| A/B testing framework | 12 connects/day quá nhỏ cho statistical significance. |
