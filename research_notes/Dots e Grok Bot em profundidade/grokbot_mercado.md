# Grok Bot (xAI / SpaceXAI): business, availability and reception (as of 2026-10-08)

Source-quality note for the report writer: the official x.ai pages (x.ai/bot, x.ai/news/introducing-grok-bot, x.ai/changelog/bot) returned HTTP 403 to direct fetch, so most product details come from third-party guides, blogs, aggregators (Releasebot) and the xAI developer docs release notes (docs.x.ai, which did load). Many of the third-party pages are SEO/affiliate pages or come from competitors (CellCog, BetterClaw), so treat them with care. The sources also disagree on the company name, calling it both "xAI" and "SpaceXAI"; the xAI API release notes themselves use "SpaceXAI" when describing Grok 4.6. I found no Grok Bot coverage from The Verge, TechCrunch, Bloomberg, The Information or VentureBeat in my searches (see Gaps).

## 1. Pricing and plans: what each tier includes, usage limits, and how cost scales

### Takeaway
Grok Bot has never had a standalone price. At launch on Aug 11, 2026 it came only with three top tiers: SuperGrok Heavy ($300/mo), Cursor Ultra ($200/mo) and Cursor Teams Premium (~$120/seat/mo). By Aug 26 access had widened to every SuperGrok plan ($30, $100 Plus, $300 Heavy) and to Cursor Pro ($20), Pro+ ($60), Ultra and all Cursor Teams plans. Usage runs on an **unpublished weekly allowance** measured in agent steps and tokens. Extra usage is billed at model/token cost, and there is no Grok Bot-specific spend cap, so an agent running continuously can drain the allowance quickly.

