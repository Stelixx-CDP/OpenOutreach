# [OpenOutreach] Campaign Content — Paste-Ready

<aside>
📌

**Usage:** Mở page này song song với Django Admin (`localhost:8000/admin/linkedin/campaign/add/`). Copy từng block code và paste vào field tương ứng. Field nào không đề cập = giữ default.

**Updated:** 2026-05-22 — refined v2 với hooks Mom Test, anti-hype voice, GEO terminology consistent.

</aside>

# Campaign A — Agency Track (Primary ICP)

## Field 1: Name

```
GEO Audit — Agency Track
```

## Field 2: Users

Chọn `congnv` từ Available users → click → Chosen users

## Field 3: Product docs

<aside>
💡

Injected verbatim vào 3 prompts (qualification, search_keywords, follow_up_agent). EN-only. Avoid Geolify banned vocab: revolutionize, leverage, synergy, holistic, robust, seamless, best-in-class, cutting-edge, game-changer, AI-powered (no context).

</aside>

```
Geolify is a Generative Engine Optimization (GEO) platform. It measures how brands appear in AI search engines (ChatGPT, Perplexity, Gemini, Google AI Mode, Claude, Microsoft Copilot, and AI Overviews), then ships specific fixes to improve that visibility.

CORE PRODUCT — GEO Audit (free, no signup wall):
- Generates a GEO Score (0-100) for any website in under 2 minutes
- Breaks the score into 6 pillars:
  1. Technical accessibility — can AI crawlers reach the site (robots.txt, Cloudflare bot rules, llms.txt)
  2. Content semantics — is content structured for AI extraction (headings, FAQ blocks, answer-shaped paragraphs)
  3. Structured data — Schema.org coverage (Organization, Product, FAQ, Article, HowTo)
  4. Entity authority — is the brand a recognized entity in Knowledge Graph and AI training data
  5. Citation signal — does the brand appear in sources AI engines cite (Reddit, news, industry blogs, Wikipedia)
  6. AI engine coverage — which of the 7 major AI engines actually mention the brand when queried

FOLLOW-ON PRODUCT — Action Center:
- 27 shipped Actions (64 more on roadmap) with step-by-step fixes ranked by impact
- Each Action ties to one or more pillars, shows expected score lift, and tracks completion
- Re-audit anytime to verify the fix moved the needle

ADD-ON — Prompt Monitoring (beta):
- Track specific prompts (e.g. "best SEO tool for SaaS") and get alerted when the brand's position changes across engines

PRICING:
- Free: 1 audit, basic Action Center access
- Starter $29/mo: 5 audits, full Action library
- Growth $79/mo: 25 audits, prompt monitoring, weekly reports (most popular)
- Pro $289/mo: unlimited audits, white-label reports, API access
- Enterprise: custom $1,800 – $7,500/mo (managed service)

BRAND:
- Tagline: "Audit. Fix. Track."
- Hook question: "What's your GEO Score?"
- Emotional positioning: "From invisible to cited."
- Voice: technical, data-driven, no hype. Talk like a senior SEO engineer, not a marketer.

DIFFERENTIATORS vs alternatives:
- Free score with no signup wall (Profound, Athena, Otterly require paid trial)
- Action-oriented — ships fixes, not just diagnostics
- Covers 7 AI engines, not just ChatGPT
- Self-serve PLG flow — no demo gate
- Built for agency reporting (white-label on Pro)

CURRENT STAGE: Early-stage. 78 signups in 3 weeks (free tier), pre-revenue, working toward first paid conversions. The audit tool is production-ready; pricing tiers are live but unproven.
```

## Field 4: Campaign objective

<aside>
💡

Injected verbatim. Đây là field quan trọng nhất cho qualification quality. Includes: target, roles, geo, pain points, engagement flow, qualify yes/no rules, search angles.

</aside>

