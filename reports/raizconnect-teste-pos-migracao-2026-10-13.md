# Raiz Connect: test after the migration to AWS (13/10/2026)

**Bottom line:** the system works on AWS. No bug caused by the migration showed up. One finding from the migration session needs action: Cloudflare blocks traffic coming from AWS IPs, webhooks included (pending item 10).

> **Updated on 13/10, evening**, with the migration session's check: production version, pipeline, test data and the Cloudflare finding. The tests in section 2 ran on `e5a2db2`.
>
> **Second update (13/10, 22:00 UTC)**: items 3, 9, 11 and 12 resolved; status of each one in section 3.
>
> **Third update (14/10, 00:30 UTC)**: items 1 and 10 resolved. Still open: 2 (delete the old branch), 5 (test cash register, optional), 6 (A1 certificate) and 7 (Hetzner, check-in on 24/10).

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
| 1 | ~~"Entrar com Google" didn't work ("origin is not allowed")~~ | done (14/10) | both origins (`https://raizconnect.com.br`, `https://app.raizconnect.com.br`) are on the OAuth client in project `raiz-connect` (account sejaorbyte); the button on the login page loads without the error |
| 2 | Obsolete branch `fix/pipeline-pasta-dos-artefatos` | Matheus | delete it on GitHub (erp-saas → Branches). PR #57 already made the same fix. This session cannot delete branches |
| 3 | ~~Alerts and approval emails don't arrive~~ | done | `falhanosistema1111@gmail.com` and `sejaorbyte@gmail.com` both confirmed |
| 4 | ~~Pipeline waiting for approval (`bb8a36f`, PR #55)~~ | done | rejected on 13/10 at 21:10 UTC: approving it would have taken production back to before PR #56 |
| 5 | Test company: the cash register opened at 01:10 UTC (R$ 200.00, user Caio Mendonça) is still open. Its two sales are from the migration session's customer-journey test (R$ 16.00 at 19:51 UTC and R$ 87.35 at 19:59 UTC, both cash) | Matheus | leave it or close it (no impact: test company) |
| 6 | Final NF-e test | Matheus | the test company has no certificate ("Certificado digital não configurado"). Upload the A1 (.pfx + password) under Fiscal → Configurações; then the NF-e in homologation can be issued |
| 7 | ~~Hetzner~~ | done (14/10) | at Matheus's request ("quero parar o gasto"): final snapshot `443402040` taken (6.4 GB, about €0.10/month), then server `raiz-connect` deleted (€41.99/month); its IPs and automatic backups went with it, and the Coolify push-to-deploy path is gone too. The site, app and `/health` on AWS answered 200 afterwards. Check-in on 24/10 asks whether to delete the snapshot |
| 8 | ~~Image for the next Terraform apply~~ | done | the next apply uses `b6cfd32`, the version SSM points to. The be17cc9 swap made straight in ECS has already been overwritten |
| 9 | ~~Agent password for automation~~ | done | the `matheus` login now also accepts a separate automation password, kept only in SSM (`/agentepessoal/operador-senha`). Matheus's own password did not change. To revoke it: `usuarios.py --sem-operador matheus` |
| 10 | ~~Cloudflare blocked traffic from AWS IPs~~ | done (14/10) | bot protection adjusted in Cloudflare (account sejaorbyte). From an EC2: `/health` 200, and the webhook routes now reach the API (401/400 without a valid signature, as expected) |
| 11 | ~~Pipeline fails when the image is already in ECR~~ | not a defect | the build in production already skips an image that exists. The `b6cfd32` run failed because the image was pushed by hand during that same build |
| 12 | ~~E2E tests out of date (`07-caixa-flow`, `44-abc-custos`)~~ | PR #58 | fixed and run against production: 6/6. In 44 there was a second cause: the test company had no expense without a category, so the test now seeds that one line when it is missing (R$ 500, "Despesa sem categoria (E2E)") |
