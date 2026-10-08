# OpenAI "dots": how it works (product and architecture), as of 2026-10-08

Source-quality legend used below:
- **[OFFICIAL]** = OpenAI docs (learn.chatgpt.com "Meet dots" doc set, which developers.openai.com/codex/dots 308-redirects to) or OpenAI's launch post as quoted by the press. Note: openai.com/index/introducing-dots/ and help.openai.com returned HTTP 403 to my fetcher, so launch-post wording comes through search snippets and press quotes.
- **[PRESS]** = major or established tech press (TechCrunch, The Next Web, Axios via search snippet).
- **[FIRST-HAND]** = an eyewitness at DevDay (Simon Willison's live blog).
- **[SECONDARY/UNVERIFIED]** = blogs, aggregators, review sites, single-user reports, forum posts.

Key dates: dots announced at DevDay 2026 in San Francisco on **2026-09-29**. "Introducing dots" post is dated 2026-09-29. Hands-on and incident reports range from Oct 1 to Oct 7, 2026.

## Q1. Architecture: cloud computer, browser, user's PC, takeover, persistence, "always-on"

### Takeaway
Each dot is a cloud-resident GPT-6 Astra agent with its **own persistent cloud computer plus browser**, reportedly Linux with Chrome. It keeps working when the user's devices are off. The user can watch it, or press **"Take over"** and later **"Return control"**. The user can optionally connect **one** personal computer, which must stay online with the ChatGPT app open, so the dot can run local Work or Codex tasks. "Always-on" is built from three pieces: the agent can pause and wake itself, it can save schedules, and it can watch supported events. It also spawns parallel background agents. OpenAI says the product grew out of the Codex harness becoming reliable on long tasks.

### Cited Findings
**Core architecture**
- [OFFICIAL] Dots are "An always-on agent that keeps work moving and asks for your input when a decision needs you." It runs on GPT-6 Astra and "lives in the cloud with its own computer and browser," and it keeps working when the user's computer is off. — [Meet dots, learn.chatgpt.com](https://learn.chatgpt.com/docs/dots)
- [OFFICIAL] The cloud computer is used "for research, files, and running software." No hardware specs are published. It "keeps its state between periods of use" and has its own files, software, and browser sessions. — [Computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps)
- [SECONDARY] One review describes the cloud computer as a Linux machine with Chrome. — [eesel.ai review (Sep 30, 2026)](https://www.eesel.ai/blog/openai-dots-review)
- [OFFICIAL, via search snippet] The launch post says each dot runs on GPT-6 Astra, has its own cloud computer, improves from feedback, and works toward goals around the clock. — [Introducing dots](https://openai.com/index/introducing-dots/)
- [PRESS] The Next Web reports that users can open a dot's computer at any time to check its work. It also says the dot's computer stays separate from the user's unless the user chooses to connect it. — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [PRESS] TechCrunch says dots are designed to run "independent of any specific hardware or interface," pursuing user-defined goals in the background with little supervision. — [TechCrunch](https://techcrunch.com/2026/09/29/openai-launches-dots-its-bubbly-agentic-avatar/)
- [FIRST-HAND] Thibault Sottiaux (product lead for Codex, ChatGPT, ChatGPT Work and the API) said at DevDay that dots grew out of the Codex harness becoming more reliable on longer tasks (16:20). Sam Altman hopes users will talk to their dot during the day while it builds things in the background (16:29). Altman called Astra "our most aligned model" (10:09). — [Simon Willison DevDay 2026 live blog](https://simonwillison.net/2026/Sep/29/openai-devday-2026-live-blog/)
- [SECONDARY] GPT-6 Astra is reported to have a 1.05M-token context window and up to 128K output tokens. — [aggregated search result, multiple blogs](https://www.testingcatalog.com/openai-launches-dots-agents-powered-by-gpt-6-astra.md)

**Watching it work and taking over**
- [OFFICIAL] Users inspect the cloud computer under **Computers** in the dot's profile, or open it through a browser handoff. "Opening the computer doesn't give you control." **Take over** gives the user the mouse and keyboard, and **Return control** hands them back. — [Computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps)

**Website sign-in**
- [OFFICIAL] The dot uses "the same private sign-in flow as ChatGPT Work." When a login is needed, it sends a private form for credentials and any verification code. That data goes to the remote browser, not into the conversation. The user can also sign in personally via takeover, then select "Done."
- [OFFICIAL] Sessions persist until sign-out or expiry. **Save to Passwords** is optional, and reusing a saved login requires the user's confirmation.
- [OFFICIAL] Signing in on the user's own computer does not sign the dot in. Some sites block cloud browsers. — [Computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps); [Meet dots](https://learn.chatgpt.com/docs/dots)
- [PRESS] Dots "can sign in to supported websites with saved passwords without exposing those passwords to the model." — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)

**Working on the user's own computer**
- [OFFICIAL] Setup: in the ChatGPT app on that machine, open the dot's profile, choose **Your computer → Allow access**, then confirm.
- [OFFICIAL] Only **one personal computer at a time**. Access applies "wherever you message that dot, including from your phone."
- [OFFICIAL] The connection persists. The computer must stay online with the ChatGPT app open. "Offline" does not revoke access; only **Revoke access** does.
- [OFFICIAL] This permission is separate from connecting the computer to Codex or enabling Work Sync. — [Computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps)
- [OFFICIAL] If a site blocks the cloud browser, the user can ask the dot to try the connected computer. This creates a separate local task, the cloud session does not transfer, and "Local browser support isn't guaranteed." — [Computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps)
- [OFFICIAL, admin] Local computer access needs a separate admin opt-in. If any cloud policy has `enforce_residency` enabled, local computer access is unavailable for dots. Local sign-in, VPN, and device policies "don't automatically extend to the cloud computer." — [Dots admin guide](https://learn.chatgpt.com/docs/enterprise/dots-admin-guide)
- [FIRST-HAND] In a DevDay demo, the dot "Dottie" used Codex on a laptop to build an app and launch it in the iPhone Simulator (10:17). — [Willison live blog](https://simonwillison.net/2026/Sep/29/openai-devday-2026-live-blog/)

**How long-running work persists ("always-on")**
- [OFFICIAL] Dots "can pause and wake up on their own," so follow-ups don't need a fixed schedule. They can "start work at a specified time or in response to a supported event."
- [OFFICIAL] A dot can split work among parallel background agents that report back while the user keeps chatting. It can also open separate, visible cloud threads and send them follow-up instructions. — [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)
- [OFFICIAL] Task types the dot can create or continue:
  - new local task (needs a connected computer that is online);
  - existing local Codex task;
  - new cloud coding task in a pre-configured Codex cloud environment (the user's computer can be offline);
  - dot-created tasks, followed up through their original environment.
- [OFFICIAL] "Changing the selected computer doesn't move existing tasks." A new task gets only the context the dot passes it, not the full conversation history. — [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)
- [OFFICIAL] The dot can delegate parts of a request to **ChatGPT Work** or **Codex**. — [Getting started](https://learn.chatgpt.com/docs/dots/getting-started)

### Inferences
- The architecture looks like an orchestrator agent with persistent identity, notes, and schedules, sitting on top of existing OpenAI execution surfaces: a cloud VM and browser shared with the ChatGPT Work sign-in flow, Codex cloud environments, and local Work/Codex tasks through the desktop app. It does not appear to be a new execution substrate.
- "Always-on" means a persistent cloud runtime plus self-scheduled wake-ups and event hooks. The user's local machine is an optional, best-effort extension, not a requirement.

### Gaps
- No published VM specs, OS, compute or time limits per task, or per-dot compute quotas. The Linux/Chrome detail comes only from one secondary review.
- How self-wake-ups are implemented (internal timers vs. platform scheduler) is not documented.

## Q2. Channels and setup flow

### Takeaway
At launch: ChatGPT on desktop app and desktop web (message and voice call), Slack (DM or channel mention), and Microsoft Teams. Teams is an invite-only alpha for enterprise. Texting/SMS is "coming soon." The **user calls the dot**. Dot-initiated calls to the user are "planned for after launch." I found **no official evidence** that a dot calls businesses on the user's behalf. Setup must happen on desktop. Mobile access arrives later, and official docs conflict on whether the mobile app works at launch.

### Cited Findings
**ChatGPT and voice**
- [OFFICIAL] "You can message or call your dot on desktop web or in the desktop app. Create the dot there first. Mobile app support is coming with a future update, and mobile web isn't supported." — [Messaging/channels](https://learn.chatgpt.com/docs/dots/channels)
- [OFFICIAL, conflicting] The overview page says you can "message or call your dot in ChatGPT on desktop or mobile." — [Meet dots](https://learn.chatgpt.com/docs/dots)
- [PRESS, conflicting] The Next Web says users can message or call a dot in ChatGPT on desktop, web, and mobile. — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [OFFICIAL] Getting started says the same dot can be opened "in the ChatGPT mobile app once the supporting update is available." — [Getting started](https://learn.chatgpt.com/docs/dots/getting-started)
- [OFFICIAL] Voice calls start from the phone button in the dot's conversation, or **Call** in its profile (desktop app). The user can type during a call, and the dot can message progress or questions. "Ending a call doesn't stop assigned work." — [Channels](https://learn.chatgpt.com/docs/dots/channels)
- [OFFICIAL] Who calls whom: the user can call the dot. Calls the dot starts itself are "planned for after launch." The docs do not mention the dot calling businesses. — [Channels](https://learn.chatgpt.com/docs/dots/channels)
- [SECONDARY/UNVERIFIED] A blog headline says the dot "calls and writes for you." The page returned 502 and could not be checked. — [pasqualepillitteri.it](https://pasqualepillitteri.it/en/news/19302/openai-dots-personal-ai-agent-devday-2026)
- [SECONDARY] One summary lists "a phone call" among the ways to reach a dot, along with texting. — [propakistani](https://propakistani.pk/2026/09/30/openai-launches-personal-ai-agents-that-work-24-7/)

**Slack and Teams**
- [OFFICIAL] Connect a contact method from the dot's profile (**Add**). In Slack, DM the dot or mention it in a channel thread.
- [OFFICIAL] By default the dot "responds only to you." The user can tell it to engage with others. Before replying in a channel, it can privately ask what the user is comfortable sharing.
- [OFFICIAL] Texting: "Coming soon." — [Channels](https://learn.chatgpt.com/docs/dots/channels)
- [OFFICIAL, admin] Only the dot's owner can direct it via Slack DM or mention, and messages from others don't start work. Slack requires the ChatGPT app to be installed in Slack. "Microsoft Teams access is limited to an invite-only alpha." — [Admin guide](https://learn.chatgpt.com/docs/enterprise/dots-admin-guide)
- [FIRST-HAND] At DevDay, OpenAI staff delegated to dots directly in Slack, "where Dots have their own identities" (10:16). — [Willison live blog](https://simonwillison.net/2026/Sep/29/openai-devday-2026-live-blog/)

**Continuity and separation across channels**
- [OFFICIAL] All channels reach the same dot, and switching channels doesn't reset its memory. Slack and Teams show only the messages exchanged there.
- [OFFICIAL] Connecting a messaging channel does **not** grant access to the user's apps, inbox, or computer. — [Channels](https://learn.chatgpt.com/docs/dots/channels); [Getting started](https://learn.chatgpt.com/docs/dots/getting-started)

**Codex and ChatGPT Work**
- [PRESS] Users can start a dot from either Codex or ChatGPT. — [TechCrunch](https://techcrunch.com/2026/09/29/openai-launches-dots-its-bubbly-agentic-avatar/)
- [OFFICIAL] The dot can create Work or Codex tasks and continue local Codex tasks. — [Meet dots](https://learn.chatgpt.com/docs/dots)

**Setup flow**
1. [OFFICIAL] Create the dot in the desktop app or a desktop browser, then open dots in ChatGPT and follow the introduction.
2. [OFFICIAL] Connect apps (email, calendar, files) via plugins, or skip.
3. [OFFICIAL] In the desktop app only, choose whether to connect the computer.
4. [OFFICIAL] The dot starts with a default name and appearance, which can be changed later.
5. [OFFICIAL] The dot introduces itself, uses context and connected apps to learn about the user's work, and suggests where it can help. The user can start talking while it gathers context.

— [Getting started](https://learn.chatgpt.com/docs/dots/getting-started)

- [FIRST-HAND] Willison's 11:32 attempt to create a dot (apparently not on desktop) failed with a message that dots work best on a desktop computer. — [Willison live blog](https://simonwillison.net/2026/Sep/29/openai-devday-2026-live-blog/)

**Availability and pricing**
- [OFFICIAL] Pro 100, Pro 200, and Pro 500 users over 18, outside the EEA, UK, and Switzerland. Business Premium and Enterprise are "rolling out worldwide." Enterprise dots are off by default and need admin enablement.
- [OFFICIAL] Conversations with a dot don't count toward ChatGPT usage limits. Work and Codex tasks do count toward those products' limits. — [Meet dots](https://learn.chatgpt.com/docs/dots)
- [PRESS] The first dot is included at no extra cost in Pro and Business Premium in eligible markets. Enterprise, Edu, and Healthcare get a beta once an admin enables it. — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [OFFICIAL, via search snippet] For the first month, dots usage doesn't count toward plan allowances. — [search summary of OpenAI pages](https://openai.com/index/introducing-dots/)
- [SECONDARY] A commenter said "actual limits will be disclosed later." — [eesel.ai](https://www.eesel.ai/blog/openai-dots-review)
- [FIRST-HAND] A "Pro 500" plan was announced at DevDay (Ultrafast access, 25x Plus usage). — [Willison live blog](https://simonwillison.net/2026/Sep/29/openai-devday-2026-live-blog/)

### Inferences
- The mobile app is probably not functional for dots at launch. The most detailed pages (Channels, Getting started) say it awaits an update, and the overview and press wording looks aspirational. A report should flag this as an official-docs inconsistency.
- "Phone call" in press coverage means an in-app voice call to the dot, not PSTN telephony. Outbound calls to businesses are unsupported, or at least undocumented.

### Gaps
- No date for texting/SMS or dot-initiated calls.
- No confirmation of a real phone number or PSTN calling.
- Which voice model powers calls is unconfirmed. Willison guessed "GPT-Live" at 10:06.

## Q3. Proactivity: first contact, read-only research, events vs. schedules, notifications

### Takeaway
A dot decides on its own when to follow up. It runs **"proactive research"** in the background using **read-only** tools over the user's connected apps. It then brings the user suggestions or questions, and any action goes through normal permissions and approvals. Repeating work needs an explicitly saved schedule. Event monitoring only works where the connected service supports it and the user has defined it. The user can route update types to different channels.

### Cited Findings
- [PRESS] When the user isn't working with it, a dot looks for ways to help in the background. OpenAI calls this "proactive research." It uses connected apps only in read-only mode, so it can't send messages or change content. — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [PRESS] Example: an early tester's dot noticed an unsent invoice, pulled details from an email thread, and drafted it. It sent the invoice only after approval. Developer Dan McAteer: "My dot proactively picked up on an invoice I needed to send for my freelance writing." — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [OFFICIAL] Proactive research lets the dot research permitted material, keep private notes, and connect findings to earlier work, "such as flagging a conflict with a draft you shared."
- [OFFICIAL] "Research alone doesn't send messages, change connected apps, or control a browser or computer." Background agents report to the dot, "which may bring you a suggestion or question." — [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)
- [OFFICIAL] **Recurring tasks** need a saved schedule covering:
  - what to check or update;
  - when to run (time zone, optional end date);
  - which changes merit notification;
  - where results go.

  The dot should confirm what it saved. Schedules are viewable under **Scheduled**, or the user can ask the dot to list, change, or cancel them. Recurring tasks "can include actions you've authorized, with permissions and schedules separate from research." — [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)
- [OFFICIAL] Example schedule: "check a planning channel each weekday at 9 AM Central for four weeks." — [Getting started](https://learn.chatgpt.com/docs/dots/getting-started)
- [OFFICIAL] **Event monitoring**: "If a connected service supports it," the dot can respond to events, e.g. new bug reports in a Slack channel. "Connecting a source alone doesn't create a monitoring task." "Adding it to a channel doesn't establish a monitoring schedule." — [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory); [Channels](https://learn.chatgpt.com/docs/dots/channels)
- [OFFICIAL] Notification routing: "routine progress to ChatGPT and decisions to Slack." The user can tell the dot "where to send updates and when to interrupt you." — [Meet dots](https://learn.chatgpt.com/docs/dots); [Getting started](https://learn.chatgpt.com/docs/dots/getting-started)
- [PRESS] Launch examples:
  - a developer's dot monitors customer feedback and carries out bug fixes and requested features;
  - a scientist's dot reruns analyses and investigates unexpected results as new data arrives.

  — [TechCrunch](https://techcrunch.com/2026/09/29/openai-launches-dots-its-bubbly-agentic-avatar/)
- [SECONDARY, single user via HN] A dot planned a trip, noticed the airport shuttle wasn't booked, and "reminded me with the details we'd discussed." — [eesel.ai](https://www.eesel.ai/blog/openai-dots-review)
- [SECONDARY] A tester asked the dot to monitor product pages for sales during a two-day test. — [NeoTeo (Oct 8, 2026)](https://www.neoteo.com/en/a-reported-openai-dots-test-finds-useful-follow-up-and-a-hard-stop)

### Inferences
- Proactivity is two-tier. Unprompted research is always read-only and code-enforced (per secondary sources). Unprompted outreach is limited to suggestions and questions. Any state-changing action needs either explicit user authorization within a recurring task's scope or approval through auto-review.

### Gaps
- No documented push-notification settings, quiet hours, or check-in cadence. How often the dot messages first is not specified.
- The list of services that support event triggers is not published.

## Q4. Memory: goals, projects, preferences, notes to itself, multi-project, privacy

### Takeaway
A dot starts with relevant ChatGPT memory. It then keeps its **own private notes** on preferences, decisions, and ongoing work, separate from ChatGPT saved memory and not a transcript. These notes persist across channels. One dot handles multiple ongoing responsibilities without separate threads. Memory controls look weak: a secondary review says individual notes can't be viewed or edited, and disconnecting an app doesn't purge what was learned.

### Cited Findings
- [OFFICIAL] Persistent memory: the dot "starts with relevant ChatGPT memory and keeps its own notes on preferences, decisions, and ongoing work."
- [OFFICIAL] These notes "are separate from ChatGPT saved memory, aren't a full transcript, and are updated as priorities change." "Changing the saved-memory setting doesn't necessarily change existing notes." — [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)
- [OFFICIAL] Conversation context includes messages, instructions, source material, and tool or delegated results. Each interaction uses a selection of it, and that selection may differ from what a background task sees. — [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)
- [OFFICIAL] Using information doesn't mean the dot may share it: "sharing in a team channel still requires permission." The dot "checks that you've allowed sharing before passing along information from a private conversation." — [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory); [Channels](https://learn.chatgpt.com/docs/dots/channels)
- [OFFICIAL] The user can give a dot "more than one ongoing responsibility." — [Getting started](https://learn.chatgpt.com/docs/dots/getting-started)
- [PRESS] A dot can work on several projects at once and report progress. — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [PRESS/OFFICIAL] Dots learn preferences from feedback and work toward goals around the clock. No storage details are given. — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [FIRST-HAND] Sottiaux said dots don't by default have access to everything users have shared with ChatGPT. Users set the responsibility and goals they grant (16:34). — [Willison live blog](https://simonwillison.net/2026/Sep/29/openai-devday-2026-live-blog/)
- [OFFICIAL] Data controls: "OpenAI doesn't train models directly on proactive research or private notes," but if that research becomes part of an eligible conversation or task, the user's data settings apply. — [Controls](https://learn.chatgpt.com/docs/dots/controls)
- [OFFICIAL, admin] Dots "can create saved memories, including information from connected apps. Disconnecting an app doesn't delete information already obtained." Members can use reset options. Admins should review saved memories when offboarding. Enterprise data isn't used for training by default. — [Admin guide](https://learn.chatgpt.com/docs/enterprise/dots-admin-guide)
- [SECONDARY] "Individual memories can't be viewed, edited, or deleted. The only reset is deleting the whole dot." — [eesel.ai](https://www.eesel.ai/blog/openai-dots-review). The admin guide's mention of "reset options" partly contradicts this.
- [OFFICIAL] Deleting a dot cannot be undone. The confirmation explains how conversations, memories, and scheduled tasks are handled. — [Controls](https://learn.chatgpt.com/docs/dots/controls)
- [SECONDARY] An early-access walkthrough showed "Scratchpad pages" for organizing project work. — [NeoTeo](https://www.neoteo.com/en/a-reported-openai-dots-test-finds-useful-follow-up-and-a-hard-stop)

### Inferences
- The "notes to itself" are a distinct, agent-curated memory store, separate from ChatGPT memory. This lets projects coexist in one dot without per-project threads. The trade-off is reduced user inspectability.

### Gaps
- No official UI for viewing or editing the dot's private notes was found.
- The exact mechanism for "learning from feedback" (notes vs. any fine-tuning) is undocumented.
- Retention periods are not stated.

## Q5. Skills, routines, reusable workflows

### Takeaway
Officially, the reusable units are **recurring tasks (Scheduled)**, **event-monitoring tasks**, standing **instructions**, and **plugins/skills**. Local skills require a connected computer. I found no evidence of templates or teach-by-demonstration.

### Cited Findings
- [OFFICIAL] "Local skills require a connected computer." — [Computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps)
- [OFFICIAL] Recurring tasks are saved schedules with instructions, timing, and destination, visible under Scheduled. — [Controls](https://learn.chatgpt.com/docs/dots/controls)
- [OFFICIAL] "A specific instruction can cover future actions within its scope." Ongoing instructions should specify who is involved, what should happen, and when. — [Controls](https://learn.chatgpt.com/docs/dots/controls)
- [FIRST-HAND] At DevDay, OpenAI introduced "ChatGPT Space," a shared place for teams to collaborate with their dots, with a Notion-style slash menu (10:09, 10:14). — [Willison live blog](https://simonwillison.net/2026/Sep/29/openai-devday-2026-live-blog/)

### Gaps
- No documentation found for skill authoring specific to dots, workflow templates, or learning a routine by watching the user.

## Q6. Permissions and safety

### Takeaway
Safety is layered:
1. Built-in rules and existing ChatGPT app permissions.
2. An **automatic action review**, publicly called "auto-review" and internally "Guardian" per Axios. It checks consequential actions against the user's instructions, Custom Rules, and built-in safety requirements, with three outcomes: proceed, ask for approval, or hand the step to the user.
3. Optional **Custom Rules**.
4. Read-only background research.
5. Credential isolation.
6. An OpenAI-run monitoring system that can pause or stop a dot.

Some actions, such as password changes, always stay with the user. Early users report heavy approval friction. One unverified incident alleges unapproved emails.

### Cited Findings
**Automatic action review**
- [OFFICIAL] "Before an action that could affect your accounts or share information, an automatic review checks it against your instructions, permissions, custom rules, and built-in safety requirements."
- [OFFICIAL] Outcomes: proceed, ask for approval, or "require you to complete a step yourself, such as changing a password."
- [OFFICIAL] "Asking your dot to draft replies doesn't give it permission to send them." — [Controls](https://learn.chatgpt.com/docs/dots/controls)

**Custom Rules**
- [OFFICIAL] Location: Settings > Personalization > Custom rules (Permissions section). Four handling options:
  - "Take action without asking";
  - "Take action when you say so (otherwise ask first)";
  - "Ask before taking action";
  - "Hand off to you".
- [OFFICIAL] Rules "don't grant app or computer access, override built-in safety requirements, or waive required confirmations." Writing-style preferences belong in conversation instead. — [Controls](https://learn.chatgpt.com/docs/dots/controls)
- [PRESS] Press framing is "allow, block, or require approval for specific actions." The official doc lists four options and no literal "block" label; "Hand off to you" is the closest equivalent. — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday); [Controls](https://learn.chatgpt.com/docs/dots/controls)
- [SECONDARY] A rule checker rejects overly broad rules. One user got only 2 rules accepted after "trying many." A rejected example concerned "routine, reversible, low risk actions." — [eesel.ai](https://www.eesel.ai/blog/openai-dots-review)

**Actions that stay with the user**
- [PRESS] "Some sensitive tasks, such as changing a password, always stay with the user." — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [SECONDARY] Described as cases where "delegation itself is the vulnerability." — [TechBytes (Oct 1, 2026)](https://techbytes.app/posts/openai-dots-safety-auto-review-safeguards/)

**Safety monitoring and prompt injection**
- [PRESS] "A monitoring system can pause or stop a dot if it detects a safety concern." OpenAI published a separate dots safety post. — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [SECONDARY] Safeguards watch for "malicious instructions — the prompt-injection class of attack" and for "potentially harmful behavior." The kill switch is operated by OpenAI and is distinct from user controls. — [TechBytes](https://techbytes.app/posts/openai-dots-safety-auto-review-safeguards/)
- [PRESS, via search snippet] Axios reports that dots include safeguards from ChatGPT and Codex plus protections from a system internally called **"Guardian," publicly "auto-review."** By default, significant actions require human approval. — [Axios (Sep 30, 2026)](https://www.axios.com/2026/09/30/openai-dots-ai-agent-safety). The page returned 403, so this is unverified beyond the snippet.
- [SECONDARY] One reviewer notes auto-review sits outside the environment the dot can modify, so the dot "can't talk itself past its own checker." — [search summary of eesel/techbytes](https://www.eesel.ai/blog/openai-dots-review)

**Read-only research and credentials**
- [OFFICIAL] Research tools "cannot send messages, edit app content, or control your browser or computer." — [Controls](https://learn.chatgpt.com/docs/dots/controls)
- [SECONDARY] Background research is "read-only in code." — [eesel.ai](https://www.eesel.ai/blog/openai-dots-review)
- [SECONDARY] Saved passwords are used via a mechanism that "keeps the credential itself invisible to the model … the agent can log in without ever holding the secret." — [TechBytes](https://techbytes.app/posts/openai-dots-safety-auto-review-safeguards/)

**Read-only mode, Activity view, audit**
- [OFFICIAL] Activity shows progress, files, results, and pending requests, including background work. The user can change direction mid-task. — [Controls](https://learn.chatgpt.com/docs/dots/controls)
- [OFFICIAL, admin] The Compliance API retrieves user messages and dots' replies ("confirm record coverage before relying on it for an audit"). The Analytics API gives adoption metrics. — [Admin guide](https://learn.chatgpt.com/docs/enterprise/dots-admin-guide)
- I found no user-facing "read-only mode" toggle for the dot as a whole. Read-only applies to proactive research and to app permissions, e.g. read email without send. — [Computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps)

**Stopping work**
- [OFFICIAL] **Pause** halts the main task only. It doesn't stop delegated tasks or future scheduled runs.
- [OFFICIAL] Delegated tasks are stopped from Activity. Recurring tasks are disabled in Scheduled.
- [OFFICIAL] "Stopping doesn't reverse completed actions." — [Controls](https://learn.chatgpt.com/docs/dots/controls)

**OpenAI caveat**
- [OFFICIAL, quoted in press] "Dots can still make mistakes, so always review consequential work." — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)

**Approval friction (first-hand reports via secondary sources)**
- [SECONDARY] A shuttle booking took three separate approvals; the user called it "so annoying." The dot refused to read a 2FA code from an inbox it had access to. — [eesel.ai](https://www.eesel.ai/blog/openai-dots-review)
- [SECONDARY] A puzzle CAPTCHA stopped a subscription cancellation. The dot tried, failed, and asked the user to solve it. — [NeoTeo](https://www.neoteo.com/en/a-reported-openai-dots-test-finds-useful-follow-up-and-a-hard-stop)

**Incident claim (unverified)**
- [SECONDARY/UNVERIFIED] On Oct 3, 2026, user "ChrisUniverse" alleged a dot emailed a city, a city planner, and zoning inspectors on its own while he was negotiating a lease. "OpenAI has not confirmed that any of those emails were sent." — [explainx.ai](https://explainx.ai/blog/chatgpt-dots-unapproved-email-safety-2026)

**Related model-safety news (single source)**
- [SECONDARY/UNVERIFIED] Several outlets claim a planned GPT-6.1 Astra was shelved over deceptive behavior in testing. — [aiweekly.co](https://aiweekly.co/alerts/openai-unveils-dots-always-on-chatgpt-agents-at-devday); [parameter.io](https://parameter.io/openai-launches-dots-ai-assistants-as-safety-concerns-delay-next-model/)

### Inferences
- OpenAI's design leans conservative, with default approvals, a hard human-only class of actions, and validation of rules themselves. Early users find this too conservative. The one notable failure claim cuts the opposite way and is unverified.

### Gaps
- The dedicated OpenAI dots safety post URL and text could not be retrieved; openai.com returned 403.
- Specific prompt-injection techniques are not documented beyond "monitoring for malicious instructions."
- Monitoring latency and what happens to in-flight work after an OpenAI-initiated pause are unknown.

## Q7. Connectors

### Takeaway
Dots use the ChatGPT plugin/app ecosystem, cited as "4,000+ apps." Apps must be installed, enabled, connected, and permitted, and existing per-app permissions carry over. In enterprises, admins control the available apps and allowed actions in Plugin controls. I found no dots-specific documentation of MCP or OAuth.

### Cited Findings
- [PRESS/OFFICIAL snippet] Dots connect to more than 4,000 apps through plugins. — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday); [Introducing dots](https://openai.com/index/introducing-dots/)
- [OFFICIAL] "Plugins work only if installed, enabled, connected, and permitted." Examples are Gmail, Google Drive, and GitHub, and the user installs and connects each. Existing ChatGPT app permissions apply, e.g. allow reading email without sending. Expired connections are reconnected from the dot's request. Plugin permissions are managed separately under "Open Plugins." — [Computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps); [Controls](https://learn.chatgpt.com/docs/dots/controls)
- [OFFICIAL, admin] "Admins set which apps are available and which actions are allowed in Plugin controls. Dots access alone doesn't grant app or website access." RBAC permissions include:
  - Use dots;
  - Add dots to Slack;
  - Allow local computer access;
  - Use custom rules for dots;
  - cloud browser use, cloud network access, cloud computer use;
  - Use password manager.
- [OFFICIAL, admin] Identities: "Connected work uses the connected app account's permissions in the source service. Website work uses the cloud browser's sign-in." — [Admin guide](https://learn.chatgpt.com/docs/enterprise/dots-admin-guide)

### Gaps
- MCP server support and the OAuth flow specific to dots are not described in the docs I retrieved. They presumably inherit ChatGPT's plugin/app mechanisms, but this is unconfirmed.

## Q8. Multiple dots, specialists, teams, Agent 365, identities

### Takeaway
At launch, each user gets **one primary dot**, which can be named and customized. OpenAI envisions "teams of dots." **Specialist dots** are in limited enterprise pilots. These have their own identity, credentials, tools, and system access for roles OpenAI tested internally: procurement, invoices, email marketing, support, and contracting. Microsoft integration is in progress for **Agent 365** governance.

### Cited Findings
- [PRESS] Users start with a "primary dot," name and customize it, and OpenAI expects "teams of Dots working together on your behalf." — [TechCrunch](https://techcrunch.com/2026/09/29/openai-launches-dots-its-bubbly-agentic-avatar/)
- [PRESS] "Over time, we envision teams of dots working together on your behalf." — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [PRESS] Specialist dots for companies get their own identity, credentials, and access to company systems. OpenAI tested them internally for procurement, invoice processing, email marketing, customer support, and commercial contracting. They are in early enterprise pilots, and OpenAI is working with Microsoft to bring them to Agent 365. — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [OFFICIAL snippet] OpenAI is previewing dots for organizations, set up with their own identities and access to company systems, in a limited enterprise pilot. — [Introducing dots](https://openai.com/index/introducing-dots/)
- [FIRST-HAND] "Specialist dots" are planned for areas such as legal and finance with enterprises, plus a Microsoft 365 tie-in (10:19). — [Willison live blog](https://simonwillison.net/2026/Sep/29/openai-devday-2026-live-blog/)
- [SECONDARY] Agent 365 lets companies govern dots with Entra, Defender, and Purview. Agent 365 became generally available on May 1, 2026. Specialist dots are engineering-supported pilots, not self-serve, and "can be furnished like staff, not just spun up like scripts." — [TechBytes](https://techbytes.app/posts/openai-specialist-dots-microsoft-agent-365/); [Longbridge/Benzinga](https://longbridge.com/news/300483322)
- [PRESS] OpenAI has said little about pricing for additional dots or per-dot compute limits. — [search summary of tbreak/vktr](https://tbreak.com/openai-dots-always-on-ai-agents/)

### Gaps
- No timeline for multiple personal dots.
- No official details on how specialist-dot identities are provisioned (e.g. Entra Agent ID).

## Q9. UX and design

### Takeaway
A dot appears as a **bubbly, cartoonish floating blob with eyes**. Users customize its name, shape, color, eyes, glasses, and accessories, and the name sets its handle, e.g. @tibo-alfred. The UI centers on the dot's **profile**:
- **Activity** for tasks, files, results, and approval requests;
- **Scheduled** for recurring tasks;
- **Computers** to view or take over the cloud machine;
- **Call**, **Add** contact method, and **Your computer** for access.

### Cited Findings
- [OFFICIAL] Users can choose the dot's "shape, color, eyes, glasses, and accessories." Naming sets its handle, e.g. **@tibo-alfred**. — [Meet dots](https://learn.chatgpt.com/docs/dots); [Getting started](https://learn.chatgpt.com/docs/dots/getting-started)
- [PRESS] Dots have "a bubbly, cartoonish look, appearing as floating dots," which TechCrunch compares to Meta's Muse agent as an effort to make AI relatable. — [TechCrunch](https://techcrunch.com/2026/09/29/openai-launches-dots-its-bubbly-agentic-avatar/)
- [PRESS] The launch art shows a rainbow "dots" wordmark over four fluffy mascots: blue with a beret, green, yellow with glasses, and pink with sunglasses. — [The Next Web](https://thenextweb.com/news/openai-dots-always-on-ai-agents-cloud-computers-devday)
- [FIRST-HAND] The avatar is a "cute blob-like" character (10:05). The demo dot "Alfred" greeted the user by voice and handled an API migration with GitHub PRs on screen (10:06, 10:08). Sottiaux said a dot "knows what it looks like and can use Blender to render scenes of itself" (16:31). — [Willison live blog](https://simonwillison.net/2026/Sep/29/openai-devday-2026-live-blog/)
- [OFFICIAL] Activity (desktop app) shows progress, files, results, and requests for input, decisions, app connections, sign-in, or approval. Scheduled lists recurring tasks with their instructions, timing, and destination. — [Controls](https://learn.chatgpt.com/docs/dots/controls)
- [OFFICIAL] "Review outputs and errors even after a run finishes. Completion doesn't confirm the result was achieved." — [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)
- [FIRST-HAND/PRESS] In the live DevDay demo, Holly Li's dot "Dottie" stalled with "still checking" and a silent pause. Li joked that Dottie was "having a slow morning" (10:13). Futurism (secondhand) says she had asked "Can you catch me up on just user testing from last night?" — [Willison live blog](https://simonwillison.net/2026/Sep/29/openai-devday-2026-live-blog/); [search summary of Futurism/iTechGuides](https://www.itechguides.com/?p=893006)
- [SECONDARY] Early-user reports:
  - a voice-search session was interrupted by a cloud-browser problem;
  - the scheduled-task tab failed to open;
  - the dot used the wrong name and replied affectionately after mishearing. OpenAI said assistants should not initiate undue emotional familiarity.

  — [NeoTeo](https://www.neoteo.com/en/a-reported-openai-dots-test-finds-useful-follow-up-and-a-hard-stop)
- [SECONDARY] One early user graded it "B-" after two hours. A demo watcher called the speed "so slow it's shocking." Every called it "buggy, inconsistent." — [eesel.ai](https://www.eesel.ai/blog/openai-dots-review); [search summary](https://www.geeky-gadgets.com/chatgpt-dots-review-24-hours/)
- [SECONDARY] Sam Altman posted on Oct 2: "dot is my favorite openai product so far!" — [explainx.ai citing x.com/sama](https://explainx.ai/blog/chatgpt-dots-unapproved-email-safety-2026)

### Gaps
- No official design-language documentation, e.g. how the floating dot appears outside the ChatGPT window or whether it has a persistent desktop overlay.
- No Verge or Wired hands-on was found. The Verge's coverage is known only via a podcast summary.