```
TARGET: B2B digital marketing agencies with 5-20 employees that serve SaaS, DTC, or professional services clients in English-speaking markets.

DECISION-MAKER ROLES (priority order):
1. Founder, CEO, or Managing Director of agencies under 30 people
2. Head of SEO, Head of Content, Head of Strategy
3. Director or VP of SEO, Content, or Digital Marketing
4. Senior SEO Manager or Senior Content Strategist (only at agencies under 10 people)

GEOGRAPHIC PRIORITY:
- Tier 1: US, UK, Australia, Canada, Ireland, New Zealand
- Tier 2: Netherlands, Germany, Sweden, France (only if profile is in English)
- Skip non-English profiles until i18n is supported

WHY THEY CARE — the pain to surface in qualification and DMs:
- Clients are asking "how do we show up in ChatGPT?" and agencies have no defensible answer
- Ahrefs, Semrush, and Moz measure traditional SEO but not AI search visibility
- Agencies need to add a GEO / AI-search service line to stay relevant in 2026
- Reporting AI visibility to clients is currently manual screenshots or impossible
- Agencies losing pitches to competitors who already pitch GEO offerings

IDEAL ENGAGEMENT FLOW:
1. Accept the connection within 7 days
2. Click the GEO Audit link and run an audit on ONE client brand
3. Share the score with the client → client asks for ongoing monitoring or fixes
4. Agency upgrades to Growth ($79) or Pro ($289) to serve multiple client brands

QUALIFY YES when the profile shows ALL OF:
- Current title contains: SEO, Content, GEO, AEO, Search, Digital Marketing, or Growth — with seniority (Founder, Head, Director, VP, Senior)
- Company is an agency, consultancy, studio, or boutique (not in-house at a single brand) — check company name or about section
- Company headcount 2-50 on LinkedIn (small or medium)
- Profile shows recent posts or comments on AI, SEO, content marketing, or growth topics (last 60 days)
- 500+ connections (active LinkedIn user)

QUALIFY NO (create FAILED Deal with outcome wrong_fit) when the profile shows ANY OF:
- In-house SEO or Content at a single brand (not an agency)
- Pure B2C or e-commerce focus without SaaS or services clients
- Recruiter, hiring manager, job-seeker, student, or HR title
- Sales, BDR, SDR, Account Executive title (not a buyer of marketing tools)
- Large agencies with 500+ employees (procurement cycle kills PLG flow)
- Solo freelancer with no team — these belong in the Solopreneur campaign
- Company with under 90 days of LinkedIn activity (likely fake or dormant)
- Profile primarily in Vietnamese, Japanese, Chinese, Korean, Arabic, or any non-English language
- Coach selling generic marketing courses (not service-delivery agency)

FOLLOW-UP TONE GUIDELINES:
- Lead with the GEO Score result for one of their client brands or their own agency site if no clear client
- Frame as data, not pitch: "ran your site through our audit, here is what stood out"
- Quote one specific pillar finding (technical accessibility, structured data, or AI engine coverage)
- Offer the booking link only after the lead engages with the audit result, not in the first message
- Never use the words: revolutionize, leverage, synergy, holistic, robust, seamless, best-in-class, cutting-edge, game-changer, AI-powered

SEARCH ANGLES (seeds for keyword generation):
- SEO agency founder
- Head of SEO at marketing agency
- Content marketing agency director
- GEO consultant
- AI search optimization agency
- generative engine optimization
- answer engine optimization
- SEO consultancy founder SaaS
- digital marketing agency owner B2B
- content strategy agency lead
```

## Field 5: Booking link

```
https://geolify.ai/geo-ai-visibility-audit?utm_source=linkedin&utm_campaign=openoutreach_agency&utm_medium=dm
```

## Field 6: Is freemium

❌ **UNCHECKED** — Geolify cần custom BayesianQualifier learn từ labels, không dùng KitQualifier pre-trained.

## Field 7: Action fraction

```
0.2
```

(Default, không đổi)

## Field 8: Seed public ids

<aside>
⚠️

Thay PLACEHOLDER bằng public_ids thật trước khi save. Xem chat để guide step-by-step thu thập.

</aside>

```
[
  "duydudjob",
  "PLACEHOLDER-agency-founder-1",
  "PLACEHOLDER-agency-founder-2",
  "PLACEHOLDER-head-of-seo-1",
  "PLACEHOLDER-head-of-seo-2",
  "PLACEHOLDER-content-director-1",
  "PLACEHOLDER-geo-consultant-1"
]
```

---

# Campaign B — Solopreneur Track (Secondary ICP, 73% production data)

## Field 1: Name

```
GEO Audit — Solopreneur Track
```

## Field 2: Users

Chọn `congnv` (cùng account, daemon tự balance load qua action_fraction gating)

## Field 3: Product docs

<aside>
💡

**Paste y hệt Campaign A Field 3** — product description không đổi theo ICP, chỉ campaign_objective khác.

</aside>

## Field 4: Campaign objective