### Cited Findings
**Launch tiers (Aug 11, 2026)**
- Early beta launched Aug 11, 2026. At launch it was bundled with SuperGrok Heavy, Cursor Ultra and Cursor Teams Premium, not sold separately. Enterprise access sat behind a waitlist. — [BuildFastWithAI review (Aug 13, 2026)](https://blog.buildfastwithai.com/grok-bot-review); [Netalith](https://netalith.com/blogs/ai-tools/what-is-grok-bot); [AIToolsReview](https://aitoolsreview.co.uk/insights/grok-bot-agent-launch)
- Price points for those launch tiers:
  - SuperGrok Heavy: $300/month. x.ai's own pricing page shows Heavy without a number; the $300 appears on the grok.com/plans checkout and the Grok Bot page. — [aipricing.guru](https://www.aipricing.guru/subscriptions/xai-supergrok-heavy/); [moclaw.ai](https://moclaw.ai/blog/supergrok-heavy-grok-bot-access)
  - Cursor Ultra: $200/month, and SuperGrok Heavy included Cursor Ultra. — [Medium/levelup review "I paid $300 for SuperGrok Heavy"](https://levelup.gitconnected.com/i-paid-300-for-supergrok-heavy-the-reason-wasnt-grok-495fa6e3c31a)
  - Cursor Teams Premium: about $120 per seat per month. This comes from an Arabic-language pricing page that itself warns its data may be partial; I found no second confirmation. — [getaiperks.com (AR)](https://www.getaiperks.com/ar/ai/grok-bot-pricing)

**Heavy-to-Ultra promotion**
- Cursor staff said on Aug 15 that a $0 Cursor Ultra subscription stays active while SuperGrok Heavy is active. — [CellCog, citing Cursor forum](https://cellcog.ai/blog/grok-bot-problems/)
- On Aug 21 (18:51 UTC) Cursor staff said the Heavy-to-Ultra promotion had ended, with users who had already claimed it grandfathered. — [CellCog, citing Cursor forum](https://cellcog.ai/blog/grok-bot-problems/)
- After the promotion ended, one Heavy buyer was refused both Ultra provisioning and a refund by Cursor Billing, because xAI had processed the charge. That buyer's xAI refund tickets were still unanswered on Aug 23. — [CellCog](https://cellcog.ai/blog/grok-bot-problems/)

**Plan expansions**
- Aug 21: the @bot account on X announced access for SuperGrok Plus, Cursor Pro+, all Cursor Teams plans, plus a limited free trial. The docs FAQ and release notes did not match this at the time. — [CellCog](https://cellcog.ai/blog/grok-bot-problems/)
- Aug 26: an xAI post titled "Grok Bot is now included with more plans" extended access to all SuperGrok, Cursor Pro and Cursor Teams plans. Enterprise remained waitlisted. — [LLM Rumors, citing xAI Aug 26](https://www.llmrumors.com/news/grok-bot-product-agents-authority-backlash); [CellCog ("individual floor of $20")](https://cellcog.ai/blog/grok-bot-problems/)

**Current pricing as of Oct 5, 2026**
- Cursor Pro from $20/mo; SuperGrok $30, Plus $100, Heavy $300. Cursor and SuperGrok allowances do not stack, and linking X Premium+ to Cursor gives a smaller allowance. — [BetterClaw comparison (published Oct 1, updated Oct 5, 2026)](https://www.betterclaw.io/blog/openai-dots-vs-meta-muse-vs-grok-bot)
- The free tier and SuperGrok Lite ($10) exclude Grok Bot. One guide lists Cursor Pro+ at $60 and Ultra at $200, with higher limits on each. — [aibuilderclub / eesel / others via search](https://www.eesel.ai/blog/grok-bot-pricing); [aibuilderclub](https://www.aibuilderclub.com/blog/grok-bot-pricing)
- Eligibility conflict: xAI's FAQ was reported to omit base SuperGrok and base Cursor Pro, while Cursor's live pricing listed Grok Bot on Cursor Pro. — [eesel.ai](https://www.eesel.ai/blog/grok-bot-pricing)
- Another guide says the official Grok Bot account stated that "all SuperGrok and Cursor Pro subscribers" have access. — [DataCamp tutorial](https://www.datacamp.com/tutorial/grok-bot-tutorial)

**Grok consumer tier prices (context)**
- Free, SuperGrok Lite $10, SuperGrok $30, SuperGrok Heavy $300. Through X: X Premium $8, X Premium+ $40. — [suprmind.ai (Aug 24, 2026)](https://suprmind.ai/hub/?p=7769)

**Usage limits and metering**
- The weekly allowance per tier has not been published.
- Usage is measured by agent steps and tokens, not messages, so one long job can cost more than 20 short ones.
- There is "no Grok Bot-specific spend cap yet". Extra usage is billed at model/token cost when on-demand is enabled.
- The limit is soft mid-run. Per Cursor, a Bot already running can finish past the limit, after which on-demand stops until you raise it or the cycle resets.
- Bot usage does not count against normal Grok or Cursor chat quotas.
- Sources: [eesel.ai](https://www.eesel.ai/blog/grok-bot-pricing); [continuumcode.ai "50 Bots and no spend cap"](https://continuumcode.ai/guides/grok-bot-limits/)

**Free trial**
- Described as a usage credit with a 7-day window. One single source says that since Sep 17, 2026 new users get one free month; I could not corroborate this. — [aibuilderclub / justinmckelvey via search](https://justinmckelvey.com/blog/grok-bot)

**Structural limits (xAI docs as of Sep 2, 2026)**
- Teach-by-demonstration recordings: up to 10 minutes.
- Routines per Bot: up to 50.
- Run records kept per routine: 20.
- All named Bots on an account share one persistent computer.
- Sources: [LLM Rumors](https://www.llmrumors.com/news/grok-bot-product-agents-authority-backlash). Continuumcode also reports a cap of 50 Bots and group chats per account. — [continuumcode.ai](https://continuumcode.ai/guides/grok-bot-limits/)

**How fast continuous agents burn the allowance (user reports, Aug 2026)**
- Six agents used about 42% of the weekly allowance on day one (Aug 14).
- About 100 basic chats plus one 10-minute script used 5% of the weekly allowance; the user called this "truly terrible" for business use (r/grok, Aug 22).
- One workload used about half of a Heavy weekly allowance (r/cursor).
- One user estimated about 16.4M tokens in the Heavy allowance and said system-prompt overhead adds cost to every turn (r/GrokBuild).
- Source for all four: [CellCog](https://cellcog.ai/blog/grok-bot-problems/)

**Grok Bot vs Grok 4.6/4.7 API token prices (reference)**
- Grok Bot overage is billed at model/token cost.
- Grok 4.6 and Grok 4.7 on the API cost $2 / $0.50 / $6 per 1M tokens (input / cached input / output) below 200k prompt tokens, and $4 / $1 / $12 above.
- Grok 4.7 Fast costs 2x the standard rates (1.5x for long context) and is available only in Cursor and Grok Build.
- Sources: [xAI docs release notes](https://docs.x.ai/developers/release-notes); [Releasebot xAI](https://releasebot.io/updates/xai)

### Inferences
- The fast widening of eligibility (Aug 11 → Aug 21 → Aug 26) looks like a move to build adoption and a response to backlash over the $200–300 entry price. The real price lever is now the opaque weekly allowance plus metered overage, not the subscription tier.
- For always-on use, effective cost depends on token burn, not seat price. Continuous multi-agent operation can exhaust a $300 Heavy allowance within days and then fall onto uncapped token billing, which is a budget-governance risk for businesses.
- The Cursor/xAI billing split (charged by xAI, provisioned by Cursor) caused refund and entitlement confusion. That is a commercial-maturity issue, not only a technical one.

### Gaps
- No official numbers for weekly allowances on any tier, and no official per-step price.
- I could not load x.ai/bot or x.ai pricing directly (HTTP 403), so the $300 Heavy and $120/seat Teams Premium figures rely on secondary sources.
- The current list price of Cursor Teams Premium could not be confirmed on cursor.com.
- Enterprise pricing is "contact sales" and not public.

## 2. Availability: platforms, regions/countries (Brazil / LatAm), languages, waitlists

### Takeaway
Grok Bot is still labeled beta. It runs on macOS, Windows and Linux desktop plus iOS, and on Android since Sep 2, 2026 (per secondary sources). I found **no official country list and no geo-exclusion for Grok Bot**, and no Brazil-specific launch or localization. Brazilians with an eligible SuperGrok or Cursor subscription can most likely use it, since access is gated by plan rather than country. The model handles PT-BR, but the admin UI and support are in English. Enterprise was waitlisted at launch; Team Bots went to public beta on Sep 28.

### Cited Findings
**Platforms**
- At launch: desktop (including a Linux build) and iOS, with Android "coming soon." — [BuildFastWithAI (Aug 13)](https://blog.buildfastwithai.com/grok-bot-review)
- Conflict: another guide said Linux desktop, Android and iPad were not supported at initial launch. A third says the download xAI links is macOS, with iOS beside it. — [search summary of composio/kie.ai guides](https://composio.dev/content/guide-to-frok-bot); [moclaw.ai](https://moclaw.ai/blog/supergrok-heavy-grok-bot-access)
- As of Oct 5, 2026: desktop app for macOS, Windows and Linux; iOS; Android since Sep 2. — [BetterClaw](https://www.betterclaw.io/blog/openai-dots-vs-meta-muse-vs-grok-bot)
- Android on Sep 2, followed by an Enterprise launch on Sep 3, per one write-up. I could not load it (HTTP 502), so this is unverified. — [pasqualepillitteri.it via search snippet](https://pasqualepillitteri.it/en/news/10621/grok-bot-xai-autonomous-agents)
- The xAI changelog for Grok Bot exists (e.g. v0.28.0 on Aug 26, 2026), but the visible excerpts did not mention Android. — [x.ai/changelog/bot via search](https://x.ai/changelog/bot)

**Infrastructure**
- Grok Bot is described as the first joint xAI–Cursor product and runs on Cursor's infrastructure for downloads and onboarding. — [search summary of launch coverage](https://www.tryfriday.ai/blog/grok-bot-launch)
- Sign-in and privacy mode come through Cursor. — [BetterClaw](https://www.betterclaw.io/blog/openai-dots-vs-meta-muse-vs-grok-bot)

**Regions**
- The BetterClaw comparison states no regional restriction for Grok Bot. The EEA/UK/Switzerland exclusion it lists applies to ChatGPT Pro/Dots, and Meta Muse is US and Canada only. — [BetterClaw](https://www.betterclaw.io/blog/openai-dots-vs-meta-muse-vs-grok-bot)

**Brazil**
- The official x.ai/bot page snippet (seen via search) lists eligible plans: SuperGrok, SuperGrok Plus, SuperGrok Heavy, Cursor Pro, Pro+, Ultra, Cursor Teams Standard and Premium, on desktop and iOS. No country restriction appears in the snippet. — [x.ai/bot (search snippet)](https://x.ai/bot)
- A Brazilian blog (nacao.digital) says the model understands and answers in PT-BR "with quality". It also says admin and official support are in English, and that xAI "não anunciou data" (has not announced a date) for full localization for the Brazilian market.
- The same blog lists caveats: compliance (data retention, audit logs) is not yet adequate for regulated sectors; Gmail and Slack integrations are in beta with permission limits; there is no native Salesforce, HubSpot or ERP integration. The author could not access xAI's pricing page. — [nacao.digital](https://nacao.digital/blog/grok-bot/)
- PT-language explainer — [eigent.ai/pt](https://www.eigent.ai/pt/blog/grok-bot)
- The Grok chatbot app has been on the Brazilian App Store since Jan 2025. — [MacMagazine](https://macmagazine.com.br/post/2025/01/31/aplicativo-oficial-do-grok-chatbot-do-x-e-disponibilizado-no-brasil/)
- A third-party App Store price tracker lists a Brazilian regional price for SuperGrok of about $29/mo, versus about $30 in the US (updated June 2026). — [opentherank.com (PT)](https://opentherank.com/pt/ai-pricing/grok/)
- Microsoft Foundry lists Brazil South as a region for several Grok API models. This concerns the API, not consumer Grok Bot. — [search summary](https://zilliz.com/ai-faq/is-grok-available-worldwide)
- Grok availability elsewhere varies with local regulation: Malaysia temporarily blocked Grok, and Indonesia was reported to do so in early 2026. — [zilliz FAQ](https://zilliz.com/ai-faq/is-grok-available-worldwide)

**Languages**
- No official statement on supported UI languages for Grok Bot. PT-BR works at the model level per the nacao.digital blog only. — [nacao.digital](https://nacao.digital/blog/grok-bot/)

**Waitlists, Enterprise and Team Bots**
- Enterprise was waitlisted at launch and still waitlisted as of the Aug 26 expansion. — [LLM Rumors](https://www.llmrumors.com/news/grok-bot-product-agents-authority-backlash)
- By October, Enterprise is listed as available "through sales." — [BetterClaw](https://www.betterclaw.io/blog/openai-dots-vs-meta-muse-vs-grok-bot)
- Team Bots (xAI news post, Sep 28, 2026): "Team Bots is available today in public beta on Teams and Enterprise plans." It offers shared context, plugins, credentials and memory, while each user's conversations stay private. It ships with pre-built bots for sales, product, marketing and data workflows. — [Releasebot xAI](https://releasebot.io/updates/xai)

### Inferences
- **Brazil:** the evidence is indirect but consistent. Access is plan-gated, SuperGrok is purchasable in Brazil (App Store regional price), and no source lists a Brazil or LatAm exclusion. It is therefore very likely usable from Brazil with an eligible plan. That is unlike OpenAI Dots (excluded in EEA/UK/CH on Pro) and Meta Muse (US/CA only).
- "Usable" is not the same as "officially launched or localized" for Brazil:
  - There is no PT-BR UI or support.
  - There is no BRL pricing beyond App Store regional pricing.
  - There is no LGPD-specific statement.
  - Connectors to Brazil-specific tools (e.g. WhatsApp Business, local ERPs) are not mentioned.
- Payments through Cursor (USD card) are probably the simplest route for Brazilian developers.

### Gaps
- No official xAI country-availability list for Grok Bot or SuperGrok. Confirmation requires checking the in-app subscription page from a Brazilian account.
- No information on data residency: where the cloud computers run, and whether they are US-only. The Grok 4.7 API is "also served on the US regional endpoint," which suggests US hosting but doesn't confirm it. — [Releasebot](https://releasebot.io/updates/xai)
- Exact dates for Windows and Android support could not be confirmed from xAI's own changelog (403).

## 3. Models: what powers Grok Bot, routing, Grok 4.20 multi-agent, benchmarks

### Takeaway
xAI's docs **do not name the model** behind Grok Bot. Model selection is managed by xAI, with no picker and no bring-your-own-key. Secondary sources variously tie it to Grok 4.5, 4.6 or (now) 4.7, so the specific model is unconfirmed. Grok 4.20 Multi-agent dates from March 2026 and is not documented as part of Grok Bot. No Grok Bot benchmarks have been published, official or independent.

### Cited Findings
**What powers Grok Bot**
- "xAI doesn't name the model in its docs. Model selection is managed for you, with no model picker and no bring-your-own-key." xAI announced Grok 4.6 in August, but the docs don't commit to it. — [BetterClaw (Oct 5)](https://www.betterclaw.io/blog/openai-dots-vs-meta-muse-vs-grok-bot)
- Grok 4.6 is tied to the wider rollout; Musk said the broader release is coming shortly. — [BuildFastWithAI (Aug 13)](https://blog.buildfastwithai.com/grok-bot-review)
- A third-party blog claims Grok Bot runs on Grok 4.5 (500K context, released Jul 8, 2026). This is unconfirmed. — [search summary](https://www.orcarouter.ai/ar/blog/grok-bot-launch)

**Model timeline (official)**
- Grok 4.6 (August 2026): described as "SpaceXAI's frontier model for coding, agentic tasks, and knowledge work". Reasoning effort settings are low, medium, high (default) and xhigh. — [xAI docs release notes](https://docs.x.ai/developers/release-notes)
- Grok 4.7: released Sep 21, 2026 (`grok-4.7`, 500k context, text and image input). "Grok 4.7 is available today in Cursor and Grok Build." There is a Fast variant with twice the output speed at twice the price. No Grok Bot mention. — [Releasebot](https://releasebot.io/updates/xai); [xAI docs](https://docs.x.ai/developers/release-notes)
- Grok 4.20 and Grok 4.20 Multi-agent appear only in the March 2026 release notes, and are not tied to Grok Bot. — [xAI docs](https://docs.x.ai/developers/release-notes)

**Routing complaints**
- One user reported that even simple tasks went to the heaviest model tier. After a later shift to a cheaper tier, the Bots were "quite stupid at times" (Aug 22). — [CellCog](https://cellcog.ai/blog/grok-bot-problems/)
- Separately, Cursor's own "Auto" router was reported to pick Grok 4.5 most of the time. That is Cursor's router, not Grok Bot's. — [Cursor forum](https://forum.cursor.com/t/auto-router-broken-only-ever-picks-grok-4-5/167588)

**Benchmarks**
- No independent benchmark exists, and the product is closed-source. — [search summary of launch reviews](https://www.anti-ai.app/specials/grok-bot/)
- As of early September there was no repeatable benchmark, large-sample reliability study or security audit. — [Review search summary (therundown/kingy/agent-finder)](https://www.therundown.ai/tools/grok-bot)

### Inferences
- Grok Bot almost certainly uses some form of automatic routing between xAI models (user reports of tier shifts). It most likely moved from 4.6 to 4.7 after Sep 21, since 4.7 shipped first "in Cursor and Grok Build" and Grok Bot runs on Cursor infrastructure. This is inference, not confirmed.

### Gaps
- No official statement on the Grok Bot model or routing policy.
- Not confirmed whether Grok 4.20 multi-agent mode is used.
- No agent benchmarks (OSWorld, WebArena or similar) published for Grok Bot.

## 4. Reception: press, users, praise, criticism, failures, security/privacy, cost, competitor comparisons

### Takeaway
Early reception splits two ways. Influencers praise the concept: Lenny Rachitsky called it one of the most exciting AI products in months. Hands-on users, mostly on the Cursor forum and Reddit, report:
- a major Aug 20–21 outage, caused by the shared computer getting stuck;
- fast allowance burn;
- context/memory problems;
- billing confusion.

The dominant critique is architectural: all named Bots share **one cloud computer, one set of browser sessions, files and credentials**, and xAI's own docs say separate Bots are not a security boundary. No confirmed breach or unauthorized transaction had been reported.

### Cited Findings
**Praise and positioning**
- Lenny Rachitsky called it one of the most exciting AI products in months. The page notes this comes from hands-on impressions, not independent testing. — [BuildFastWithAI](https://blog.buildfastwithai.com/grok-bot-review)
- xAI says its own team uses bots across sales, marketing and other functions. Example uses:
  - auto-replies across inbox and messaging tools;
  - research and podcast briefs;
  - scanning subscriptions;
  - job matchmaking.
  - Source: [BuildFastWithAI](https://blog.buildfastwithai.com/grok-bot-review)
- Product capabilities:
  - one persistent cloud VM with a browser, terminal and files;
  - teach-by-demonstration that turns into skills and routines;
  - memory;
  - approvals;
  - connectors;
  - handoff between named Bots;
  - Bots keep working after the user's device is closed.
  - Sources: [xAI docs release notes ("Durable AI teammates that work on a persistent cloud computer, with messaging, approvals, connectors, and routines")](https://docs.x.ai/developers/release-notes); [LLM Rumors](https://www.llmrumors.com/news/grok-bot-product-agents-authority-backlash)
- Aug 29: an X integration added post search, timelines, mentions, trends and bookmark management. — [LLM Rumors, citing xAI "Grok Bot now works with X"](https://www.llmrumors.com/news/grok-bot-product-agents-authority-backlash)

**Reliability incidents (Aug 2026), per CellCog, a competitor, citing the Cursor forum and Reddit** — [CellCog](https://cellcog.ai/blog/grok-bot-problems/)
- Aug 20–21: "None of my agents in grok bot work… nothing works." Cursor staff confirmed the cause was a stuck shared computer. Because every Bot runs on that one machine, all of a user's Bots stopped at once, and resetting the computer can lose unsynced work.
- Aug 20–21: "Bot failed to respond" persisted through restarts and reinstalls.
- Aug 21–23: one user saw a black window and was locked out for days.
- Aug 17: a user who bought Cursor Ultra for Grok Bot called it "nearly unusable for me", citing overloaded-provider errors, a slow VM and agents stuck on basic tasks.
- Unverified: an r/cursor comment alleged a Bot wiped production.

**Context and memory**
- Michael Greenhalgh (Health.AI) on Aug 13: "Each Bot is one unbounded thread", and duplicating Bots "does not fix the product."
- Cursor staff confirmed on Aug 20 that conversations are auto-summarized near the context limit. There is no fresh session within the same Bot, no manual compaction and no context meter.
- Source: [CellCog](https://cellcog.ai/blog/grok-bot-problems/)

**General agent failure modes**
- Browser automation is fragile: changed pages, expired sessions, CAPTCHAs and blocked sites cause failures.
- Bots can hallucinate, pick the wrong account or record, and report incomplete work as done.
- Community reports include forgotten multi-step tasks and a bot that missed a live fantasy-draft pick.
- Sources: [review search summary (cellcog/therundown/kingy)](https://www.therundown.ai/tools/grok-bot); [kingy.ai](https://kingy.ai/blog/grok-bot-ai-teammate-price-security/)

**Security and privacy**
- xAI's docs (updated Aug 22) say separate Bots should not be used as a security boundary. Browser cookies, signed-in sessions, files under /workspace and CLI credentials are shared across all Bots on an account.
- Deleting a Bot does not remove its files or sessions.
- Approvals cover only the next proposed action and cannot undo completed work. The risk of consent fatigue is noted.
- Sources: [LLM Rumors](https://www.llmrumors.com/news/grok-bot-product-agents-authority-backlash); [CellCog](https://cellcog.ai/blog/grok-bot-problems/)
- daily.dev headline: "Grok Bot is a 24/7 cloud worker that knows your passwords, and that's the problem". Passwords and 2FA codes are entered into a remote browser controlled by vendor infrastructure. Action recordings are reportedly kept for 90 days. — [daily.dev](https://daily.dev/posts/grok-bot-is-a-24-7-cloud-worker-that-knows-your-passwords-and-that-s-the-problem-rlbylyidy); [review search summary](https://www.therundown.ai/tools/grok-bot)
- One business user created separate Chrome profiles per agent to isolate Microsoft logins. The profiles reset daily and Chrome crashed often. — [CellCog](https://cellcog.ai/blog/grok-bot-problems/)
- Prompt injection: there is no Grok Bot-specific evaluation. NIST CAISI red-teaming found agent hijacking succeeded against every target model. — [LLM Rumors](https://www.llmrumors.com/news/grok-bot-product-agents-authority-backlash)
- Counterpoint: no independently verified cross-Bot breach, unauthorized transaction or Auto Review failure has been reported. The critique is "architectural and prospective." — [LLM Rumors](https://www.llmrumors.com/news/grok-bot-product-agents-authority-backlash)
- Mitigations: a training opt-out is available, and sensitive actions can go through Auto Review. — [BetterClaw](https://www.betterclaw.io/blog/openai-dots-vs-meta-muse-vs-grok-bot)

**Cost complaints**
- The allowance-burn reports above.
- The Heavy-to-Ultra promo ending abruptly, with refunds refused.
- Opaque, unpublished allowances.
- Sources: [CellCog](https://cellcog.ai/blog/grok-bot-problems/); [eesel.ai](https://www.eesel.ai/blog/grok-bot-pricing)

**Competitor comparisons (as of Oct 5, 2026)**

| | Grok Bot | OpenAI Dots | Meta Muse |
|---|---|---|---|
| Launch | Aug 11 (beta) | Sep 29 | Sep 8 |
| Model | Not named, managed by xAI | GPT-6 Astra | Muse Spark |
| Entry price | $20 (Cursor Pro) / $30 (SuperGrok) | $100 (ChatGPT Pro) | Free; Power $20, Max $100 |
| Regions | No restriction stated | Pro excludes EEA, UK, CH | US and Canada only |
| Best for | Coding and computer-use tasks | Work across 4,000+ apps | Personal errands |

- None of the three lets users choose the underlying model. Grok Bot's weaknesses are opaque usage, no model choice and beta status. — [BetterClaw](https://www.betterclaw.io/blog/openai-dots-vs-meta-muse-vs-grok-bot)
- Business access for Grok Bot is around $120/seat, which one source calls the most expensive business option. — [blockchain-council / appscribed via search](https://www.blockchain-council.org/ai/openai-dots-vs-grok-bot-vs-muse/)
- Anthropic is framed as "AI teammates inside your tools." Meta Muse Code and xAI's own Grok Build are framed as coding agents. — [BuildFastWithAI](https://blog.buildfastwithai.com/grok-bot-review)
- I found no comparison with "Google Gemini Spark", and search returned nothing for that product name.

### Inferences
- The narrative is "a strong concept, an immature beta." Bugs such as the stuck computer can be fixed, but the single shared computer per account, advisory memory and bundled weekly quotas are architectural choices. — [paraphrasing review summary](https://www.therundown.ai/tools/grok-bot)
- For a business buyer, the shared-credential model is the main adoption blocker. It forces "one account per trust domain" designs.

### Gaps
- No mainstream tier-1 press found (The Verge, TechCrunch, Bloomberg, The Information, VentureBeat). Either the search tool didn't surface it or coverage was limited.
- No direct Reddit or HN threads retrieved; Reddit content is second-hand via CellCog.
- No YouTube reviews retrieved.
- No incident post-mortem from xAI.

## 5. Grok consumer features context and roadmap / adoption metrics

### Takeaway
Announced or delivered roadmap so far:
- Android (shipped around Sep 2);
- Team Bots (public beta Sep 28, on Teams and Enterprise plans);
- Enterprise (waitlist, later through sales);
- the X integration (Aug 29).

I found no announced marketplace, Team Bots GA date or adoption numbers. Consumer Grok features (memory, custom-agent slots, Skills, Workspaces, Companions, DeepSearch, Automations) were not researched in depth here.

### Cited Findings
- Team Bots public beta (Sep 28) ships pre-built bots for sales, product, marketing and data. Teams and Enterprise customers are invited to "contact sales." — [Releasebot](https://releasebot.io/updates/xai)
- Enterprise contracts: admin panel, permission controls and dedicated support, priced on request. — [nacao.digital](https://nacao.digital/blog/grok-bot/)
- An Enterprise launch on Sep 3 is reported by one source only and is unverified. — [pasqualepillitteri.it snippet](https://pasqualepillitteri.it/en/news/10621/grok-bot-xai-autonomous-agents)
- Grok Bot features that overlap with the consumer "Skills / Automations" concept:
  - skills taught by demonstration;
  - routines (scheduled automations; up to 50 per Bot);
  - memory, which the docs warn "can hold stale assumptions."
  - Sources: [LLM Rumors](https://www.llmrumors.com/news/grok-bot-product-agents-authority-backlash); [CellCog](https://cellcog.ai/blog/grok-bot-problems/); [DataCamp tutorial](https://www.datacamp.com/tutorial/grok-bot-tutorial)
- Grok Bot is a separate product from the Grok chat app and from Grok Build, the coding CLI. — [DataCamp](https://www.datacamp.com/tutorial/grok-bot-tutorial)
- Adoption: no user counts were found. "None are stated." — [BuildFastWithAI](https://blog.buildfastwithai.com/grok-bot-review); [LLM Rumors](https://www.llmrumors.com/news/grok-bot-product-agents-authority-backlash)

### Inferences
- The roadmap is moving toward teams and enterprise. Team Bots with shared credentials and memory directly addresses the "one machine per user" critique by making sharing a feature. It does not solve isolation, though.
- The expansion to $20/$30 plans suggests consumer reach matters as much as enterprise.

### Gaps
- No info found on:
  - a marketplace;
  - a Team Bots GA date;
  - Grok Bot inside custom agents (4 slots), Workspaces, Companions or DeepSearch;
  - adoption, revenue or usage metrics;
  - SLA, uptime commitments or compliance certifications (SOC 2 etc.).
