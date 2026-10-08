# Grok Bot (SpaceXAI / xAI): how the product works

Scope: the always-on agent product "Grok Bot" launched in beta on Aug 11, 2026. It is not the @grok chatbot on X. Research date: 2026-10-08.

Source-quality legend:
- **[OFFICIAL]**: x.ai news posts and docs.x.ai/grok-bot pages, read via fetch on 2026-10-08. The docs are living pages and have changed since launch (see the platform and plan conflicts below).
- **[PRESS]**: major tech press (VentureBeat, MacRumors).
- **[3P]**: third-party guides, blogs and X posts.
- Quotes were extracted through a page-summarising fetch tool. Wording is very close to the source but may differ slightly, so re-check before quoting in print.
- The official changelog (x.ai/changelog/bot) returned HTTP 403. Changelog items here come from search snippets and third-party trackers.

---

## 1. Architecture: the persistent cloud computer, computer use, takeover and limits

### Takeaway
Each Grok Bot is a named agent working on a persistent cloud computer. The computer has a browser, filesystem/`/workspace`, terminal/command line and connected tools, and it runs in Cursor's cloud.

- **One machine per account, one screen per Bot.** The computer belongs to the user account and is shared by all of that user's Bots. Each Bot gets its own "screen" and runs one computer-use task at a time.
- **Not a security boundary.** Official docs state explicitly that separate Bots are not a security boundary.
- **Keeps running offline.** Work continues with the laptop or app closed.
- **Takeover for human-only steps.** Passwords, passkeys, 2FA, CAPTCHAs, payment and identity checks are done by the human through the "Agent Computer" takeover view.
- **Known limits.** Sites that block automation or datacenter IPs, expiring sessions, and possible routine pauses.

### Cited Findings