```
TARGET: Solo SEO consultants, content strategists, indie SaaS founders, content creators, and personal-brand builders — individuals (not agencies) who personally do AI/SEO work and own the buying decision.

DECISION-MAKER ROLES (priority order):
1. Solo SEO consultant or freelance SEO
2. Freelance content strategist or content marketer
3. Indie SaaS founder (1-3 people team) using content-driven distribution
4. Newsletter operator or content creator who monetizes via paid newsletter or community
5. Personal-brand builder with active LinkedIn or Twitter presence in marketing niche

GEOGRAPHIC PRIORITY:
- Tier 1: US, UK, Australia, Canada, Ireland, New Zealand
- Tier 2: Netherlands, Germany, Sweden, France (English profiles only)
- Tier 3 (solo segment is global): India, Philippines, South Africa (only if profile + posts are clearly in English and active)

WHY THEY CARE — pain to surface:
- They sell SEO services and need to add GEO to their offering to stay relevant
- They run a personal brand and want to know if AI engines actually mention them
- They are early adopters and love testing tools — high engagement, high share-rate
- Small budgets but fast decision speed (no procurement, no committee)
- Vocal on LinkedIn — when they like something, they amplify (word-of-mouth multiplier)

IDEAL ENGAGEMENT FLOW:
1. Accept the connection within 5 days (faster than agencies)
2. Run a GEO Audit on their own personal site or a client site within 3 days
3. Often share a screenshot of the score on LinkedIn (free distribution loop)
4. Upgrade to Starter ($29) within 2 weeks for additional audits

QUALIFY YES when the profile shows ALL OF:
- Title contains: freelance, solo, consultant, founder (single-person), creator, strategist, independent, indie
- Company field shows Self-Employed, Freelance, or a 1-person company they founded
- Posts AI, SEO, GEO, or content marketing content actively in the last 30 days
- Has a personal site, newsletter, Substack, or portfolio in the profile
- 1000+ followers with active engagement (likes and comments on their own posts)

QUALIFY NO (create FAILED Deal with outcome wrong_fit) when profile shows ANY OF:
- Agency owner with more than 5 employees — belongs in Agency campaign
- In-house role at a brand with more than 100 employees
- Pure B2C e-commerce solo seller (not marketing services)
- Recruiter, hiring manager, or coach selling courses unrelated to marketing
- Profile inactive in the last 60 days (no posts, no comments, no profile updates)
- Profile primarily in a non-English language
- Crypto or NFT promoter title
- Generic "life coach", "mindset coach", "manifestation" titles

FOLLOW-UP TONE GUIDELINES:
- Match their casual LinkedIn voice — less formal than the Agency campaign
- Lead with a finding from THEIR personal site audit, not a generic intro
- Invite them to share the score publicly ("would love your take if you post about it")
- Reference one specific pillar finding tied to their content style
- Never use: revolutionize, leverage, synergy, holistic, robust, seamless, best-in-class, cutting-edge, game-changer, AI-powered

SEARCH ANGLES (seeds for keyword generation):
- freelance SEO consultant
- solo SEO consultant SaaS
- freelance content strategist B2B
- indie SaaS founder content marketing
- AI content creator newsletter
- GEO consultant freelance
- personal brand SEO
- newsletter operator marketing growth
- content marketing freelancer SaaS
- generative engine optimization solo
- independent content strategist
```

## Field 5: Booking link

```
https://geolify.ai/geo-ai-visibility-audit?utm_source=linkedin&utm_campaign=openoutreach_solo&utm_medium=dm
```

## Field 6: Is freemium

❌ **UNCHECKED**

## Field 7: Action fraction

```
0.2
```

## Field 8: Seed public ids

```
[
  "PLACEHOLDER-solo-seo-1",
  "PLACEHOLDER-solo-seo-2",
  "PLACEHOLDER-freelance-content-1",
  "PLACEHOLDER-indie-founder-1",
  "PLACEHOLDER-creator-newsletter-1",
  "PLACEHOLDER-personal-brand-1"
]
```

---

# Verification checklist sau khi tạo cả 2 campaigns

- [ ]  Cả 2 campaigns hiển thị trong `Campaigns` list của Django Admin
- [ ]  Click vào từng campaign → verify tất cả 8 fields đã save đúng
- [ ]  `campaign_objective` và `product_docs` KHÔNG bị truncate (textarea full length)
- [ ]  `is_freemium` = False trên cả 2
- [ ]  `users` field hiển thị `congnv` ở mỗi campaign
- [ ]  `seed_public_ids` là valid JSON array (không có PLACEHOLDER, có quotes đúng)
- [ ]  `booking_link` đầy đủ UTM parameters
- [ ]  Test: vào `linkedin/searchkeyword/` → daemon nên auto-generate 5-10 SearchKeyword cho mỗi campaign sau <1 giờ first run