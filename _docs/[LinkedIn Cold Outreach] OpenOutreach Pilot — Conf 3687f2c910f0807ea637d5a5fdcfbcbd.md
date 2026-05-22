# [LinkedIn Cold Outreach] OpenOutreach Pilot — Config & Plan

<aside>
📌

**Status:** Active pilot — OpenOutreach daemon self-hosted on Japan VPS (16GB RAM), account `nv-cong` (LinkedIn Premium Career), 2 campaigns parallel (Agency + Solopreneur)

**Updated:** 2026-05-22

**Owner:** @Gnoc Ng

</aside>

## 1. TL;DR

- **Tool:** self-hosted OpenOutreach (Docker), GPLv3, repo active
- **Account:** Cong Premium Career, SSI **38/100** (industry avg 42 — dưới trung bình)
- **LLM:** `openai/gpt-oss-120b:free` qua OpenRouter — **cần nạp $10 credits** để unlock 1000 req/day (default 50/day không đủ)
- **Config:** Conservative — 12 connects/day, 70/week
- **2 campaigns song song:** Agency Track 5-20 (primary) + Solopreneur Track (73% production data)
- **Đã có 2 cold outreach manual baseline:** Duy ✅ (warmed → whitelist), Laurent ⚠️ (product bug killed momentum)

---

## 2. OpenOutreach — Tóm tắt nhanh

Self-hosted LinkedIn automation daemon (Python + Playwright stealth + Voyager API + Django CRM). 1.8k★, GPLv3, repo active push hôm nay.

**Differentiator:** KHÔNG cần leads list. Cấp 3 input → AI tự discover + qualify + connect + follow-up.

**Pipeline:**

```
Discovery → Enrichment (Voyager API + FastEmbed 384-dim)
         → QUALIFIED (LLM decision)
         → READY_TO_CONNECT (GP gate p>0.9)
         → PENDING (sent, no note)
         → CONNECTED (accepted)
         → COMPLETED (follow-up agent done)
```

**ML core:** Gaussian Process Regressor + BALD active learning. Explore (high BALD) khi balanced; exploit (high P) khi negatives > positives. LLM luôn là quyết định cuối — GP chỉ chọn candidate nào để query LLM.

**3 task types:** `connect` (per-campaign, ML-ranked), `check_pending` (per-profile, exponential backoff), `follow_up` (per-profile, agentic DM).

**Monitor live:** noVNC ở `localhost:6080/vnc.html` (xem browser chạy real-time).

**Risks:** LinkedIn ToS (use at own risk), GPLv3 copyleft (chỉ self-host OK, fork-and-distribute phải open source), Voyager API có thể breaking changes.

---

## 3. SSI Score Analysis