**What the computer is**
- Official overview: each Bot "works on a persistent cloud computer" with "a browser, a filesystem, and a terminal". Bots "use connectors where available and computer use for everything else". "The computers Bots use run in Cursor's cloud." — [docs.x.ai overview](https://docs.x.ai/grok-bot/overview)
- "Grok Bot works from a persistent cloud computer", providing browser, command line, files and connected tools. — [docs.x.ai Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)
- Every Bot on the account uses the same computer. Browser sessions, files and command-line credentials are shared. "The computer is assigned to your user account, not an individual Bot." — [docs.x.ai Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)
- Per-Bot screens: each Bot gets its own screen, but "one Bot can run only one computer-use task on its screen at a time". Screens are not security boundaries. — [docs.x.ai Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)
- Inconsistency within the docs: they first say each Bot has "a computer of its own", then clarify it is "one shared machine per account". — [DataCamp](https://www.datacamp.com/blog/grok-bot), quoting SpaceXAI docs
- Press and 3P sources still describe it as each Bot having "its own virtual machine" / "a real virtual machine". The current official docs contradict this: the computer is per account. — [ultrathink](https://ultrathink.ai/news/grok-bot-early-beta-cursor-spacexai) and [aibuilderclub guide](https://www.aibuilderclub.com/blog/grok-bot-guide), contradicted by [docs.x.ai overview](https://docs.x.ai/grok-bot/overview)

**Files, persistence and recovery**
- Shared durable workspace is `/workspace`. "Treat temporary directories, manually installed packages, and uncommitted application state as replaceable." — [docs.x.ai Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)
- Recovery tools:
  - "Recover Grok Bot's Computer" appears only in the error state.
  - Settings → Updates → **Update** installs new software and keeps files.
  - **Reset** rebuilds from the last snapshot, so recent changes may be lost.
  — [docs.x.ai Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)
- Computers keep local files, browser sessions and browser data on a durable disk across sessions. Idle computers hibernate, which is not deletion. Connector tokens are never stored on the computer. — [docs.x.ai Security](https://docs.x.ai/grok-bot/security)
- Changelog v0.63.0 (Sep 29): deleted Bots now free their screens on the shared computer, so other Bots' browser actions no longer fail because every screen is taken. This suggests the number of screens is finite. — [x.ai changelog via search snippet](https://x.ai/changelog/bot)

**Working while you are away**
- "Closing the Grok Bot app or your laptop does not stop cloud work." — [docs.x.ai Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)
- Launch post: Bots keep working when you step away and "only come back to you when something needs a human decision". — [x.ai launch post](https://x.ai/news/introducing-grok-bot); [Barchart/launch coverage](https://www.barchart.com/story/news/3810959/spacexai-and-cursor-team-up-on-grok-bot-persistent-ai-agents-that-sign-into-your-apps)

**Computer use on sites with no API**
- Bots operate tools without clean APIs or MCP support. — [x.ai launch post](https://x.ai/news/introducing-grok-bot)
- VentureBeat: works on sites with "no clean API or MCP". Product employee Roman: "Grok Bot can finish the swing, because the work lands where a human would put it, in the actual tool." — [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month)

**Takeover (human-only steps)**
- Open **Agent Computer** from a conversation to view the desktop. — [docs.x.ai Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)
- The Bot may ask you to take over for passwords, passkeys, 2FA, CAPTCHAs, payment or identity checks, or sites requiring a human. Complete only the blocked step, then tell the Bot to continue. — [docs.x.ai Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)
- "Do not send a password or one-time code in ordinary chat." Secure secret requests are masked, excluded from the transcript and "not shown to the model". — [docs.x.ai Approvals, security, and privacy](https://docs.x.ai/grok-bot/approvals-security-and-privacy)
- Hardware security keys are usable when the setting is on:
  - On by default on macOS and Windows.
  - Not supported on Linux.
  - Each use requires approval.
  — [docs.x.ai Approvals, security, and privacy](https://docs.x.ai/grok-bot/approvals-security-and-privacy)
- Launch coverage: the subscriber signs into sites on that computer and the agent does not see the password. — [Barchart](https://www.barchart.com/story/news/3810959/spacexai-and-cursor-team-up-on-grok-bot-persistent-ai-agents-that-sign-into-your-apps)
- Example from an xAI employee: a Bot checks into flights when the window opens and hands back control for 2FA or CAPTCHA. — [DataCamp](https://www.datacamp.com/blog/grok-bot), citing Eric Zakariasson's X posts

**Limits**
- Sites may block automation, sessions may expire, and some steps require a human. The Bot then hands the step to you. — [docs.x.ai overview](https://docs.x.ai/grok-bot/overview)
- When a site re-requests verification, the Bot should "pause and notify you rather than attempting to bypass the check". — [docs.x.ai Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)
- 3P hands-on findings:
  - "Some sites block cloud datacenter addresses even after a correct login."
  - "The browser is flexible, but it is more fragile than a plugin."
  - Workaround: Settings → Computer → "Route egress through this desktop" sends the cloud computer's traffic through your desktop IP.
  — [Flavio Copes deep dive, checked Sep 30, 2026](https://flaviocopes.com/grok-bot/)
- Recorded skills may "keep clicking the old spot without flagging it" when a site's layout changes. — [Layer3Labs review, updated Sep 9, 2026](https://www.layer3labs.io/guides/grok-bot-review)
- The local computer is separate from the cloud computer. "A Bot only runs commands on your local computer when that capability is enabled and you approve it." Policy options (team admins can cap this):
  - Ask every time (default).
  - Always allow.
  - Never allow.
  — [docs.x.ai Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps); [docs.x.ai Approvals](https://docs.x.ai/grok-bot/approvals-security-and-privacy)

### Inferences
- "Each Bot has its own computer" (launch marketing and press) became "each Bot has its own screen on one shared account computer" in the docs. For product-design comparisons, the real unit of isolation is the user account, not the Bot.
- The egress-through-desktop option and the "datacenter IP blocked" reports suggest bot-blocking is a material practical limit for consumer sites.

### Gaps
- No published hardware specs (CPU, RAM, disk, OS image) for the cloud computer.
- No published maximum number of screens per account.
- Encryption at rest and in transit is asserted in launch coverage but is not detailed on the security page. The page mentions only encrypted backups of the control plane.

---

## 2. Teach a task (learning by demonstration)

### Takeaway
"Teach a task" is officially documented, but it may be rolled out gradually. The flow:

1. In a one-to-one Bot chat, open the computer view and start recording.
2. Describe the intended result.
3. Perform the workflow once.
4. The recording captures visible computer interactions only, up to 10 minutes, with no microphone audio.
5. The Bot drafts a skill.

The skill is explicitly a draft. The user must add decision rules, failure handling and approval boundaries, then test it on a safe example before scheduling. Corrections over time are described in marketing, but no docs section covers them.

### Cited Findings
- Official steps:
  1. Open a one-to-one Bot conversation and its computer view.
  2. Start "Teach a task".
  3. Describe the intended result.
  4. Perform the workflow once.
  5. Stop recording.
  6. Review the generated skill.
  7. Test on a safe example before scheduling.
  — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Recording limits: captures "visible computer interaction" for up to ten minutes and does not capture microphone audio. Credentials go through the secure handoff flow, not the demonstration. — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Draft status: the learned skill is "a draft". You should add decision rules, failure handling and approval boundaries. — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Availability: the control "may be rolled out gradually". If it is missing, ask the Bot to build a skill from written instructions. — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Mobile: "teach-by-demonstration workflows are not available on mobile". — [docs.x.ai Mobile](https://docs.x.ai/grok-bot/mobile)
- Launch post framing: a Bot can watch you perform a task, save it as a routine, take corrections and repeat it later. — [x.ai launch post](https://x.ai/news/introducing-grok-bot)
- VentureBeat: users can correct a routine and the Bot incorporates the corrections. The article does not say how demonstrations are captured. — [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month)
- Composio guide (Aug 20): describes it as a browser workflow ("where enabled, the user performs a browser workflow once while the Bot watches"). — [Composio guide](https://composio.dev/content/guide-to-frok-bot)
- Flavio Copes: "Start recording, perform the workflow yourself, and let the Bot observe the visible interactions." — [Flavio Copes](https://flaviocopes.com/grok-bot/)
- Layer3Labs recommends reviewing the first few runs of a new skill before letting it run unattended. — [Layer3Labs review](https://www.layer3labs.io/guides/grok-bot-review)

### Inferences
- The draft-skill design (record, then review and test) treats demonstration as a source of evidence, not authority. Approval boundaries are added by hand.
- Corrections appear to flow through normal chat and Bot memory rather than a dedicated "correction" feature. No official mechanism is documented.

### Gaps
- Whether the recording is pixel-level screen video or a structured action log is not published. Docs say only "visible computer interaction".
- The skill file format produced by Teach a task is not documented.

---

## 3. Skills, routines, triggers, Grok Automations and slash-command skills

### Takeaway
- **Skill**: a reusable set of instructions covering when to use it, inputs and access, sequence, validation, output and what needs approval. It works on any Bot with the right access, is invoked with `/`, and lives in a private library shared across Bots or in the Marketplace.
- **Routine**: binds one workflow to one Bot "on a schedule or, where supported, after an event", such as Slack messages or GitHub notifications. Limits:
  - 50 routines per Bot.
  - The last 20 runs are kept.
  - Schedules must be at least 5 minutes apart.
  - Test run performs real work.
- **Lineage**: consumer Grok "Automations" (Jul 16, 2026) and Grok Build's skills and workflows are earlier, separate products.

### Cited Findings

**Skill definition and contents**
- A skill is "a reusable set of instructions for how to do a task". The page lists six elements:
  1. When to use it.
  2. Required inputs and access.
  3. Sequence of work.
  4. How to validate results.
  5. What to return.
  6. What needs approval.

  Skills can also include decision rules, expected output and safety boundaries.
  — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Composio summary: a skill includes "steps, decision rules, output requirements, and approval boundaries". — [Composio guide](https://composio.dev/content/guide-to-frok-bot)
- Flavio Copes suggests these contents: purpose, inputs, source priority, workflow, validation checks, output, failure behaviour, approval boundaries and examples. No file format is documented. — [Flavio Copes](https://flaviocopes.com/grok-bot/)

**Where skills live and how they are invoked**
- In the desktop composer, "/" references a saved skill and "@" references Bots, groups, routines and connectors. — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Private skills are "a single library shared across your Bots". If a skill is missing from "/", check Marketplace → Your plugins → Manage plugins and skills → "Private skills". — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Skills work on any Bot with the right access. — [DataCamp](https://www.datacamp.com/blog/grok-bot)

**Routines**
- A routine tells one Bot when to run a workflow, "on a schedule or, where supported, after an event". — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Event triggers: "Cursor account integrations" start routines from events such as Slack messages or GitHub notifications. These are separate from the Slack and GitHub plugins and may need their own connection. The docs advise narrow matching rules and warn that broad listeners add noise, usage and the risk of acting on irrelevant input. — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Triggers also include "supported reactions". "Every run consumes usage, even when the Bot wakes up and finds nothing." — [Flavio Copes](https://flaviocopes.com/grok-bot/)
- Limits:
  - Up to 50 routines per Bot.
  - The 20 most recent run records are kept per routine.
  - Schedules must be at least five minutes apart.
  - Deleting a routine is immediate and irreversible.
  - Deleting a Bot deletes its routines.
  - "Grok Bot may pause routines after a long absence without a response."
  — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Test run: tests "perform real work", including site navigation, file changes and connected-tool calls. Use safe inputs and keep write actions behind approval. — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Example prompts in the docs:
  - A "Weekly account health" skill.
  - A weekday 8:00 AM "Daily customer-risk" routine.
  - An event trigger on `#customer-escalations` messages containing a ticket link and "needs repro".
  — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- Use-case guidance: create a routine "only when retries and failure cases are defined". — [docs.x.ai Use cases](https://docs.x.ai/grok-bot/use-cases)
- On mobile you can review, pause, resume and delete routines. "Editing the schedule or instruction and testing a routine currently require the desktop app." — [docs.x.ai Mobile](https://docs.x.ai/grok-bot/mobile)
- MacRumors relays SpaceXAI's claim that no workflow or routine building is needed up front: you just message the Bot. — [MacRumors](https://www.macrumors.com/2026/08/11/grok-bot-macos-ios/)

**Grok Automations (consumer Grok app, the predecessor)** — [3P coverage](https://flowith.io/blog/grok-automations-scheduled-email-trigger-guide/); [aibase](https://www.aibase.com/news/29671); [blockchain.news](https://blockchain.news/news/grok-automations-scheduled-tasks)
- Launched Jul 16, 2026 at grok.com/automations, in the web and mobile apps.
- Saved prompt that runs on a schedule (once, daily, weekdays, weekly, monthly, yearly) or when a matching email arrives (filter on sender, recipient or subject).
- Each run is a new session saved in run history.
- Notifications by email, app notification, both, or neither.
- Plan gating: reports say scheduled runs are free and email triggers require SuperGrok, but sources conflict.
- I found no xAI primary post for this.
- Composio confirms the lineage: "scheduled Automations added to Grok in July, then large parallel workflows added to Grok Build". — [Composio guide](https://composio.dev/content/guide-to-frok-bot)

**Slash-command skills (Grok Build, the coding CLI)**
- Skills are folders of markdown instructions, scripts and resources. A skill with `user-invocable: true` in `SKILL.md` frontmatter becomes a slash command (e.g. `/commit`). Name collisions are resolved as `/local:commit` or `/user:commit`. — [docs.x.ai Build: Skills, Plugins & Marketplaces](https://docs.x.ai/build/features/skills-plugins-marketplaces) (via search summary)
- "Grok Skills" for consumer Grok, as a modular instruction set called by slash command with .zip/.skill/.md import, is described only in a social post. — [Threads post](https://www.threads.com/@artificiallyinfluenced/post/DYSIwAsjDNg/what-grok-skills-actually-is-skills-are-modular-reusable-instruction-sets/)

### Inferences
- Three separate "skill/automation" systems exist across the xAI/Cursor family:
  - Grok app Automations (timer or email).
  - Grok Build's SKILL.md skills and workflows.
  - Grok Bot skills and routines (cloud computer plus approvals).
- Grok Bot's design looks like a merger of the first two, with a computer and approval layer added.
- Grok Bot event triggers are implemented via Cursor account integrations, consistent with Cursor-run infrastructure.

### Gaps
- No official file format or export of Grok Bot skills.
- No official xAI post found for Grok Automations (Jul 16 date is from 3P).
- The full list of supported trigger event sources is not documented beyond Slack and GitHub (plus "reactions" per Flavio Copes).

---

## 4. Proactivity and notifications

### Takeaway
At launch, proactivity was a marketing claim: Bots "learn when to ping vs keep going", nudge stalled handoffs and pick up work before you ask. It became a concrete feature on Oct 1, 2026 with **Primary Bot**:
- One starred Bot per user.
- It looks around connected apps, inboxes and files, offers work without being asked, and routes tasks to specialist Bots.

As of early October, interruption rules and how to disable proactivity are undocumented.

### Cited Findings

**Launch-era claims**
- Bots "pick up your voice, your edge cases, and know when to ping versus keep going". They "follow up on threads you dropped, nudge a stalled handoff, and pick work back up from previous conversations". Over time they become "more proactive, picking up work before you need to ask and knowing when something needs your attention." — [x.ai launch post](https://x.ai/news/introducing-grok-bot) (via search snippet)
- VentureBeat: SpaceXAI says Bots learn when to ask for approval vs proceed alone, and "sometimes find work before being asked". — [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month)

**Primary Bot (Oct 1, 2026)**
- Announced in an official @bot post on X. Quotes:
  - "Grok Bot can now suggest ways to help without you needing to ask."
  - "Your primary Bot will spot work it can take off your plate and offer to handle it."
  - Onboarding screen: "Primary Bot does work proactively"; it "checks in when it needs your help".
  - First message: "I'm taking a look around to see if there's anything I can pick up for you. I'll follow up in a moment."
  - Suggestions are said to be free. Whether executing them consumes usage is unclear.
  — [progressiverobot.com, Oct 2, 2026](https://www.progressiverobot.com/2026/10/02/primary-bot-grok-4-7-base-model-proactive-grok-bot/) (relays the @bot post plus TestingCatalog screenshots)
- Real-world example: Matt Palmer (SpaceXAI) said Grok Bot flagged an Uber reservation still tied to his old flight and pinged him mid-flight. — [progressiverobot.com](https://www.progressiverobot.com/2026/10/02/primary-bot-grok-4-7-base-model-proactive-grok-bot/)
- Mechanics: "only one Primary Bot", shown with a star badge in the sidebar. You can create a new one or promote an existing Bot. Removing it requires "Replace with different Bot". — [Flavio Copes](https://flaviocopes.com/grok-bot/); [progressiverobot.com](https://www.progressiverobot.com/2026/10/02/primary-bot-grok-4-7-base-model-proactive-grok-bot/)
- As of Oct 2 there was no Primary Bot mention in the nine docs pages, and no detail on interruption frequency, monitored signals, or how to limit or disable it. — [progressiverobot.com](https://www.progressiverobot.com/2026/10/02/primary-bot-grok-4-7-base-model-proactive-grok-bot/)
- A user-written guide describes Primary Bot periodically checking other Bots, nudging a stalled Bot once, staying quiet while work moves and contacting you only when needed. This is not official. — [search snippet, botskills.sh/flavio](https://botskills.sh/blog/grok-bot-stalled)
- A customer story on xAI's site describes Bots watching a cloud coding agent and unblocking it when it stalls: "one-off flakiness rarely reaches me at all". — [x.ai guide: Grok Bot for Engineering](https://x.ai/bot/guides/grok-bot-for-engineering) (via snippet)

**Notifications and interruptions**
- Mobile notifications fire when a Bot has a result, a question or an approval request. — [docs.x.ai Mobile](https://docs.x.ai/grok-bot/mobile)
- Aug 18 update: grouped mobile notifications. — [4geeks tracker](https://4geeks.com/en/blog/ai-tools/grok-bot-news-and-updates)
- "A direct message from you takes priority over background work and can redirect the current turn." "Stop now" ends work immediately but does not undo completed actions. — [docs.x.ai Chat and collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration)
- Feedback tuning in the Chief of Staff use case: "Tune the Bot by marking what was useful and what was noise." — [docs.x.ai Use cases](https://docs.x.ai/grok-bot/use-cases)

### Inferences
- Proactivity is implemented as "suggest then accept" (an offer to handle), which keeps approval in the loop.
- The launch "learns when to interrupt" claim has no documented mechanism. It is likely memory/preference-driven rather than a configurable policy.

### Gaps
- No official docs on Primary Bot, proactivity controls or interruption thresholds as of the research date.

---

## 5. Memory

### Takeaway
Each Bot keeps its own memory: stable preferences, role context, important facts and summaries of prior work. Conversations and learned context are separate per Bot. Context moves between Bots only through shared files, browser sessions, group messages and handoffs. Team Bots add shared team memory plus private per-person notes.

The docs warn that memory is "not a substitute for an authoritative source". User-facing memory view, edit or delete controls are not documented.

### Cited Findings
- A named Bot keeps memory, files, browser sessions and preferences across sessions. Per the FAQ, it remembers stable preferences, role context and summaries of prior work. Conversations and learned context stay separate per Bot. — [docs.x.ai overview](https://docs.x.ai/grok-bot/overview)
- "Memory is not a substitute for an authoritative source." Keep changing facts in the source system and ask the Bot to reopen current data for consequential decisions. — [docs.x.ai Work with Grok Bot](https://docs.x.ai/grok-bot/bots)
- Docs advise against a broad job like "General Helper" because it makes saved context harder to reuse. — [docs.x.ai Work with Grok Bot](https://docs.x.ai/grok-bot/bots)
- Learning voice and edge cases: Bots "pick up your voice, your edge cases" (launch). They remember prior conversations and learn writing voice and edge cases (VentureBeat). — [x.ai launch post](https://x.ai/news/introducing-grok-bot); [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month)
- Team Bots: "Team memory is read by everyone. Personal notes stay private to each person." — [docs.x.ai Team Bots](https://docs.x.ai/grok-bot/team-bots)
- Flavio Copes on Team Bots: "Every conversation reads team memory", but the Bot writes to it only when someone asks. Also: "Sharing a computer does not mean sharing conversational memory." — [Flavio Copes](https://flaviocopes.com/grok-bot/)
- Matt Palmer (Cursor) described three memory layers on X: user, individual Bot and shared project ("Projects"). This is not in the official docs. — [DataCamp](https://www.datacamp.com/blog/grok-bot)
- Hands-on: memory persists and earlier corrections are applied when resuming work (e.g. an email-triage preference set once). — [Layer3Labs](https://www.layer3labs.io/guides/grok-bot-review)
- Team Bots launch post: "Memories help it retain what it learns and improve at its role over time." — [releasebot, quoting x.ai Sep 28 post](https://releasebot.io/updates/xai)
- Resuming threads:
  - Search and the command palette jump to prior messages.
  - Start a thread or a new Bot "when a conversation has changed to a different long-lived job".
  — [docs.x.ai Chat and collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration)

### Inferences
- Memory scope follows the role. That is why the docs push one clear job per Bot: role-scoped memory is the main way Bots specialise.

### Gaps
- No documented UI to view, edit or delete Bot memory, and no memory retention policy.

---

## 6. Multi-agent: named Bots, group chats, handoffs, Chief of Staff, prebuilt roles, Team Bots

### Takeaway
- **Named Bots**: each has a name, label, description and avatar. Docs recommend one clear job per Bot.
- **Group chats**: 2 to 6 Bots. Bots decide who answers; `@` targets one Bot and `@everyone` targets all.
- **Handoffs**: asynchronous Bot-to-Bot messages that pass ownership.
- **Chief of Staff**: an orchestrator pattern, used internally at SpaceXAI, which later became a product feature as Primary Bot.
- **Prebuilt roles**: eight documented in Use cases.
- **Templates**: shareable via public or team link, with a marketplace launched Sep 4.
- **Team Bots** (Sep 28, Teams/Enterprise): one shared Bot with its own Slack app, private per-user chats and admin assignment.

### Cited Findings

**Creating Bots**
- New → Create new Bot (Cmd/Ctrl+N). Edit Profile sets name, label, description and avatar. Recommended clear jobs include Talent Scout, Expense Manager and Bug Reproduction. Account Health example: "Own the weekly account-health review." — [docs.x.ai Work with Grok Bot](https://docs.x.ai/grok-bot/bots)
- Limit: Bots and group chats combined up to 50. — [Flavio Copes](https://flaviocopes.com/grok-bot/) (3P)

**Group chats**
- Groups suit work where "several Bots need one shared outcome and visible handoffs". Size: "select two to six Bots". — [docs.x.ai Chat and collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration)
- Addressing:
  - Writing normally lets Bots decide who responds.
  - `@Bot` targets one Bot.
  - Reply targets a message.
  - `@everyone` should be used "sparingly".
  — [docs.x.ai Chat and collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration)
- Approval requests, secret and login requests, and email or Slack drafts do not appear in a group. — [docs.x.ai Chat and collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration)
- Behind the scenes the host "still wakes each member in turn". — [Flavio Copes](https://flaviocopes.com/grok-bot/)

**Handoffs**
- "A Bot can send an asynchronous message to another Bot." "Ask for a single owner at each stage", because too many parallel handoffs cause duplicate work. "Bot-to-group handoff messages are currently text-only." — [docs.x.ai Chat and collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration)
- Bots can "pass ownership of a task" without you routing between them. — [DataCamp](https://www.datacamp.com/blog/grok-bot), quoting docs
- Recommended handoff contents: output path, evidence, open questions, next owner. — [Flavio Copes](https://flaviocopes.com/grok-bot/)
- Example: an engineering Bot reproduces a bug in the product UI, files a ticket and hands the fix to a debugging Bot. — [MacRumors](https://www.macrumors.com/2026/08/11/grok-bot-macos-ios/); [x.ai launch post](https://x.ai/news/introducing-grok-bot)

**Chief of Staff**
- Internally, SpaceXAI runs a "chief of staff" Bot over specialists for inbox, recruiting, expenses, operations and bug fixes. — [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month)
- The launch demo used Research, Communications, Chief of Staff and Travel Bots. — [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month)
- Matt Shumer: "It worked out of the box." He called orchestration a top feature: "an agent for everything, not just code." — [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month)

**Prebuilt roles (official Use cases page)** — all from [docs.x.ai Use cases](https://docs.x.ai/grok-bot/use-cases)

| Role | What it owns and returns | Connects to | Boundary |
|---|---|---|---|
| Sales Outbound | Account research and contact prioritisation; returns a review-ready list. Nightly routine "stops at the review list". | CRM, intent data, websites, email, professional networks "as permitted by their terms" | "do not send or enroll anyone" |
| Talent Scout | Sourcing, candidate research, outreach drafts, scheduling prep | ATS, approved sourcing tools, email, calendar | "Add approvals before external outreach" |
| Paid Media | Campaign monitoring and budget recommendations; returns reallocation recommendations and a draft Slack update | Ad platforms, analytics, budget sheet, Slack | "Keep campaign changes behind approval even after the analysis becomes a routine" |
| Expense Manager | Weekly reconciliation; returns a summary and one draft follow-up per owner. Exceptions need policy citations. | Expense system, email, drive, finance sheets | "do not send messages or change reimbursements" |
| Product Performance | Investigations that separate facts from hypotheses; recurring health report | Observability, analytics, incidents, source control | "Do not change alerts or production settings" |
| Bug Reproduction | Repro packs: steps, expected vs actual, minimal test case | Issue tracker, staging, browser, network tools | No production customer data; test credentials via secure handoff |
| Account Health | Ranked watch list with evidence; thresholds defined in the Bot description | CRM, usage, support, billing, CS notes | "Do not contact customers or edit the CRM" |
| Chief of Staff | Source-linked digest; "Return only items that map to the priorities in this document" | Slack, email, calendar, meeting notes, planning docs | "Do not send messages or change meetings" |

**Templates and marketplace**
- Share menu → Create template, as a Public link or Team-only (Enterprise defaults to Team-only). The shared config includes identity, description, skills and routines, not the computer or logins. — [docs.x.ai Work with Grok Bot](https://docs.x.ai/grok-bot/bots); [docs.x.ai Approvals](https://docs.x.ai/grok-bot/approvals-security-and-privacy)
- Sep 4: Bot template marketplace launched with "Haggle Bot" (procurement). It claims more than $100k in internal savings. — [4geeks tracker](https://4geeks.com/en/blog/ai-tools/grok-bot-news-and-updates) (3P relay)

**Team Bots (public beta Sep 28, 2026, Teams and Enterprise plans)**
- Launch: "Team Bots is available today in public beta on Teams and Enterprise plans". Each Bot has its own Slack handle and each user's conversations stay private. "Plugins let it work in applications such as Salesforce, Notion, and GitHub." — [releasebot, quoting x.ai](https://releasebot.io/updates/xai); [Codersera](https://codersera.com/blog/grok-bot-complete-guide-2026/)
- Setup: the owner configures plugins, secrets, skills and files, then publishes (or uses Share → "Publish to Team"). Teammates use it in desktop, mobile and Slack. — [docs.x.ai Team Bots](https://docs.x.ai/grok-bot/team-bots)
- Plugins and MCP:
  - OAuth plugins use each teammate's own account.
  - Key-configured plugins use the Bot's shared credential.
  - Command-based MCP servers run on the conversation's computer and should not contain credentials.
  — [docs.x.ai Team Bots](https://docs.x.ai/grok-bot/team-bots)
- Secrets: up to 25 per Bot, 8 characters to 4,096 bytes each, used by name and redacted in output. Files: .txt, .md, .csv, .json, .yaml, up to 256,000 characters each. — [docs.x.ai Team Bots](https://docs.x.ai/grok-bot/team-bots)
- Where work runs:
  - The owner's chat runs on the owner's computer.
  - Each teammate's chats run on that teammate's computer.
  - Slack channels and group conversations run on one shared computer.
  — [docs.x.ai Team Bots](https://docs.x.ai/grok-bot/team-bots)
- Connector consent in shared conversations: Allow once / Always allow for this Bot / Always allow for all Team Bots / Skip. Routines are personal. — [docs.x.ai Team Bots](https://docs.x.ai/grok-bot/team-bots)
- Slack:
  - Each Team Bot gets its own Slack app, named after the Bot, which posts as itself.
  - It answers all DMs, responds to @mentions in channels and then follows that thread.
  - Teammates link Slack under Settings → General → Team Bots.
  - Setup can show "Awaiting admin approval".
  — [docs.x.ai Team Bots](https://docs.x.ai/grok-bot/team-bots)
- Usage and admin:
  - Usage counts against each teammate. Routines count against their creator. Unlinked Slack sources count against the owner.
  - Admins use "Manage Team Bots" to assign Bots to everyone, no one or groups.
  - Enterprise audit logs record Team Bot events.
  — [docs.x.ai Team Bots](https://docs.x.ai/grok-bot/team-bots)
- Sep 30 changelog: v0.64.0 added Team Bot managers; v0.65.0 added Team Bot voice chat. — [x.ai changelog via search snippet](https://x.ai/changelog/bot); [runtimewire](https://runtimewire.com/article/grok-bot-team-bot-managers-voice-calls)

### Inferences
- Coordination is message-based (async DMs, group threads, single-owner handoffs), not an explicit DAG/workflow engine.
- Risk to note: one Bot's bad output can propagate to another Bot before a human notices. — [DataCamp](https://www.datacamp.com/blog/grok-bot)

### Gaps
- No published orchestration internals. Composio explicitly says its architecture diagram is "conceptual".

---

## 7. Permissions, approvals and security

### Takeaway
- **Per-action approval cards**: Allow once / Always allow / Deny.
- **Rule-based Auto Review**: an independent review model that evaluates shell commands, plugin calls, computer use, automation writes and delegation before they run. It can allow, require approval or deny. "Ask first" wins conflicts.
- **Recommended practice**: keep sending, publishing, purchasing, deleting, permission changes, production changes and legal terms behind approval.
- **Security boundary**: the account, not the Bot. A Bot "can never hold more access than the person it belongs to".
- **Enterprise controls**: network allowlists, Action Recording, OTel export, audit logs, enforced Auto Review.

### Cited Findings

**Approvals**
- Bound actions in your request, especially:
  - Sending messages.
  - Publishing.
  - Purchases.
  - Deleting or overwriting data.
  - Changing permissions.
  - Production changes.
  - Accepting legal terms.

  "An approval controls the proposed action. It does not reverse work already completed."
  — [docs.x.ai Approvals, security, and privacy](https://docs.x.ai/grok-bot/approvals-security-and-privacy)
- Approval cards: Allow once, Always allow, Deny. Approvals from routines, triggers or other Bots expire after about 10 minutes. — [docs.x.ai Approvals](https://docs.x.ai/grok-bot/approvals-security-and-privacy)
- Reviewers should not approve an action whose target or effect they cannot identify. Recommended practice:
  - Connect only the tools needed.
  - Start with read-only tasks and drafts.
  - Review active routines and pause them when the source system changes.
  — [docs.x.ai search summary of approvals page](https://docs.x.ai/grok-bot/approvals-security-and-privacy)
- Drafts: Bots prepare "New Email" / "New Slack Message" cards you send or discard. Voice memos and drafts are approved before sending. — [docs.x.ai Mobile](https://docs.x.ai/grok-bot/mobile); [docs.x.ai overview](https://docs.x.ai/grok-bot/overview)
- 1Password (Sep 16): the Bot can use items shared in a vault, and each fill requires approval. — [4geeks tracker](https://4geeks.com/en/blog/ai-tools/grok-bot-news-and-updates)

**Auto Review**
- Location: Settings → General → Auto-review. It evaluates tool calls and computer actions before they run.
- "Ask first" rules always stop matching actions and win over "Allow automatically".
- It is model-based, so it complements least privilege rather than replacing it.
- Personal rules are stored on the desktop and synced to the computer.
- — [docs.x.ai Approvals](https://docs.x.ai/grok-bot/approvals-security-and-privacy)
- It covers shell commands, plugin calls, computer use, "automation writes" (changes to routines and triggers) and delegation (Cloud Agent and subagent launches). "It can let an action proceed, require approval, or deny it." "It does not review every side effect." Personal rules can only make behaviour stricter. Enterprise admins can enforce it and add locked team rules. — [docs.x.ai Security](https://docs.x.ai/grok-bot/security)
- 3P warning against broad rules like "always allow browser actions". — [Flavio Copes](https://flaviocopes.com/grok-bot/)

**Isolation and credentials**
- All Bots share one cloud computer, so "Don't treat separate Bots as a security boundary." Sign out, remove temp files and revoke connectors when they are no longer needed. Deleting a Bot does not remove shared-computer files or sessions. — [docs.x.ai Approvals](https://docs.x.ai/grok-bot/approvals-security-and-privacy)
- "The isolation boundary is your account." — [DataCamp](https://www.datacamp.com/blog/grok-bot), quoting docs
- "A Bot can never hold more access than the person it belongs to." Bots have no identity or credentials of their own, except team-managed connectors. Bots invoke tools without receiving OAuth tokens, which stay on Cursor's backend. — [docs.x.ai Security](https://docs.x.ai/grok-bot/security)

**Enterprise controls (Enterprise only)** — [docs.x.ai Security](https://docs.x.ai/grok-bot/security)
- Audit Logs, with SIEM streaming.
- Action Recording: off by default, includes scrubbed shell commands, 90-day retention.
- OpenTelemetry export tagged `cursor.surface=grok_bot`.
- Opt-in conversation export with secret and email redaction.
- Network Controls, including "Team Allowlist Only".
- Team Secrets.
- Allow Local Egress.
- Team model allowlist, where enforcement is "not guaranteed".

**Data, training and compliance** — [docs.x.ai Approvals](https://docs.x.ai/grok-bot/approvals-security-and-privacy); [docs.x.ai Security](https://docs.x.ai/grok-bot/security)
- Uses Cursor auth and data settings. It requires data storage and does not support Legacy Privacy Mode.
- With Privacy Mode, customer data is not used for training.
- Providers operate under Zero Data Retention.
- ISO 27001 and ISO 42001 (Anysphere, Schellman) include Grok Bot in scope.
- Computers run in the US, without a US-only residency commitment by default.

**Gaps noted by press and reviewers**
- At launch, an audit view was listed as coming, not shipped, and there was no Grok Bot-specific spend cap. — [DataCamp](https://www.datacamp.com/blog/grok-bot)
- Launch coverage said SpaceXAI hadn't detailed how authentication works. — [MacRumors](https://www.macrumors.com/2026/08/11/grok-bot-macos-ios/)
- Enterprise concern: the product reaches staff through consumer subscriptions rather than security review. — [beam.ai](https://beam.ai/agentic-insights/grok-bot-enterprise-ai-agents)

### Inferences
- The approval model is layered:
  1. The user's prompt boundaries.
  2. Skill-level approval boundaries.
  3. Per-action cards.
  4. Model-based Auto Review rules.
  5. Enterprise-enforced team rules and network policy.
- Deterministic controls (per-user isolation, network policy, token custody on backend) are explicitly separated from model-judgment controls (Auto Review).

### Gaps
- No published Auto Review model identity or accuracy figures.
- At-rest encryption of the cloud computer is not documented on the security page.

---

## 8. Connectors: plugins, MCP, Composio, marketplace; connector vs browser login

### Takeaway
- **Connectors**: installed as plugins from the in-app Marketplace (Add, then authenticate). They are account-wide and attached in chat with `@`.
- **Preference**: the docs say "Prefer a connector when one is available". The browser is the fallback for services without one, or for visual work.
- **MCP**: command-based MCP servers run on the computer. Composio is installable from the Marketplace for 1,000+ apps with OAuth.
- **Additions**: Microsoft (Outlook, Calendar, OneDrive) on Aug 31; 1Password on Sep 16; multiple accounts per plugin on Aug 18.

### Cited Findings
- Connectors give structured access to supported services. Install them as plugins from **Marketplace** → **Add** → authenticate. Type `@` to attach a connector and `/` for skills. "Prefer a connector when one is available." Use the browser for services without a connector or for visual workflows. Installed connectors are account-wide. — [docs.x.ai Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)
- Marketplace (sidebar) holds supported connectors and packaged skills. — [docs.x.ai Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
- "Plugins expose structured application actions to the Bot." They are compared to MCP servers and are usually better than browser automation.
  - API-key connectors use a secure credential field. Grok Bot "stores the value separately and makes it available only to that connector".
  - Connectors can be attached to multiple accounts, so specify which one to use.
  - Fix for plugin problems: reconnect and test one read operation.
  — [Flavio Copes](https://flaviocopes.com/grok-bot/)
- Command-based MCP servers run on the conversation's computer and should not contain credentials (Team Bots). — [docs.x.ai Team Bots](https://docs.x.ai/grok-bot/team-bots)
- Composio:
  - Install via **Settings → Plugins → Marketplace**.
  - Tool discovery and execution "across more than 1,000 apps", with user-scoped OAuth and auto-refresh.
  - On-demand connection: the Bot asks the user to approve an account in the browser, then reuses it.
  - Composio Search is a no-auth toolkit.
  - Composio MCP Gateway restricts access by org, team, user or action and logs calls.
  - Guidance: direct site sign-in can suffice for one site, but multi-service workflows are easier through Composio.
  - In the author's test, Slack and Linear were unconnected, so the Bot requested a one-click connect.
  — [Composio guide, Aug 20, 2026](https://composio.dev/content/guide-to-frok-bot) (vendor content; the homepage says "1,500+ apps", which conflicts with the body's "1,000+")
- Connector timeline:
  - Aug 18: multiple accounts per plugin and an improved plugins marketplace.
  - Aug 31: Microsoft plugins (Outlook, Calendar, OneDrive).
  - Sep 16: 1Password.
  — [4geeks tracker](https://4geeks.com/en/blog/ai-tools/grok-bot-news-and-updates)
- Third-party plugins exist, e.g. a macOS iMessage skill using a local launchd helper bridge (unaffiliated). — [GitHub jeffhuber/grokbot-imessage-skill](https://github.com/jeffhuber/grokbot-imessage-skill)
- Removing access: uninstall connectors **and** revoke authorisation in the source service. — [docs.x.ai Approvals](https://docs.x.ai/grok-bot/approvals-security-and-privacy)
- Cursor Teams Premium includes a team marketplace for skills and plugins. — [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month)

### Inferences
- The layering is: connector or plugin (structured, OAuth on the backend), then MCP (on the computer), then browser login (fallback). This mirrors Cursor's plugin/MCP stack.

### Gaps
- No official list of first-party connectors was retrieved.
- No official page documenting remote (non-command) MCP configuration was retrieved.

---

## 9. Channels and apps; Cursor relationship; SpaceXAI branding; Grok Build

### Takeaway
The UI is a messaging app ("iMessage-like"):
- Bots in a left sidebar, conversation in the centre, and a right panel with settings, the Bot's screen and routines.
- Text, dictation, voice chat and voice memos.
- Approval and draft cards.

Platforms grew quickly after launch:

| Date | Platforms |
|---|---|
| Aug 11 (launch) | macOS + iPhone (iOS 18+); Windows per docs |
| Sep 2 | Android 9+ |
| Current docs | macOS, Windows and Linux desktop; iPhone, iPad and Android mobile |
| Sep 28 | Slack, via Team Bots |
| Current docs | @bot on X |

The product is SpaceXAI-branded but built, hosted, billed and authenticated through Cursor (Anysphere). Access expanded from top tiers only (Aug 11) to Cursor Pro, Pro+, Ultra and Teams plus SuperGrok/Plus/Heavy (Aug 26). Grok Build is a separate xAI coding CLI.

### Cited Findings

**Apps and UI**
- Interaction is by text, dictation or voice chat. — [docs.x.ai overview](https://docs.x.ai/grok-bot/overview)
- Text-thread interface on mobile or desktop. — [x.ai news Aug 26](https://x.ai/news/grok-bot-more-plans)
- Layout: "Your bots are listed on the left. The conversation sits in the center. A panel on the right holds the bot's settings, its screen, and its routines." The interface is "similar to iMessage". — [search summary of 3P sources incl. aibuilderclub](https://www.aibuilderclub.com/blog/grok-bot-guide); [RetroChainer X article](https://x.com/RetroChainer/article/2091204446394929533) (3P)
- Chat features:
  - Pasted text, links, images, files, dictation, voice chat and `/` skills.
  - Threads ("Reply in a thread when feedback applies to one result or one approval request").
  - Reactions.
  - Voice memos with transcript.
  - "Start voice chat".
  — [docs.x.ai Chat and collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration)
- Voice timeline: Sep 17 voice; Sep 18 Bot voice notes; Aug 18 Command-D dictation. — [4geeks tracker](https://4geeks.com/en/blog/ai-tools/grok-bot-news-and-updates)

**Mobile**
- Mobile uses the same Bots, conversations, routines, connectors and shared computer as desktop.
- Requirements: iOS 18+ or Android 9+ (current page also lists iPad on iPadOS 18+).
- Features:
  - Computer view with takeover.
  - Routine review, pause and delete.
  - Search.
  - Email and Slack draft cards.
  - Notifications.
- Limits:
  - Routine editing and testing are desktop-only.
  - No teach-by-demo on mobile.
  - The Android share sheet accepts text only.
- — [docs.x.ai Mobile](https://docs.x.ai/grok-bot/mobile)

**Platform conflicts by date**

| Date | Claim | Source |
|---|---|---|
| Aug 11 | macOS and iOS | [MacRumors](https://www.macrumors.com/2026/08/11/grok-bot-macos-ios/) |
| Launch-era docs | macOS, Windows, iPhone; no Linux, Android or iPad | [DataCamp](https://www.datacamp.com/blog/grok-bot); [Composio](https://composio.dev/content/guide-to-frok-bot) |
| Press | macOS, Windows, Linux, iOS; Android "coming soon" | [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month) |
| Sep 2 | Android on Google Play | [4geeks](https://4geeks.com/en/blog/ai-tools/grok-bot-news-and-updates) |
| Current docs | Desktop: macOS (Apple silicon/Intel), Windows (x64/Arm64), Linux (x64/Arm64). Mobile: iPhone, iPad, Android | [docs.x.ai overview](https://docs.x.ai/grok-bot/overview) |

- Linux timing is disputed by third parties. — [whiskerbeacon](https://whiskerbeacon.com/changelog/); [cellcog](https://cellcog.ai/blog/what-is-grok-bot/)

**Cross-device continuity**
- Message from phone or desktop and continue the same conversation. — [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month)
- "Work continues in the cloud when the app is closed." — [docs.x.ai Mobile](https://docs.x.ai/grok-bot/mobile)

**X and Slack**
- Tag @bot on X: your main Bot picks up the post as a task and @bot replies publicly. This requires a connected X account and is not available in every region. — [docs.x.ai overview](https://docs.x.ai/grok-bot/overview)
- Slack arrives via Team Bots (see section 6).

**Cursor relationship**
- Hosting and identity:
  - Computers run in Cursor's cloud.
  - Grok Bot uses Cursor authentication and data settings.
  - Event triggers come from "Cursor account integrations".
  - Plans and billing live at cursor.com/help/grok-bot/plans.
  — [docs.x.ai overview](https://docs.x.ai/grok-bot/overview); [docs.x.ai Approvals](https://docs.x.ai/grok-bot/approvals-security-and-privacy)
- The macOS download points to `downloads.cursor.com` (or cursor.sh). The iOS app publisher is Anysphere. — [DataCamp](https://www.datacamp.com/blog/grok-bot); [x.ai launch post](https://x.ai/news/introducing-grok-bot); [roo.beehiiv analysis](https://roo.beehiiv.com/p/grok-bot-cursor-infrastructure) (3P)
- The Grok Bot computer is protected under Cursor's ISO certifications (Anysphere). Admin dashboard and SSO are Cursor's. — [docs.x.ai Security](https://docs.x.ai/grok-bot/security); [DataCamp](https://www.datacamp.com/blog/grok-bot)
- Corporate context:
  - SpaceX absorbed xAI (Feb 2026) and rebranded it SpaceXAI.
  - SpaceX agreed in June 2026 to buy Anysphere/Cursor for about $60B in stock.
  - Closing status conflicts: DataCamp said it was expected in Q3 and not confirmed, while another guide claims it closed Aug 14.
  — [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month); [DataCamp](https://www.datacamp.com/blog/grok-bot); [Wikipedia SpaceXAI](https://en.wikipedia.org/wiki/SpaceXAI)
- Origin: built first as an internal tool, used for sales outreach, marketing, onboarding, office ops and bug fixes. — [x.ai launch post](https://x.ai/news/introducing-grok-bot); [Composio](https://composio.dev/content/guide-to-frok-bot)

**Models**
- No model picker: "Cursor manages model selection." The router "wasn't great" at first, per Shumer. — [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month); [progressiverobot](https://www.progressiverobot.com/2026/10/02/primary-bot-grok-4-7-base-model-proactive-grok-bot/)
- Grok 4.5 was co-trained by SpaceXAI and Cursor in July. Grok 4.7 (Sep 21) was "trained to natively understand the Grok Bot harness". — [DataCamp](https://www.datacamp.com/blog/grok-bot); [releasebot](https://releasebot.io/updates/xai)
- The claim that Bots run Grok 4.6 is 3P-only and unconfirmed. — [layer3labs what-is](https://www.layer3labs.io/guides/what-is-grok-bot)

**Access and pricing timeline**

| Date | Eligible plans | Source |
|---|---|---|
| Aug 11 | SuperGrok Heavy ($300/mo), Cursor Ultra ($200/mo), Cursor Teams Premium ($120/seat/mo); enterprise waitlist | [VentureBeat](https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month) |
| Aug 26 | SuperGrok, SuperGrok Plus, SuperGrok Heavy, Cursor Pro, Pro+, Ultra, Cursor Teams Standard and Premium | [x.ai news](https://x.ai/news/grok-bot-more-plans) |
| Sep 3 | Enterprise availability with admin controls and two weeks of free usage | [4geeks](https://4geeks.com/en/blog/ai-tools/grok-bot-news-and-updates) |

- Bots have usage "separate from your Grok and Cursor plans". — [x.ai news](https://x.ai/news/grok-bot-more-plans)
- Usage resets weekly. — [docs.x.ai overview](https://docs.x.ai/grok-bot/overview)
- Plans do not stack. — [cursor.com help](https://cursor.com/help/grok-bot/plans), via search summary
- A weekly limit stalled a 3P multi-Bot "swarm" mid-task. — [Composio](https://composio.dev/content/guide-to-frok-bot)

**Grok Build (separate product)**
- xAI's terminal coding agent: reads the codebase, edits files, runs commands and spawns subagents in git worktrees.
- v1.0 on Aug 7, 2026; open source (Apache 2.0).
- Has SKILL.md skills, plugins, marketplaces and MCP.
- Composio places it in the lineage: "large parallel workflows added to Grok Build" before Grok Bot.
- Bots can delegate to "Cloud Agent" and subagents, which Auto Review covers.
- — [Wikipedia Grok Build](https://en.wikipedia.org/wiki/Grok_Build); [docs.x.ai Build skills](https://docs.x.ai/build/features/skills-plugins-marketplaces); [releasebot](https://releasebot.io/updates/xai); [docs.x.ai Security](https://docs.x.ai/grok-bot/security)

### Inferences
- **Why it is sold via Cursor**: Cursor (Anysphere, being acquired by SpaceX) supplies the cloud-computer fleet, auth/SSO, billing, admin dashboard, ISO-certified infrastructure, plugin/MCP marketplace and Cloud Agents. SpaceXAI supplies the brand and models (Grok 4.5 to 4.7, tuned to the Bot harness).
- **Two-company structure**: in effect, Grok Bot is a Cursor-operated product under SpaceXAI branding. This is supported by docs that still say "Cursor" throughout.

### Gaps
- No official statement explaining the strategic rationale for Cursor distribution was found.
- The current status of the Cursor acquisition closing is unconfirmed.
- The official changelog was inaccessible (403), so the exact versions and dates for Linux, iPad and @bot-on-X launches are unconfirmed.
- No official Android launch post was retrieved; the Sep 2 date is from a 3P tracker.
