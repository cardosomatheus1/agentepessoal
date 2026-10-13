# Raiz Connect: test after the migration to AWS (13/10/2026)

**Bottom line:** the system works on AWS. No bug caused by the migration showed up. One finding from the migration session needs action: Cloudflare blocks traffic coming from AWS IPs, webhooks included (pending item 10).

> **Updated on 13/10, evening**, with the migration session's check: production version, pipeline, test data and the Cloudflare finding. The tests in section 2 ran on `e5a2db2`.

- **Site:** https://raizconnect.com.br, https://app.raizconnect.com.br, https://api.raizconnect.com.br
- **Version in production:** `b6cfd32` (PR #56), API and site, applied by Terraform; the SSM parameters point to it. The tests below ran on `e5a2db2` (PR #54).
- **Account used:** the test company's level 1 test account ("Raiz Connect Ltda"). Credentials stay in the agent's vault, not in this document.
- **Data created:** only what the tests create, marked "TESTE", plus my records marked "TESTE AGENTE"
- **Hard limits:** no invoice issued (NF-e/NFC-e), no payment, no email or WhatsApp to anyone

---

## 1. Migration status

| Item | Status | How I checked |
|---|---|---|
| DNS points to AWS (site, app, api, www) | ok since 14:24 UTC | tagged requests showed up in the API and web logs on AWS |
| Environment variables | all of them came over | name and hash of each value compared with the Hetzner container: 32 identical; the 4 that differ are on purpose; the ones left over were unused |
| Database | ok | boot log: "12 ok, 0 apply-fail" |
| WhatsApp (Baileys) | reconnected on its own | reopened with the session saved in the database, no QR code |
| SEFAZ (TLS with ICP-Brasil) | ok | test from inside AWS: BA (homologation and production), SP and SVRS validate; without the fix, all of them refused |
| Real time (WebSocket) | ok for users | connects straight on AWS and through Cloudflare (code 101). **Correction:** what decides it is the network the request comes from, not the type of client. Anything leaving an AWS IP gets a 403 bot challenge from Cloudflare, webhooks included (pending item 10) |
| Automatic deploy (pipeline) | working, with one gap | GitHub connection authorized; reads the code, builds the images, stops at approval. The `b6cfd32` run failed when pushing the images: they were already in ECR (pushed for the Terraform apply), and ECR does not overwrite a tag (pending item 11) |

### Fixes made along the way

| What | Where | Status |
|---|---|---|
| Pipeline couldn't write to the build bucket (wrong folder in the permission) | AWS (applied) + PR #57 in `erp-saas` `master` (with a test; also handles the name cut at 20 characters) | done. My branch `fix/pipeline-pasta-dos-artefatos` is obsolete: **do not merge it** |
| Agent panel: wrong password gave error 500 | `agentepessoal` (commits `5ca865c`, `00310a8`) | fixed and deployed |

---

## 2. Test by module

### 2.1 Every screen in the menu (~90 pages)

I opened each page with the test account. **None** had a server error (5xx) or a broken screen.

### 2.2 Business flows (automated tests from the project itself, against production)

**Result: 65 passed, 21 failed, 7 skipped.** I analyzed each failure in section 2.4.

| Area | Tests run | Result |
|---|---|---|
| Registration (products, customers, suppliers, supplies) | `02-cadastro` | passed |
| Sales and orders | `03-vendas` | passed |
| Dashboard, CMV and logout | `04-dashboard-cmv` | passed |
| Navigation and menus | `05-homepage-nav` | passed |
| Quick purchase (supplies) | `09-compra-rapida` | passed |
| Batches, expiry and FEFO | `10-lote-validade`, `11-lote-vencimento` | passed |
| Delivery schedule | `12-agenda-entrega` | passed |
| Break-even point | `14-ponto-equilibrio` | passed |
| POS without choosing | `101-pdv-sem-escolha` | passed |
| Production and full recipe | `104-producao-conta-e-receita-completa` | passed |

### 2.3 Flows I ran by hand through the API (create, check, undo)

| Module | What I did | Result |
|---|---|---|
| Restaurant | opened a tab on a free table, added a menu item (Talharim, R$ 27.39), cancelled the tab | ok; table back to "free" |
| Kitchen (KDS) | checked the kitchen queue after the order | the tab's order showed up |
| Financial | created a receivable and a payable (R$ 12.34), checked the list, cancelled both | ok |
| Dashboards | financial, stock and supplies | ok |
| ABC cost curve | opened the screen and the API | loads the data (API in 1.5 s) |

### 2.4 Failures explained

| Test | Cause | Bug in the system? |
|---|---|---|
| `08-venda-rapida` (7), `100`, `103`, `13` (3), `15` (4), `43` | the test prepares data straight in the database (`DATABASE_URL`), which only exists on the local machine | **no** |
| `07-caixa-flow` | the test looks for "Caixa Aberto"; the screen now shows "Aberto desde…". The cash register works (opening, sales, cash withdrawal and top-up) | **no** (test is out of date) |
| `44-abc-custos` | the test waited for the data after it had already arrived; the screen shows the curve normally | **no** (test timing) |

Not run on purpose:
- `105`: writes straight to the database through SQL.
- Restaurant suite: it uses a simulated API. I replaced it with the real flow from section 2.3.
- Operations, admin and WhatsApp suites: they touch production configuration or send messages.

---

## 3. Pending items

| # | What | Who | How |
|---|---|---|---|
| 1 | **"Entrar com Google" doesn't work** ("origin is not allowed"). This isn't from the migration; the domain is the same. | Matheus | Google Cloud Console → Credentials → login client ID → *Authorized JavaScript origins*: add `https://raizconnect.com.br` and `https://app.raizconnect.com.br` |
| 2 | Obsolete branch `fix/pipeline-pasta-dos-artefatos` | Matheus | delete it on GitHub (erp-saas → Branches). PR #57 already made the same fix. This session cannot delete branches |
| 3 | Approval email doesn't arrive | Matheus | confirm the subscription in the "AWS Notifications" email at sejaorbyte@gmail.com |
| 4 | ~~Pipeline waiting for approval (`bb8a36f`, PR #55)~~ | done | rejected on 13/10 at 21:10 UTC: approving it would have taken production back to before PR #56 |
| 5 | Test company: the cash register opened at 01:10 UTC (R$ 200.00, user Caio Mendonça) is still open. Its two sales are from the migration session's customer-journey test (R$ 16.00 at 19:51 UTC and R$ 87.35 at 19:59 UTC, both cash) | Matheus | leave it or close it (no impact: test company) |
| 6 | Final NF-e test | Matheus | issue an NF-e in homologation with the real A1 certificate |
| 7 | Hetzner | later | keep it stopped for 1 to 2 weeks, take a last backup and shut it down |
| 8 | ~~Image for the next Terraform apply~~ | done | the next apply uses `b6cfd32`, the version SSM points to. The be17cc9 swap made straight in ECS has already been overwritten |
| 9 | Agent password in SSM (`/agentepessoal/password`) | Matheus | it doesn't match the `matheus` login on the panel; update it if automation should be able to send messages to the agent |
| 10 | **Cloudflare blocks traffic from AWS IPs** with a 403 bot challenge. Users are fine; webhooks sent from AWS (Stripe, fiscal) and any call leaving AWS are not | Matheus / migration session | Cloudflare: an exception rule that skips the bot challenge for the webhook routes (or turn off Bot Fight Mode); then resend a test Stripe webhook and check for a 2xx |
| 11 | Pipeline fails when the commit's image is already in ECR (tags cannot be overwritten) | migration session | in the build, skip the push when the tag already exists |
| 12 | E2E tests that are out of date: `07-caixa-flow` (looks for "Caixa Aberto"; the screen shows "Aberto desde…") and `44-abc-custos` (waits for the data after it has arrived) | migration session | fix them on its branch, without touching production (it offered; recommended) |