![Update: 22 May 2026 - [https://www.linkedin.com/in/nv-cong/](https://www.linkedin.com/in/nv-cong/)](%5BLinkedIn%20Cold%20Outreach%5D%20OpenOutreach%20Pilot%20%E2%80%94%20Conf/image.png)

Update: 22 May 2026 - [https://www.linkedin.com/in/nv-cong/](https://www.linkedin.com/in/nv-cong/)

**Current:** 38/100 (industry top 63%, network top 65%). Industry avg = 42 → Cong đang **dưới trung bình ngành VC/PE Principals**.

| Pillar | Score (/25) | % pillar | Note |
| --- | --- | --- | --- |
| Establish professional brand | 6.93 | 28% | Cần update headline, banner, featured |
| Find the right people | 6.1 | 24% | Search & save leads nhiều hơn |
| **Engage with insights** | **0.7** | **2.8%** | ⚠️ Pillar yếu nhất — ít post/comment |
| Build relationships | 24.348 | 97% | Pillar mạnh nhất — network tốt |

**Implication for automation:**

- SSI 38 nằm vùng "average-to-low" → LinkedIn có thể apply rate limit chặt hơn account high-SSI
- "Engage with insights" 0.7/25 → profile gần như zero content engagement. Khi daemon push lots of connects mà profile không post/comment → pattern bất thường → flag risk cao

**Action — Boost SSI parallel với pilot:**

- [ ]  Post 2-3x/tuần (text post hoặc carousel — không cần video)
- [ ]  Comment thoughtfully 5-10 posts/ngày trong GEO/SEO/AI marketing niche
- [ ]  Like/react on connected people's posts daily
- [ ]  Update profile: headline tag ("Founder @ Geolify — Audit. Fix. Track. AI Search Visibility"), banner, featured section với link GEO Audit
- [ ]  Save 20-30 leads vào saved list để boost "Find right people"

**Target after 30 ngày pilot:** SSI 50+ (từ 38). Mỗi +5 SSI = +5-10% acceptance rate.

---

## 4. LinkedIn Premium Career — Verified Limits (2026)

Verified cross-check từ multiple sources (Hasam 2026, Wandify, LinkedHelper, Dux-Soup, official LinkedIn Help).

| Metric | Free safe | Premium safe (Cong) | **Cong's pilot target** |
| --- | --- | --- | --- |
| Connection requests/week | 60-80 | 80-100 | **70** (conservative — 30% buffer) |
| Messages (1st degree)/week | 80-100 | 120-150 | 60 (follow-ups) |
| Profile views/day | 200-250 | 800-1000 | ~100 (auto-discover scrape) |
| Connection note chars | 200 | **300** (Premium perk) | N/A (OpenOutreach gửi no-note) |
| InMail credits/month | 0 | 5 (Career plan) | Reserve cho hot leads |
| Search results/query | 1000 | 1000 | — |
| Easy Apply | 50/day | 50/day | — |

<aside>
⚠️

**Myth alert:** Premium **KHÔNG tăng** connection request limit. Cap vẫn ~100/week reputation-based. Premium chỉ tăng InMail, search filters, profile views, message char limit.

</aside>

**Restriction windows:**

- First restriction: 3-7 ngày (typically 7)
- Repeated: manual review, có thể giảm reach permanent
- Triggers: burst behavior (100+ trong 1 day), pending invites > 500, low acceptance rate, automation tool detection

---

## 5. OpenRouter LLM volume analysis (clarified)

<aside>
📊

**Source clarification:** "212 requests/3h" là từ **OpenRouter Activity dashboard** (`openrouter.ai/activity`), KHÔNG phải OpenOutreach admin. Snapshot 2026-05-22: **301 requests / 1.42M tokens / $0 spend** trong Past 1 Day, tất cả vào `gpt-oss-120b`.

</aside>

### 5.1 Tại sao số cao — decomposition

| Action | LLM calls/action | Why |
| --- | --- | --- |
| **Qualification** (per profile) | **~100** | `qualification_n_mc_samples: 100` — Monte Carlo sampling cho BALD active learning |
| Search keyword gen (per campaign) | 1-5 | Sinh search seeds từ objective |
| Follow-up agent (per pending DM) | 1-3 | Agentic decide → generate |
| Embedding | 0 | FastEmbed local, không qua OpenRouter |

**Quy ngược 301 LLM calls/3h:** ~3 profile qualifications (100 calls/qual) + vai search/follow-up calls. Normal cho cold-start phase.

### 5.2 ⚠️ Free tier capacity — bổ sung cảnh báo quan trọng

<aside>
⚠️

**OpenRouter `:free` rate limits:**

- 20 req/min (hard cap)
- **50 req/day nếu lifetime credits < $10**
- **1000 req/day nếu lifetime credits ≥ $10**

Bạn đã có 301 req/day thành công → hoặc đã nạp ≥ $10, hoặc gpt-oss-120b:free có cap riêng. **Cần verify tại `openrouter.ai/credits`.**

</aside>

**Projection cho từng phase:**

| Phase | Connects/day | ~Profiles qualified/day | LLM calls/day | Free 1000/day OK? |
| --- | --- | --- | --- | --- |
| Phase 0 (warmup) | 5 | ~5-8 (explore-heavy) | 500-800 | ✅ OK |
| Phase 1 (ramp) | 8 | ~10-15 | 1000-1500 | ⚠️ Borderline |
| Phase 2-3 (steady) | 12 | ~15-25 | 1500-2500 | ❌ **Sẽ hit cap** |

### 5.3 Mitigation — 3 options

**🎯 Option A — Reduce `qualification_n_mc_samples: 100 → 30` (RECOMMENDED trước Phase 0)**

- Edit `linkedin/conf.py` trong fork
- Variance estimate vẫn ok (std error reduction 5.5x vs 100=10x). Cold-start phase (<50 labels) không cần high precision.
- **LLM volume giảm 70%** → Phase 2-3 vẫn dưới 1000/day cap
- Zero cost

**💰 Option B — Switch sang paid `openai/gpt-oss-120b` (bỏ `:free` suffix)**

- Same model, no rate cap, $0.09 input + $0.45 output / 1M tokens
- 1.42M tokens/day × 30 × ~$0.27 blended ≈ **~$11-12/month**
- Reliable, no daily cap worry

**🔬 Option C — Combine A + B (Phase 2+ if needed)**

- Start với Option A (reduce MC samples) cho Phase 0-1
- Nếu Phase 2 vẫn hit cap → switch sang paid (Option B)
- Best risk-adjusted path

### 5.4 OpenOutreach admin vs OpenRouter — hai dashboards khác nhau

| Dashboard | Đo cái gì | URL |
| --- | --- | --- |
| **OpenRouter Activity** | LLM API calls (qualification + follow-up + search gen) | `openrouter.ai/activity` |
| **OpenOutreach Django Admin** | LinkedIn actions thực (connect / message / view) | `localhost:8000/admin/` |
| **LinkedIn UI** | Account health, pending invites, acceptance | `linkedin.com/mynetwork/...` |

**3 metrics phải track parallel mỗi ngày:**

1. OpenRouter: LLM calls/day (watch 1000 cap)
2. Django Admin ActionLog: actual connect count (watch 12/day cap)
3. LinkedIn UI: pending invites + acceptance rate

---

## 6. Config Spec — Final

### 6.1 `.env` file

```bash
LLM_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx
AI_MODEL=openai/gpt-oss-120b:free
LLM_API_BASE=https://openrouter.ai/api/v1
```

<aside>
💡

**LLM strategy:** Nạp **$10 OpenRouter credits trước khi run** → unlock 1000 req/day free tier. Default tier chỉ 50 req/day → KHÔNG ĐỦ vì OpenOutreach 1 ngày tốn ~30-50 LLM calls (qualify + search keywords + follow-up).

**Fallback nếu free tier unstable:** chuyển sang paid `openai/gpt-oss-120b` (~$0.09/$0.45 per 1M tokens), ước tính $3-8/mo.

</aside>

### 6.2 LinkedInProfile model (Django Admin sau khi setup)

| Field | Value | Reasoning |
| --- | --- | --- |
| `linkedin_username` | Cong's LinkedIn email |  |
| `linkedin_password` | (password) |  |
| `active` | `true` |  |
| `subscribe_newsletter` | **`false`** | VN = non-GDPR → daemon auto-set true; phải override = false |
| `connect_daily_limit` | **12** | 12 × 5 working days = 60/week (15% headroom dưới target 70) |
| `connect_weekly_limit` | **70** | 30% buffer dưới LinkedIn cap 100, an toàn cho SSI 38 |
| `follow_up_daily_limit` | **20** | Conservative cho DM nurture |
| `legal_accepted` | `true` | Sau khi đọc LEGAL_[NOTICE.md](http://NOTICE.md) |

### 6.3 `conf.py` — KEEP defaults (đã calibrated cẩn thận)

<aside>
✋

**Đính chính:** Mình rút lại đề xuất trước về "shorter bursts". Đọc kỹ comment trong code thì `2700/3900` (45-65 min) là intentional human-rhythm calibration. Random uniform tạo natural variance. Shorter bursts → pattern quá đều → DỄ detect hơn. **GIỮ defaults.**

</aside>

**KEEP nguyên (do NOT modify):**

- `burst_min_seconds: 2700` (45 min)
- `burst_max_seconds: 3900` (65 min)
- `break_min_seconds: 600` (10 min)
- `break_max_seconds: 1200` (20 min)
- `min_ready_to_connect_prob: 0.9`
- `connect_delay_seconds: 10`
- `check_pending_recheck_after_hours: 24`

**Optional overrides (chỉ nếu muốn extra-safe cho SSI 38):**

- `enrich_min_delay_seconds: 6 → 8`
- `enrich_max_delay_seconds: 10 → 15`
- `enrich_max_per_page: 10 → 6`
- `min_action_interval: 120 → 180`

### 6.4 Active hours (RECOMMENDED ON)

```python
ENABLE_ACTIVE_HOURS = True
ACTIVE_START_HOUR = 9   # 9 AM
ACTIVE_END_HOUR = 19    # 7 PM (10-hour window)
ACTIVE_TIMEZONE = "Asia/Ho_Chi_Minh"  # VN time, không phải JP time của VPS
REST_DAYS = (5, 6)      # Sat + Sun off
```

**Lý do:** Daemon chỉ chạy giờ work VN → match Cong's natural pattern. VPS Nhật UTC+9, VN UTC+7 — lệch 2h, nên phải set explicit timezone.

### 6.5 Campaign field reference — 8 fields, mỗi field ảnh hưởng khác nhau

Từ code (`linkedin/models.py`, `architecture.md`, `CLAUDE.md` + 3 prompt templates `qualification.j2`, `search_keywords.j2`, `follow_up_agent.j2`):

| Field | Type | Ảnh hưởng đến | Cong cần làm gì |
| --- | --- | --- | --- |
| **`name`** | CharField unique | Display name trong Admin + ActionLog | Rõ ràng, không "test" — vd: `GEO Audit — Agency Track` |
| **`users`** | M2M to User | LinkedIn accounts chạy campaign này. `AccountSession.campaigns` = campaigns where user is in M2M | Add `congnv` vào cả 2 campaigns |
| **`product_docs`** | TextField | ⚡ **INJECTED VERBATIM** vào 3 LLM prompts: qualification, search_keywords, follow_up_agent. Quality = quality of qualification + DMs | Viết EN-only, structured spec (không paste wiki bilingual). 300-500 words optimal |
| **`campaign_objective`** | TextField | ⚡ **INJECTED VERBATIM** vào cả 3 prompts — đây là ICP/targeting spec. LLM dùng để (1) generate search keywords (2) qualify yes/no (3) decide follow-up strategy | **KHÔNG được thiếu:** roles, company size, pain points, search angles, exclude criteria |
| **`booking_link`** | URLField | Conditional trong `follow_up_agent.j2`: `{% if booking_link %}...{% endif %}`. KHÔNG có → agent không pitch CTA cuối conversation | **ĐIỀN VÀO** — hiện đang EMPTY → lose conversion driver |
| **`is_freemium`** | BooleanField | Switch pipeline: `False` = `pipeline/pools.py` (per-campaign BayesianQualifier GP+BALD). `True` = `pipeline/freemium_pool.py`  • `KitQualifier` (pre-trained model từ HuggingFace `eracle/campaign-kit`) | **Để `False` cho Geolify** — dù product có free tier, field này không nhắc tới pricing mà chỉ về qualifier type. Geolify cần custom learning từ labels của Cong |
| **`action_fraction`** | FloatField (default 0.2) | Probabilistic gating giữa Partner campaigns và Regular campaigns. 0.2 = 20% connect attempts allocated to partner | Leave **0.2 default** — cả 2 campaigns của Cong đều Regular (non-partner) |
| **`seed_public_ids`** | JSONField (list of strings) | LinkedIn public IDs để seed discovery. Daemon visit những profile này → phát hiện network liên quan | **Quan trọng:** add Duy (`duydudjob`) + 5-10 ideal customer IDs. Empty = bỏ lỡ warm-start signal |

<aside>
⚠️

**Gỡ ngay 4 issues từ screenshot "LinkedIn Outreach test":**

1. `name="LinkedIn Outreach test"` → đổi sang `GEO Audit — Agency Track` (production-ready name)
2. `product_docs` = wiki bilingual paste → viết lạ bằng EN, structured. Wiki content có markdown header + VN comments → LLM context noise.
3. `campaign_objective` = `"sell Geolify.ai platform to primary ICP (agencies)"` → quá mỏng. LLM không biết search keywords phải sinh ra là gì, qualify tiêu chí nào, follow-up hướng đâu. **Section 6.6/6.7 bên dưới có full spec.**
4. `booking_link` = EMPTY → follow_up agent sẽ không pitch CTA. ĐIỀN: `https://geolify.ai/geo-ai-visibility-audit`
5. `seed_public_ids` = `[]` → mất warm-start. Add ID của Duy + 5-10 ideal customers phải thu thập trước Phase 0.
</aside>

### 6.6 Campaign A — Agency Track (Primary ICP) — FULL SPEC

<aside>
📋

Paste từng field theo Django Admin form (`linkedin > Campaigns > Add`). Field nào KHÔNG nhắc tới bên dưới thì giữ default.

</aside>

**`name`** (Field 1)

```
GEO Audit — Agency Track
```

**`users`** (Field 2): Chọn `congnv` từ Available users → Chosen users

**`product_docs`** (Field 3) — EN-only structured spec, KHÔNG paste wiki:

```
Geolify is a Generative Engine Optimization (GEO) platform that helps brands measure and improve how they appear in AI search engines (ChatGPT, Perplexity, Gemini, Google AI Mode, Claude, Copilot, Microsoft Copilot, AI Overviews).

WHAT WE DO:
- Free GEO Audit tool generates a GEO Score (0-100) for any website in under 2 minutes
- The Score breaks down into 6 pillars: technical accessibility (can AI bots crawl?), content semantics (is content structured for AI extraction?), structured data (Schema.org coverage), entity authority (is the brand a recognized entity?), citation signal (is the brand mentioned in AI training sources?), AI engine coverage (which of the 7 major AI engines cite this brand?)
- 27 shippable Actions (with 64 more on roadmap) provide specific fixes ranked by impact
- Action Center workspace lets users execute fixes and track score improvements over time
- Prompt Monitoring (beta) alerts when brand visibility changes in specific AI queries

PRICING:
- Free: 1 audit, basic Action Center access
- Starter $29/mo: 5 audits, full action library
- Growth $79/mo: 25 audits, prompt monitoring, weekly reports
- Pro $289/mo: unlimited audits, white-label reports, API access
- Enterprise: custom ($1,800-$7,500/mo)

BRAND VOICE:
- Tagline: "Audit. Fix. Track."
- Hook: "What's your GEO Score?"
- Emotional positioning: "From invisible to cited."
- Tone: technical-but-friendly, data-driven, no hype

DIFFERENTIATORS:
- Free score (no signup wall to see results)
- Action-oriented (not just diagnostics — ships with fixes)
- Covers all 7 major AI engines, not just ChatGPT
- Self-serve PLG — no demo required to get value

TRACTION: 78 signups in 3 weeks, currently free-tier focused, working toward first paid conversions.
```

**`campaign_objective`** (Field 4) — FULL ICP spec cho Agency Track:

```
TARGET: B2B digital marketing agencies, 5-20 employees, that serve SaaS / DTC / professional services clients.

DECISION-MAKER ROLES (in order of priority):
1. Founder / CEO / Managing Director of agencies <30 people
2. Head of SEO, Head of Content, Head of Strategy
3. Director / VP of SEO, Content, or Digital Marketing
4. Senior SEO Manager / Senior Content Strategist (if agency <10 people)

GEOGRAPHIC FOCUS: English-speaking markets first (US, UK, AU, CA, IE, NZ), then EU-EN (NL, DE, SE, FR). Skip non-English markets unless profile is in English.

WHY THEY CARE (pain points to surface in qualification + DMs):
- Clients are asking "how do we show up in ChatGPT?" — agencies have no answer
- Traditional SEO tools (Ahrefs, Semrush, Moz) don't measure AI search visibility
- Agencies need to add a GEO/AI-search service line to stay competitive in 2026
- Reporting AI visibility to clients is currently manual / impossible
- Agencies need a way to differentiate proposals from competitors still selling "just SEO"

IDEAL ENGAGEMENT FLOW:
- They accept the connection within 7 days
- They click the GEO Audit link and run an audit on ONE client brand
- They share the score with their client → client asks for ongoing monitoring
- Agency upgrades to Growth ($79) or Pro ($289) to serve multiple clients

QUALIFY YES if profile shows:
- Title contains: SEO, Content, GEO, AEO, Search, Digital Marketing, Growth (with seniority)
- Company is an agency (not in-house) — look for "agency", "consultancy", "studio" in company name or description
- Headcount 2-50 (LinkedIn company size 2-10 or 11-50)
- Posts or interacts with AI / SEO / content marketing topics
- Has 500+ connections (active LinkedIn user)

QUALIFY NO (FAILED Deal with wrong_fit) if profile shows:
- In-house SEO / Content at a single brand (not an agency) — wrong campaign, route to no campaign
- Pure B2C / e-commerce focus (Geolify is B2B-leaning)
- Recruiters, hiring managers, job-seekers, students
- Sales / BDR / SDR titles (not buyer)
- Large agencies 500+ employees (procurement cycle too slow for PLG)
- Solo freelancer with no team — belongs in Campaign B
- Companies with <90 days of LinkedIn activity (fake / dormant)
- Profile language not in English (until i18n is supported)

SEARCH ANGLES (seeds for search_keywords generation):
- "SEO agency founder"
- "Head of SEO agency"
- "Content marketing agency director"
- "GEO consultant"
- "AI search optimization"
- "generative engine optimization"
- "answer engine optimization"
- "SEO consultancy founder"
- "digital marketing agency owner SaaS"
```

**`booking_link`** (Field 5):

```
https://geolify.ai/geo-ai-visibility-audit?utm_source=linkedin&utm_campaign=openoutreach_agency
```

**`is_freemium`** (Field 6): ❌ UNCHECKED — phải dùng BayesianQualifier custom-learning

**`action_fraction`** (Field 7): `0.2` (default — không đổi)

**`seed_public_ids`** (Field 8) — seed với Duy + ideal customers (Cong cần thu thập trước Phase 0):

```json
[
  "duydudjob",
  "PLACEHOLDER-agency-founder-1",
  "PLACEHOLDER-head-of-seo-1",
  "PLACEHOLDER-content-agency-2",
  "PLACEHOLDER-geo-consultant-1"
]
```

<aside>
📌

**Action Cong trước Phase 0:** browse LinkedIn, save 5-10 public IDs (lấy từ URL `linkedin.com/in/<public_id>/`) của agency founders/SEO heads thật sự fit ICP. Paste vào `seed_public_ids` field. Đây là warm-start signal cho discovery.

</aside>

### 6.7 Campaign B — Solopreneur Track (Secondary ICP, 73% production data)

**`name`**:

```
GEO Audit — Solopreneur Track
```

**`users`**: Chọn `congnv`

**`product_docs`**: **Paste cho giống hệt Campaign A** (Section 6.6 Field 3) — product description không đổi theo ICP.

**`campaign_objective`** — FULL ICP spec cho Solopreneur Track:

```
TARGET: Solo SEO consultants, content strategists, indie SaaS founders, content creators, and personal-brand builders — individuals (not agencies) who personally do AI/SEO work.

DECISION-MAKER ROLES (in order of priority):
1. Solo SEO consultant / Freelance SEO
2. Freelance content strategist / Content marketer
3. Indie SaaS founder (1-3 people team) building content-driven distribution
4. Newsletter operator / Content creator who monetizes via paid newsletter or community
5. Personal-brand builder with active LinkedIn / Twitter presence in marketing niche

GEOGRAPHIC FOCUS: English-speaking markets first (US, UK, AU, CA, IE, NZ), then EU-EN. Solo segment is more global — also OK with profiles in IN, PH, ZA if profile + posts are in English.

WHY THEY CARE:
- They sell SEO services and need to add GEO to their offering to stay relevant
- They run their own personal brand and want to know if AI engines mention them
- They're early adopters and love testing new tools — will share results on LinkedIn
- They have small budgets but high decision speed (no procurement, no committee)
- They're vocal on LinkedIn and amplify what they like — word-of-mouth multiplier

IDEAL ENGAGEMENT FLOW:
- Accept connection within 5 days (faster than agencies)
- Run GEO Audit on their own personal site or a client site within 3 days
- Share screenshot of score on LinkedIn (free distribution)
- Upgrade to Starter ($29) within 2 weeks for additional audits

QUALIFY YES if profile shows:
- Title contains: "freelance", "solo", "consultant", "founder" (single-person), "creator", "strategist", "independent"
- Company is "Self-Employed", "Freelance", or a 1-person company they founded
- Posts AI / SEO / content marketing content actively (last 30 days)
- Has a personal site, newsletter, or substack listed in profile
- 1000+ followers and active engagement (likes, comments on their posts)

QUALIFY NO (FAILED Deal with wrong_fit) if profile shows:
- Agency owner with >5 employees — belongs in Campaign A
- In-house at large brand (>100 employees) — wrong pain point
- Pure B2C ecommerce solo (not marketing services)
- Recruiters, coaches selling courses unrelated to marketing
- Profile inactive in last 60 days
- Profile language not in English

SEARCH ANGLES:
- "freelance SEO consultant"
- "solo SEO consultant"
- "freelance content strategist"
- "indie SaaS founder marketing"
- "AI content creator"
- "GEO consultant freelance"
- "personal brand SEO"
- "newsletter operator marketing"
- "content marketing freelancer"
```

**`booking_link`**:

```
https://geolify.ai/geo-ai-visibility-audit?utm_source=linkedin&utm_campaign=openoutreach_solo
```

**`is_freemium`**: ❌ UNCHECKED

**`action_fraction`**: `0.2` (default)

**`seed_public_ids`** — cần thu thập 5-10 solo consultants/creators fit ICP:

```json
[
  "PLACEHOLDER-solo-seo-1",
  "PLACEHOLDER-freelance-content-1",
  "PLACEHOLDER-indie-founder-1",
  "PLACEHOLDER-creator-1"
]
```

### 6.8 Tip pre-launch: thu thập seed_public_ids

Trước khi launch Phase 0, dedicate 30 phút manual research:

1. Từ network hiện có của Cong, identify 10 connections best-fit Campaign A + 10 best-fit Campaign B
2. Lấy `public_id` từ URL profile: `https://linkedin.com/in/<public_id>/`
3. Paste vào `seed_public_ids` field của từng campaign
4. Khi daemon bắt đầu, nó sẽ visit seed profiles trước → discover similar profiles qua "People you may know" + "Other profiles viewed" → cold-start GP model với positive signals strong hơn random search

**Đặc biệt:** Duy (`duydudjob`) đã success-converted → paste vào Campaign A seed giúp GP learn "profile giống Duy = high P(qualify)"

---

## 7. Pre-flight Checklist

### 7.1 OpenRouter setup

- [ ]  Tạo OpenRouter account, lấy API key
- [ ]  **Nạp $10 credits** để unlock 1000 req/day free tier
- [ ]  Test API key với curl: `curl https://openrouter.ai/api/v1/models -H "Authorization: Bearer $KEY"`

### 7.2 LinkedIn account audit (`nv-cong`)

- [ ]  Verify SSI tại `linkedin.com/sales/ssi` (snapshot rồi: 38/100)
- [ ]  Check pending invitations < 500 (xem cách check ở Section 10)
- [ ]  Check recent acceptance rate (xem Section 10)
- [ ]  Logout tất cả device khác (giảm fingerprint mismatch risk)
- [ ]  Tắt 2FA tạm thời (hoặc set app-specific cookies) — Playwright login với 2FA phức tạp
- [ ]  Confirm country code trên profile = VN (để daemon detect non-GDPR đúng)

### 7.3 VPS prep (Japan, 16GB RAM)

- [ ]  Docker installed (`docker --version`)
- [ ]  Port 5900 (VNC) + 6080 (noVNC) accessible từ máy bạn (firewall rules)
- [ ]  Persistent volume mount: `~/.openoutreach/data:/app/data`
- [ ]  4GB+ RAM free (Chrome stealth ăn ~1.5GB)
- [ ]  Disk space 10GB+ (Playwright browsers + embeddings)

### 7.4 Code customization (cần fork repo trước build)

- [ ]  Fork `eracle/OpenOutreach`
- [ ]  Edit `linkedin/conf.py` — apply optional overrides ở Section 6.3 (nếu chọn extra-safe)
- [ ]  Edit `conf.py` — enable ACTIVE_HOURS với VN timezone
- [ ]  (Optional) Customize `linkedin/templates/prompts/follow_up_agent.j2` với Geolify brand voice (tránh banned vocab: revolutionize, leverage, synergy, holistic, robust, seamless, best-in-class, cutting-edge, game-changer)
- [ ]  Build: `make build`

### 7.5 First run

- [ ]  `make run` — interactive onboarding sẽ hỏi:
    - LinkedIn credentials
    - LLM API key (paste từ OpenRouter)
    - Campaign A info (paste product_docs + objective)
- [ ]  Tạo Campaign B qua Django Admin (onboarding chỉ tạo 1)
- [ ]  Set LinkedInProfile fields theo Section 6.2 qua Django Admin
- [ ]  Verify daemon login thành công qua VNC
- [ ]  Check ActionLog sau 1h để confirm rate limits đang được enforce

---

## 8. 30-day Pilot Plan

| Phase | Days | Daily limit | Goal | Stop criteria |
| --- | --- | --- | --- | --- |
| **0 — Warmup** | 1-3 | 5/day total (cả 2 campaign cộng lại) | Verify daemon stability, monitor VNC live, baseline 0 errors | Bất kỳ LinkedIn rate-limit warning popup |
| **1 — Safe ramp** | 4-10 | 8/day | First connections accept, GP model cold-start (cần ≥2 labels) | Acceptance rate < 15% trong 5 days liên tiếp |
| **2 — Steady** | 11-20 | 12/day (final target) | Build labeled dataset 50+, follow-up agent chạy | Pending invites > 300, hoặc bounce rate > 10% |
| **3 — Optimize** | 21-30 | 12/day | Refine ICP từ GP signals, measure CTR sang GEO Audit, iterate follow-up prompt | — |

### Success metrics (track weekly trong Gnoc Workspace)

| Metric | Target 30 days | Tracking source |
| --- | --- | --- |
| Total connects sent | 250-300 | Django Admin → ActionLog |
| Acceptance rate | **≥ 25%** | Deal.state count: CONNECTED+ / total sent |
| CTR sang GEO Audit | **≥ 8%** of connected | PostHog UTM `utm_source=linkedin&utm_campaign=openoutreach` |
| Free signups attributed | **≥ 3%** of connected | PostHog conversion event |
| Reply rate to follow-up | ≥ 12% | ChatMessage count where lead replied |
| Account health | Zero LinkedIn warnings, SSI ≥ 45 | Manual check weekly |
| LLM cost | < $10 over 30 days | OpenRouter dashboard |
| SSI improvement | 38 → 50+ | [linkedin.com/sales/ssi](http://linkedin.com/sales/ssi) |

### Weekly review cadence

- **Monday morning:** Review ActionLog stats, acceptance rate, pending count
- **Thursday:** Check follow-up agent quality (read random 5 conversations)
- **Sunday:** Update Session Log trong Gnoc Workspace + iterate prompts

---

## 9. Conversation Review — bài học từ 2 cold outreach baseline (manual)

### 9.1 Duy Nguyễn — ✅ SUCCESS PATTERN

[https://www.linkedin.com/in/duydudjob/](https://www.linkedin.com/in/duydudjob/)

```markdown
### April 21

**Cong Nguyen (4:11 PM):** Hey Duy, thanks for connecting! I run Geolify[.]ai — we help brands figure out how they show up on AI search engines (ChatGPT, Perplexity, etc.). We actually just launched a free audit tool for this. Thought you might find it interesting: https://geolify.ai/geo-ai-visibility-audit Happy to chat if anything in the results stands out!

---

### April 23

**Cong Nguyen (4:11 PM):** Hey Duy! Just floating this back up — I know LinkedIn messages pile up fast. The audit only takes about 2 minutes and a few folks have found some surprising gaps. No pitch, just data. It gives a quick view of how your brand is appearing across AI search results. If you try it, I'd be curious what you think

**Duy Nguyễn (4:46 PM):** Thanks Cong. I'm trying it now. I like the UX, very intuitive

**Cong Nguyen (4:52 PM):** yeah, thank you

**Duy Nguyễn (5:07 PM):** Do you think of launching a deal on AppSumo? This category is quite hot in there

**Cong Nguyen (5:13 PM):** Yes sure. We are working with Appsumo, and hope Geolify can launch soon. We are running a campaign for early access too

**Duy Nguyễn (5:15 PM):** Awesome

**Cong Nguyen (5:18 PM):** would you like me to add you to our whitelist for early access? I'd love to have a 'power user' like you on board before we officially hit AppSumo 😊

**Duy Nguyễn (5:19 PM):** Yeah, that would be great!

**Cong Nguyen (5:19 PM):** Yeah. And by the way, what do you think about the audit results? Was there any specific insight about your brand's AI search visibility that surprised you?

**Duy Nguyễn (5:22 PM):** this one supprises me. I'm checking my setting on Cloudflare right now 😅 *[Shared an image preview]*

**Cong Nguyen (5:22 PM):** Cool

**Cong Nguyen (5:23 PM):** glad it helped. It is a small fix but makes a huge impact on your AI visibility. Once you update the settings on your CF, feel free to run the audit again to see the difference

**Cong Nguyen (5:28 PM):** Once the bots can crawl your site again, the next step is ensuring the content is structured for AI to cite it properly. That's where the GEO scores in the report come in handy. Let me know if you want to dive deeper into those scores later !

**Duy Nguyễn (5:35 PM):** got it, thanks you 👍
```

**Bài học rút ra (replicate trong `follow_up_agent.j2`):**

1. **2-touch sequence cách 2-3 ngày** — hoạt động tốt. Touch 1 = intro + tool link. Touch 2 = soft re-float ("no pitch, just data").
2. **"No pitch, just data" framing** — giảm defense, tăng engagement.
3. **Question-driven deep dive** sau khi lead engage: *"what specifically surprised you?"* → drove sharing screenshot.
4. **Value-first response** trước khi pitch: explain Cloudflare fix → "feel free to run again" → no immediate ask.
5. **Bridge to next pillar** một cách tự nhiên: "next step is ensuring content is structured for AI to cite it properly" — đề cập GEO scores 6 pillars.
6. **Whitelist offer** là powerful close — biến cold lead thành "power user" status.

### 9.2 Laurent Tam Nguyen — ⚠️ FRICTION (bug killed momentum)

[https://www.linkedin.com/in/laurenttamnguyen/](https://www.linkedin.com/in/laurenttamnguyen/)

```markdown
### May 7

**Cong Nguyen (3:03 PM):** Hey Laurent, thanks for connecting! I run Geolify[.]ai — we help brands figure out how they show up on AI search engines (ChatGPT, Perplexity, etc.). We actually just launched a free audit tool for this. Thought you might find it interesting: https://geolify.ai/geo-ai-visibility-audit Happy to chat if anything in the results stands out!

---

### May 10

**Cong Nguyen (11:58 AM):** Hey Laurent! Just floating this back up — I know LinkedIn messages pile up fast. The audit only takes about 2 minutes and a few folks have found some surprising gaps. No pitch, just data. It gives a quick view of how your brand is appearing across AI search results. If you try it, I'd be curious what you think

**Laurent Tam NGUYEN (6:11 PM):** hi i am interested. i have just tried but the code verification did not work.

---

### May 11

**Cong Nguyen (8:56 PM):** Hi Laurent, thanks for trying it out and apologies for the hiccup! We checked the system and found a minor issue with the verification code process, but it's sorted now. You can try again to experience the tool, or simply drop your website link here and I'll run the audit report and send it to you directly

---

### May 12

**Laurent Tam NGUYEN (9:53 AM):** it still does not work. the code did not work. the resend button did not resend any additional email with ohter code. the email says code is avalid 20min and the validity of the the code on landing page is less than 1 min

**Cong Nguyen (10:50 AM):** thank you for the detailed breakdown and apologies again. I'm digging into the root cause with my team right now to get this fixed

**Cong Nguyen (4:56 PM):** Hello Mr Laurent, just following up :)
Good news, we got it fixed

**Cong Nguyen (4:58 PM):** We found a major issue in the authentication loop thanks to the axact details you send over. Really appreciate you taking the time to help us catch that

**Cong Nguyen (4:59 PM):** Feel free to give the tool another spin whenever you have a moment. I'd love to hear your thoughts, and of course, I'm always here to help if anything else pops up
```

**Outcome:** Lead cold sau May 12. Bug fixed nhưng momentum mất.

**Bài học (FIX trước khi pilot launch):**

1. **P0 BLOCKER — Bug verification code (1-min expiry vs 20-min email claim):** vẫn chưa biết đã thực sự fix chưa. Cần regression test trước khi push 250+ leads vào funnel. **Mỗi 1% lead gặp bug = lose conversion**.
2. **Manual fallback TRONG initial message** — preempt friction:
    
    > *"...Happy to chat if anything in the results stands out! And if the audit tool gives you any trouble, just drop your website URL here and I'll run it for you and send the report directly."*
    > 
3. **Reply detection cần work** — khi Laurent reply "the code did not work", daemon nên auto-pause follow-up và alert Cong. OpenOutreach hiện có `follow_up_agent` đọc conversation history nhưng cần verify nó detect được negative friction signals.
4. **Recovery messaging template** — khi user report bug, agent (hoặc Cong manual) nên có pattern:
    - Acknowledge specific detail họ shared (không generic apology)
    - Offer concrete alternative (manual run)
    - Update khi fix xong
    - Re-invite low-pressure

---

## 10. How to check pending invitations + acceptance rate

### 10.1 Pending invitations sent

1. Truy cập: `https://www.linkedin.com/mynetwork/invitation-manager/sent/`
2. UI sẽ list tất cả pending invites bạn đã gửi
3. Count total — **nếu > 500-700, cần withdraw bớt** (acceptance rate thấp = LinkedIn flag account)
4. Cách withdraw bulk: scroll xuống → click "Withdraw" trên invites cũ nhất (> 30 days = ít khả năng accept)

### 10.2 Acceptance rate (manual calculation)

LinkedIn không hiển thị acceptance rate trực tiếp. Compute:

- **Numerator** = số connections mới trong N ngày qua
    - `linkedin.com/mynetwork/invite-connect/connections/` → sort by "Recently added"
    - Count those added trong window
- **Denominator** = số invites đã gửi trong N ngày qua
    - `linkedin.com/mynetwork/invitation-manager/sent/` → filter date
- **Rate** = numerator / denominator × 100%

**Benchmark:**

- < 15% → account health concern, slow down
- 15-25% → average
- 25-40% → good
- 
    
    > 40% → excellent (rare for cold outreach)
    > 

### 10.3 Once OpenOutreach is running

Django Admin sẽ tracking chính xác:

- **ActionLog** → `action_type='connect'` count = total sent
- **Deal** model:
    - `state='PENDING'` = waiting acceptance
    - `state='CONNECTED'` = accepted (Numerator)
    - `state='FAILED'` = rejected/disqualified
- Compute rate = `CONNECTED / (PENDING + CONNECTED + FAILED)`

---

## 11. Resolved Decisions (2026-05-22 EOD)

| Question | Resolution |
| --- | --- |
| Verification code bug | ✅ **Fixed + tested carefully** — green-light Phase 0 |
| 2FA on `nv-cong` | **ON** — keep ON (safer). Workflow: see Section 12 below |
| SSI boost owner | **Cong** sẽ tự chạy parallel (post 2-3x/tuần + comment 5-10/day) |

## 12. 2FA Workflow (LinkedIn Premium Career + Playwright)

<aside>
🔐

**Keep 2FA ON.** OpenOutreach support flow này nhưng cần supervise initial login + plan cho cookie expiry.

</aside>

### 12.1 Initial login (Day 0)

1. SSH vào VPS Nhật, start container: `make run`
2. Open noVNC từ máy local: `http://<vps-ip>:6080/vnc.html`
    - Hoặc SSH tunnel an toàn hơn: `ssh -L 6080:localhost:6080 user@vps-ip` rồi mở `http://localhost:6080`
3. Daemon sẽ mở Chrome stealth → navigate to LinkedIn login page
4. **Bạn nhập credentials thủ công** qua VNC viewer (daemon có auto-fill nhưng 2FA cần human)
5. LinkedIn prompt 2FA code → mở LinkedIn mobile app/SMS → nhập code qua VNC
6. Sau login thành công → cookies tự động save vào `~/.openoutreach/data/storage_state.json`
7. Verify: stop container, restart → daemon login lại bằng cookie KHÔNG cần 2FA

### 12.2 Cookie expiry plan

- **Typical lifespan:** 14-30 ngày (LinkedIn rotation policy)
- **Force re-login triggers:**
    - VPS IP đổi (Nhật VPS thường stable, ít rotate)
    - LinkedIn detect suspicious activity → security challenge
    - User logout từ device khác
    - Profile/password change
- **Monitor:** Daemon log sẽ ghi `LoginFailed` hoặc `SecurityChallenge`. Setup:
    - Email alert qua `cron` check log file mỗi giờ
    - Hoặc: Telegram bot ping khi daemon stuck > 10 min

### 12.3 Recovery procedure

Khi cookie expire (alert trigger):

1. SSH vào VPS, check log: `docker logs openoutreach --tail 100`
2. Open noVNC → see browser stuck ở login/2FA screen
3. Nhập credentials + 2FA code mới qua VNC
4. Daemon tự resume từ state cũ (Deal/ActionLog không bị lost)
5. Log incident vào Session Log để track pattern

### 12.4 Critical: Volume persistence

Đảm bảo Docker run command có volume mount:

```bash
docker run -d \
  -p 8000:8000 -p 5900:5900 -p 6080:6080 \
  -v ~/.openoutreach/data:/app/data \
  --name openoutreach \
  ghcr.io/eracle/openoutreach:latest
```

Nếu KHÔNG mount volume → cookies + database mất khi container restart → re-login + lose all Deals.

### 12.5 Backup cookies (recommended weekly)

```bash
# Trên VPS, cron weekly:
tar -czf ~/openoutreach-backup-$(date +%Y%m%d).tar.gz ~/.openoutreach/data/
# Rotate: keep last 4 weeks
ls -t ~/openoutreach-backup-*.tar.gz | tail -n +5 | xargs rm -f
```

---

## 13. Remaining Open Items (lower priority, can address mid-pilot)

- [ ]  **Banned vocab compliance** — customize `follow_up_agent.j2` để tránh: revolutionize, leverage, synergy, holistic, robust, seamless, best-in-class, cutting-edge, game-changer, AI-powered (no context). Default prompt generic dễ output banned words.
- [ ]  **PostHog UTM tracking** — setup `utm_source=linkedin&utm_campaign=openoutreach_agency|solo` trên booking link
- [ ]  **Short audit URL** — `geolify.ai/geo-ai-visibility-audit` → `geolify.ai/audit` (giảm LinkedIn link preview filter risk)
- [ ]  **Initial message A/B** — test short version (~30 words) parallel với current (~65 words)

---

<aside>
🚦

**Go/No-Go decision points:**

1. ✅ **CLEARED** — Audit bug fixed + tested → green-light Phase 0 warmup
2. SSI ≥ 38 stable (không tụt) → ✅ green-light Phase 1 ramp
3. Phase 1 acceptance ≥ 15% → ✅ green-light Phase 2 steady
4. Any LinkedIn warning popup → ⛔ STOP daemon, manual review, reduce limits
</aside>

<aside>
🚀

**NEXT ACTION — Phase 0 launch checklist:**

1. Nạp $10 OpenRouter credits (unlock 1000 req/day)
2. Fork OpenOutreach repo + enable ACTIVE_HOURS với `Asia/Ho_Chi_Minh` timezone
3. SSH vào VPS Nhật, `make run` + nhập 2FA qua noVNC (Section 12.1)
4. Set LinkedInProfile limits qua Django Admin (Section 6.2): 12/day, 70/week
5. Tạo Campaign A (Agency) qua onboarding, Campaign B (Solo) qua Django Admin
6. Day 1-3: 5 connects/day total, monitor live VNC liên tục
7. Khi nào ready, ping mình để review Phase 0 log + green-light Phase 1
</aside>