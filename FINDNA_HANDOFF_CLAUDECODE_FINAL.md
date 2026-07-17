# FinDNA — Final Ground-Level Handoff (Claude Code)

Supersedes `FINDNA_HANDOFF_CLAUDECODE.md` (session 1 only) and `FINDNA_HANDOFF_CLAUDECODE_FULL.md`
(sessions 1–3). This document adds **session 4** (UC5 / Twilio SMS, the Employee-Dashboard
split into per-customer pages, the new Customer Search page) and **session 5** (switching UC5's
delivery channel from SMS to Twilio WhatsApp, plus a network-outage diagnosis — see §3a), and
re-verifies everything still on disk as of **2026-07-16**. Read this one; the other two are kept
only as historical record of bugs already fixed.

Written by reading `agent.py`, `prompt.py`, `.env` (structure only), the four frontend `.dc.html`
files, `git log`, and the prior Claude Code session transcripts — not by re-deriving from memory.
Every line number below was re-checked against the files on disk at write time.

---

## 0. Repo / file map

| Path | Repo | Tracked? |
|---|---|---|
| `/Users/mhsn/VsCode/hackthon/agent.py` | `/Users/mhsn/VsCode` (parent repo) | **No** — `git status` shows `?? hackthon/`, still fully untracked |
| `/Users/mhsn/VsCode/hackthon/prompt.py` | same | **No**, same reason |
| `/Users/mhsn/VsCode/hackthon/.env` | same | No — untracked, and also listed in `hackthon/.gitignore` (`.env`, `__pycache__/`) so `git add -A` at the parent level would still skip it if the folder were ever added |
| `FinDNA-Banking-Application/FinDNA App.dc.html` | `FinDNA-Banking-Application` (own repo, origin `github.com/Afnan-Jadidi/FinDNA-Banking-Application`) | Yes, branch `agent-integration` — **but currently has uncommitted changes** (`M "FinDNA App.dc.html"`, the session-4 UC5 work, never committed) |
| `FinDNA-Banking-Application/FinDNA Dashboard - Ahmed.dc.html` | same | Yes, committed (`72ff778`) |
| `FinDNA-Banking-Application/FinDNA Dashboard - Sara.dc.html` | same | Yes, committed (`72ff778`) |
| `FinDNA-Banking-Application/FinDNA Customer Search.dc.html` | same | Yes, committed (`72ff778`) |
| `FinDNA-Banking-Application/FinDNA Employee Dashboard.dc.html` | same | **Deleted** — replaced by the Ahmed/Sara split, see §5 |

Deployed agent: **`https://findna-agent.cycls.ai`**, `POST /chat/completions` (aliased at `/` and
`/chat`). Currently live with UC5 included, **redeployed in session 5** after switching UC5's
send channel from SMS to WhatsApp (see §3a) — this is the most current deploy as of this writing.

### Branch/commit history, `FinDNA-Banking-Application`, branch `agent-integration`
```
509bb04  Initial commit                                                        (pre-existing, Afnan)
0ff649e  feat: integrate FinDNA live AI agent — UC2/UC4, SSE parsing, CORS fix  (session 1+2, m7snAl)
8a81253  feat: timeout, UC3 wiring, UC1 real call, DNA personality label       (session 3, m7snAl)
886c26f  Merge pull request #1 from Afnan-Jadidi/agent-integration              (merge, Afnan — #1 merged into #1?? see note below)
72ff778  Add new page (Customer Search)                                        (session "Afnan", Jul 15 16:50)
05749b3  Merge branch 'agent-integration' ... into agent-integration           (merge, current HEAD)
```
**Note on `886c26f`:** it's a "Merge pull request #1 from Afnan-Jadidi/agent-integration" landing
*on* `agent-integration` itself — i.e. Afnan opened a PR from `agent-integration` back into
`agent-integration` (or the branch was merged into a copy of itself on GitHub's side) rather than
this branch ever having been merged into `main`. **`main` still has none of this work.** No PR
into `main` exists yet.

**Uncommitted right now:** `FinDNA App.dc.html` (session-4 UC5 additions). Nothing else is dirty.
`hackthon/agent.py` / `hackthon/prompt.py` have no git history at all (not in any repo), so their
session-4 changes (UC5 prompt section, `_send_sms`, etc.) exist only on disk + in the deployed
container, same caveat as sessions 1–3.

---

## 1. Architecture per file

| File | Architecture | Evidence |
|---|---|---|
| `FinDNA App.dc.html` | **Component class** — `class Component extends DCLogic` (`:949`), `state = {...}` (`:950`), `renderVals()` (`:1209`), `componentDidMount()`/`componentWillUnmount()` (`:1006`, `:1008`), template bindings via `{{ key }}` | Confirmed by direct grep of `class .*extends`, `state = {`, `renderVals()` |
| `FinDNA Dashboard - Ahmed.dc.html` | **Vanilla-JS IIFE**, no Component/state/renderVals — plain `<script type="text/x-dc" data-dc-script">` with top-level `async function callAgent(...)`, `async function loadDashboard()`, `async function loadUC3()`, driven entirely by `data-*` attributes + `document.querySelector` | No `class`/`state =`/`renderVals` hits anywhere in the file |
| `FinDNA Dashboard - Sara.dc.html` | **Identical architecture to Ahmed** — same script verbatim, only the hardcoded `CUSTOMER_DATA`/`CUSTOMER_DATA_UC3` payloads and display text differ (see §5) | `diff` of the two files shows zero script-logic differences, only data/text |
| `FinDNA Customer Search.dc.html` | **Component class**, but trivial — `class Component extends DCLogic` (`:85`), `state = { query: '' }` (`:86`), a hardcoded `customers` array (`:87–93`), `renderVals()` does client-side `.filter()` (`:94–105`). **No fetch, no agent call, no `data-*` attributes.** | Full file read (109 lines, small enough) |

`FinDNA Employee Dashboard.dc.html` (the pre-split file sessions 1 and 3 worked on) **no longer
exists** on disk — Afnan's commit `72ff778` renamed/duplicated it into Ahmed + Sara. Session 3's
line-number references to that filename (in `FINDNA_HANDOFF_CLAUDECODE_FULL.md`) are now stale;
use the tables in this document instead.

---

## 2. Every UC, wired where, exact line numbers

### UC1 — Financial DNA Profile Builder
- **Prompt:** `prompt.py:133–191` (section header `:135`), triggered by `[UC1]` prefix or `mode: uc1` in memory.
- **Schema:** `personality.label`, `strengths[]`, `weaknesses[]`, `recommendations[].action`, DNA score fields (built via `calculate_dna_score` tool).
- **Frontend:** `FinDNA App.dc.html` only.
  - Method `_runUC1()`, `:1088–1157` (based on the same fetch/SSE-parse pattern as `_loadAIContent`).
  - Triggered from the onboarding "Continue" handler `obNext`, `:1274–1278` — real agent call replaces what was originally a fake 2s `setTimeout`.
  - On success, sets `dnaPersonality`, `dnaStrengths`, `dnaWeaknesses`, `dnaRecommendations` state (initial placeholders at `:987–990`).
  - Rendered at `{{ dnaPersonality }}` (`:405`); strengths/weaknesses/recommendations are joined into single strings (`' • '.join(...)`), not separately templated.

### UC2 — Daily AI Assistant
- **Prompt:** `prompt.py:192–232` (header `:194`), triggered by `[UC2]` or `mode: uc2`.
- **Schema:** `morning_briefing`, `daily_insight`, `recommendations[].title/subtitle`.
- **Frontend:** `FinDNA App.dc.html` only.
  - Method `_loadAIContent()`, `:1010–1086`, called from `componentDidMount()` (`:1006`) — fires on every page load.
  - Sets `aiMorningBriefing`, `aiDailyInsight`, `aiRec1..3Title/Subtitle`, `aiLoaded` (`:1065–1075`).
  - Rendered at `{{ aiDailyInsight }}` (`:223`), `{{ aiMorningBriefing }}` (`:492`), `{{ aiRec1Title }}`/`{{ aiRec1Subtitle }}` etc. (`:500–527`).

### UC3 — Loan Eligibility & Improvement Plan
- **Prompt:** `prompt.py:89–132` (header `:91`), triggered by `[UC3]` or `mode: uc3`.
- **Schema:** `approval_status`, `current_approval_probability`, `blocking_factors[]`, `improvement_plan[]`, `best_product.{name,max_amount,estimated_monthly,reason}`, `dti_analysis.{current_dti,dti_after_loan,bank_limit,headroom}`.
- **Frontend:** `Dashboard - Ahmed.dc.html` **and** `Dashboard - Sara.dc.html`, identical wiring at identical line numbers in both files:
  - `loadUC3()`, `:497–626` — builds `CUSTOMER_DATA_UC3` per-customer payload (`:499–510`), calls `callAgent('UC3', ...)` (`:512`).
  - Fills `[data-uc3-figures]` (max/monthly/probability/DTI, `:547–579`), `[data-uc3-reason-wrap]`/`[data-uc3-reason]` (`:582–585`), `[data-uc3-conditions-wrap]`/`[data-uc3-improve-wrap]` via a shared `fillList()` helper (`:586–610`).
  - Uses a bidi-safe `setMixed()` helper (defined inline) so Arabic text with embedded numbers renders LTR numerals correctly inside RTL text.
  - Fired in parallel with `loadDashboard()` at bootstrap: `:631–633`.
  - **This is more elaborate than what session 3's handoff documented** — session 3's UC3 card was a single-line decision + amount + reason + risk text. The current version (post-Afnan-split) has a 4-figure grid (max amount, monthly payment, approval probability bar, DTI bar with a bank-limit marker), a collapsible reason box, and two side-by-side "blocking factors" / "improvement suggestions" columns. This was reworked at some point between session 3 and now — not documented anywhere, reconstructed here from the current file.

### UC4 — Employee Dashboard (summary/badges/eligibility/recommendations)
- **Prompt:** `prompt.py:37–88` (header `:39`), triggered by `[UC4]` or `mode: uc4`.
- **Schema:** `summary`, `badges[]`, `eligibility.{car_loan,personal_loan,mortgage}`, `recommendations[]`, `investment_potential`, `risk_flags[]`.
- **Frontend:** `Dashboard - Ahmed.dc.html` and `Dashboard - Sara.dc.html`, identical wiring:
  - `callAgent(mode, data)` helper, `:386–421` (POST + 180s `AbortController` timeout + SSE-parse).
  - `loadDashboard()`, `:422–496` — builds `CUSTOMER_DATA` (`:351–384`, per-customer), calls `callAgent('UC4', ...)` (`:432`), fills `[data-ai-summary]` (`:425`), 3× `[data-badge]` (`:442–452`), 3× `[data-eligibility="car_loan"/"personal_loan"/"mortgage"]` → `[data-status]`/`[data-note]` children (`:453–466`), and 4× `[data-rec-card]` → `[data-rec-title]`/`[data-rec-reason]` (`:468–486`).
  - Bootstrap: `:631–633` (same block as UC3, both fire together after a 500ms delay).

### UC5 — Daily Spending Alert (SMS)
- **Prompt:** `prompt.py:233–251` (header `:233`), triggered **only** by `[UC5]` prefix (no memory-mode route — one-shot action, not a conversational mode).
- **Schema:** `sms_message` (Arabic, <160 chars), `category`, `amount_exceeded`, `remaining_budget`.
- **Backend (`agent.py`) — the actual SMS send happens server-side, not in the browser:**
  - `_last_user_text(context)`, `:448–466` — pulls the last user message's text regardless of whether `content` is a bare string or an Anthropic-style content-block list.
  - `is_uc5` check, `:503` — `last_user_text.strip().startswith("[UC5]")`.
  - Non-UC5 path (`:505–508`): normal streaming passthrough, unchanged from sessions 1–3.
  - UC5 path (`:510–532`): buffers the full model output instead of streaming deltas (`:514–519`), `json.loads`s it (`:521–524`, with a fallback that truncates to 160 chars if the model didn't return clean JSON), calls `_send_sms(sms_text)` (`:527`), appends `sms_sent`/`sms_error` to the JSON (`:528–530`), and yields **one** augmented JSON chunk through the same delta channel (`:532`) — chosen specifically so the frontend's existing SSE-parsing loop needs zero changes to consume it.
  - `_send_sms(body)`, `:469–490` — reads `TWILIO_SID`/`TWILIO_TOKEN`/`TWILIO_FROM`/`TWILIO_TO` from `os.environ` (populated via `load_dotenv()` at `:20`), POSTs to `https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json`, returns `(sent: bool, error: str|None)`.
- **Frontend (`FinDNA App.dc.html`) — only file with UC5 wiring:**
  - `sendingAlert` state (`:991`, init `false`).
  - `_sendSpendingAlert()`, `:1157–1207` — same fetch/AbortController/SSE-parse pattern as UC1/UC2, hardcoded `SPENDING_DATA_UC5` payload (`:1160–1163`: customer name + one category with `daily_limit`/`exceeded_by`/`remaining_budget`), calls `[UC5]`, shows a toast via `showToast()` (`:1195`) reporting `r.sms_sent` / `r.sms_error`.
  - Button: `:278`, "تنبيه الإنفاق 🔔" under the "ميزانية اليوم" (today's budget) card, `onClick="{{ sendSpendingAlert }}"` bound at `:1426` (`sendSpendingAlert: () => this._sendSpendingAlert()`), `disabled="{{ alertSending }}"` bound to `s.sendingAlert` at `:1427`.
  - **Not wired into either Dashboard file** — UC5 is customer-app-only (makes sense: the SMS goes to the *customer's* phone, triggered from the customer-facing app, not the employee dashboard).

---

## 3. UC5 status — what works, what doesn't, why

**Full pipeline confirmed working end-to-end except the actual SMS delivery, as of session 4:**
1. Frontend button → agent endpoint: **works.**
2. Agent detects `[UC5]` prefix, routes correctly, does not stream raw deltas: **works** (buffering logic at `agent.py:510–519` confirmed via a live test call).
3. Model generates a valid Arabic SMS message matching the schema (category, amounts, message text): **works** — a live test produced a correct, well-formed message ("تجاوزت ميزانية اليوم... المطاعم... 260 ريال...").
4. Agent calls Twilio's REST API server-side: **works** (request is sent, response is received and parsed).
5. **Twilio itself rejected the send — HTTP 400, error code 21660:**
   ```
   Twilio 400: {"code":21660,"message":"Mismatch between the 'From' number +18777804236
   and the account [REDACTED_TWILIO_ACCOUNT_SID]","more_info":"https://www.twilio.com/docs/errors/21660","status":400}
   ```
6. Agent correctly surfaced the failure — `sms_sent: false`, `sms_error: "Twilio 400: ..."` — rather than silently swallowing it or claiming success. **No SMS was sent, no charge occurred.**

Root cause at the time: `TWILIO_FROM` (`+18777804236`) was not a number actually provisioned
under that Twilio Account SID (or was an unverified toll-free number) — an account-config issue,
not a code bug.

### 3a. Session 5 — switched from SMS to Twilio WhatsApp, plus a network detour

**Change made this session, `agent.py:483`:**
```python
data={"To": f"whatsapp:{to_number}", "From": "whatsapp:+14155238886", "Body": body[:1600]},
```
(previously `{"To": to_number, "From": from_number, "Body": body[:1600]}`). `+14155238886` is
Twilio's public WhatsApp **sandbox** number — this sidesteps the SMS toll-free-verification/
number-provisioning problem from §3 entirely, since sandbox WhatsApp doesn't require a purchased,
verified sending number. `TWILIO_FROM` in `hackthon/.env` was also updated to `+14155238886` to
match (the `from_number` env var is still read and still gates the "not configured" check at
`agent.py:475`, but the actual `From` value sent to Twilio is now the hardcoded sandbox constant,
not `from_number` — so editing `TWILIO_FROM` again won't change what's actually sent unless
`agent.py:483` is also updated).

**Redeployed successfully** (`uv run cycls deploy agent.py` → `[DONE] Deployment complete!`,
`https://findna-agent.cycls.ai`). Not yet re-tested live against a real `[UC5]` call after this
switch — do that next (same `curl` shape as before, see below).

**New caveat this introduces, not present with plain SMS:** Twilio's WhatsApp **sandbox**
requires the recipient number to have opted in first, by sending the sandbox's join code (e.g.
"join <two-words>") as a WhatsApp message to `+14155238886` from `TWILIO_TO`'s phone
(`+966593038274`). Until that opt-in happens, expect Twilio to reject the send with a *different*
error than 21660 — most likely **63007** (channel/number not found or not a valid WhatsApp
sender) or **63016** (message sent outside the allowed 24h session window / sender not a
verified sandbox participant). If a test fails after this change, check the error code against
Twilio's docs before assuming the code is wrong — it likely just means the opt-in step hasn't
happened yet.

**Known-safe test call** (real send, real cost — recipient must have joined the sandbox first):
```bash
curl -sS -X POST https://findna-agent.cycls.ai/chat/completions \
  -H 'Content-Type: application/json' --max-time 180 \
  -d '{"model":"findna-agent","messages":[{"role":"user","content":"[UC5]\n{\"customer\":{\"name\":\"أحمد السالم\"},\"today_spending\":{\"مطاعم\":1860,\"daily_limit\":1600,\"exceeded_by\":260,\"remaining_budget\":-260}}"}],"stream":false}'
```

**`TWILIO_TO` is already a real number**, not a placeholder (`.env:4`, `+966593038274`). No edit
needed there.

### 3b. Network detour this session — api.cycls.ai looked "down," wasn't

Mid-session, both `api.cycls.ai` (the deploy API) and `findna-agent.cycls.ai` (the live agent)
became unreachable — `uv run cycls deploy agent.py` failed twice with a `Read timed out` on
`api.cycls.ai`, and direct `curl` calls hung on the TLS handshake after a successful TCP connect.
This looked like a Cycls-side outage at first (no public Cycls status page exists to check
against — searched, none found). ~20 minutes of polling (first ~5 min, then another ~15 min)
eventually returned one success, and diagnosis found the real cause:

- `curl -4` (forced IPv4) to `api.cycls.ai` → succeeds instantly (HTTP 200, ~2.4s).
- `curl -6` (forced IPv6) → hangs and times out every time.
- `dig AAAA api.cycls.ai` returns a `64:ff9b::/96`-prefixed address — the well-known **NAT64
  synthesized-address prefix**, not a real IPv6 address Cycls publishes (unlike `google.com`,
  which has a genuine native AAAA record).

**Conclusion: this sandbox environment's dual-stack DNS resolution intermittently prefers the
NAT64/IPv6 path to `*.cycls.ai`, and that translated path is unreliable** (hangs on TLS) for this
specific destination — it is **not** a Cycls outage; their server answers immediately once IPv4
is forced. This is worth knowing for next time: if `cycls deploy` or a direct curl to
`*.cycls.ai` hangs/times out again, try `curl -4` first to confirm before assuming Cycls itself is
down. A possible permanent fix (not applied, flagged as a choice for whoever hits this again) is
pinning `api.cycls.ai` / `findna-agent.cycls.ai` to their IPv4 addresses in `/etc/hosts` — not
done this session since it's a system-config change outside the repo and wasn't asked for once
the deploy started succeeding on its own again.

---

## 4. Deviation this session made from the literal task brief, and why

The pasted session-4 instructions asked to **hardcode the live Twilio Account SID + Auth Token
directly into `FinDNA App.dc.html`** (a static file shipped straight to the browser, already
tracked in a public-facing git repo). This was flagged and *not* done as written:

- View-source or a repo clone would hand anyone a fully live, functional Twilio credential pair —
  capable of sending SMS (cost to the account owner) or being harvested by the bots that scan
  public GitHub repos for exactly this credential pattern within minutes of a push.
- A prior session (session 1, see `FINDNA_HANDOFF_CLAUDECODE_FULL.md` open item #6) had already
  flagged the *existing* hardcoded `cycls.api_key` and OpenRouter key in `agent.py` as a
  pre-existing issue "to fix before this goes anywhere more public than a hackathon." Adding a
  second hardcoded secret pair to a browser-shipped file would compound a known issue rather than
  be a one-off shortcut.

**What was done instead, same feature, no exposed secrets:**
- `prompt.py`'s UC5 section was added exactly as specified (it only makes the model return JSON
  text — no secrets involved there).
- The actual Twilio call was moved **server-side**, into `agent.py`, reading credentials from a new
  `hackthon/.env` (gitignored via a new `hackthon/.gitignore`, `.copy(".env")`'d into the Cycls
  deploy image at build time, loaded via `python-dotenv`). The browser only ever talks to the
  FinDNA agent endpoint — exactly like the existing UC1–UC4 calls — and only ever sees
  `sms_sent`/`sms_error` in the response, never Twilio credentials.

This is a change in **where** the Twilio call happens, not in what the feature does or how it's
triggered from the UI.

**Deviations from sessions 1–3** (UC3 field-name mismatch fixed, wrong architecture assumed for
the dashboard, brace-escaping bug in `prompt.py`, wrong filename `main.py` vs actual `agent.py`,
CORS not in any brief, sequential-vs-parallel UC3/UC4 firing, AbortError handling kept
non-destructive instead of a bare `return`) are all still accurate as documented in
`FINDNA_HANDOFF_CLAUDECODE_FULL.md` §1–§3 and not repeated here — nothing in session 4 touched
those files' prior fixes.

**Session 5 had no deviations** — the SMS→WhatsApp channel switch (§3a) was implemented exactly
as instructed (literal `data={...}` replacement in `_send_sms`, literal `TWILIO_FROM` value
change), no architecture mismatch or ambiguity to resolve.

---

## 5. What Afnan changed in the Employee Dashboard → Ahmed/Sara split, and what's new in Sara

Commit `72ff778` ("Add new page (Customer Search)", Afnan-Jadidi, Jul 15 16:50 2026) did three things
at once: it deleted two unrelated stale export files (`FinDNA App v1 (before UX fixes).dc.html`,
`FinDNA App-print-16oz8ni.dc.html` — pre-existing cruft, not related to this project's active
work), added the new Customer Search page, and **split `FinDNA Employee Dashboard.dc.html` into
two files**: `FinDNA Dashboard - Ahmed.dc.html` and `FinDNA Dashboard - Sara.dc.html`.

Diffing the pre-split file (`git show 8a81253:"FinDNA Employee Dashboard.dc.html"`) against each
new file shows:

**Structural changes applied to *both* new files (i.e. these are Afnan's real content/behavior
changes, not per-customer data):**
- Added a "← العملاء" back-link to `FinDNA Customer Search.dc.html` in the top bar (new file
  `:33–35` in both) — the dashboards are no longer standalone, they're reached by picking a
  customer from the new search page.
- **Reworked the UC3 loan-eligibility card** from the session-3 version (single decision line +
  amount + reason + risk text, ~13 lines) into a much richer card: a 4-box figures grid (max
  amount / monthly payment / approval-probability bar / DTI bar with a bank-limit marker line), a
  collapsible reason box, and two side-by-side detail columns for blocking factors vs improvement
  suggestions (new file `:232–289` in both — see §2's UC3 section above for the exact wiring).
  This is a real UI/JS rework, not a rename — the `data-uc3-*` attribute set expanded from 5
  attributes to about 15, and `loadUC3()`'s body was substantially rewritten (bidi-safe text
  helper `setMixed()`, tone-based coloring of the decision badge, `fillList()` helper for the two
  detail columns).
- The eligibility card's decision-badge JS now computes a `tone` (`danger`/`warn`/`ok`) from the
  approval status/probability and applies an `fd-badge-*` CSS class instead of just setting plain
  text color.

**Per-customer changes (Sara is a duplicate of Ahmed with different hardcoded data, not new
logic):**
- `diff` between `Dashboard - Ahmed.dc.html` and `Dashboard - Sara.dc.html` shows **zero
  differences in script/JS logic** — every function, every line number, every `data-*` attribute
  is identical between the two files. The only differences are: customer name/ID/avatar initial,
  DNA score (82 vs 74), commitment score (96 vs 88), risk level (low vs medium), all the financial
  figures (income, obligations, DTI, savings rate), the 3 static badges (Ahmed: "qualified for
  auto loan / clean payment history / high restaurant spend"; Sara: "conditionally qualified /
  high obligations / refinancing opportunity"), the 3 eligibility-card notes/statuses (Sara is
  "not eligible" for mortgage, vs Ahmed's "conditional"), the 3 financial goals, and the
  `CUSTOMER_DATA`/`CUSTOMER_DATA_UC3` payload objects sent to the agent (`:351–384` and `:499–508`
  respectively) — Sara requests a personal-loan refinance instead of a mortgage.
- In short: **Sara is a persona clone of Ahmed for demo variety** (a lower-DNA-score, higher-risk
  customer to show the UC3/UC4 flows producing different real output), not a new feature.

**Does this affect the agent?** No — both files call the same `[UC3]`/`[UC4]` prompts with
different `customer` payloads; `prompt.py` needed zero changes to support two customers.

---

## 6. Customer Search — what it does, does it need agent work

`FinDNA Customer Search.dc.html` is a **pure client-side router/filter page**, not an agent
integration point:
- `Component` class, `state = { query: '' }` (`:85–86`).
- A hardcoded `customers` array of 5 entries (`:87–93`): only **2 have working links**
  (`href: 'FinDNA Dashboard - Ahmed.dc.html'` and `'...Sara.dc.html'`); the other 3 (خالد الدوسري,
  نوف الشمري, فهد العتيبي) have `href: ''` — **dead entries**, clicking them goes nowhere, because
  no dashboard page exists for them.
- `renderVals()` (`:94–105`) does an in-memory `.filter()` on `id`/`name` substring match against
  `this.state.query`, no debounce, no backend call of any kind.
- **Zero fetch calls, zero `data-*` agent-bound attributes, zero UC references anywhere in this
  file.**

**Does it need agent work?** Not for its current scope (it's a static directory/router). It would
only need agent involvement if either:
1. The 3 dead-link customers are meant to get real dashboards — that's more Ahmed/Sara-style
   dashboard cloning (§5), not new agent code; `prompt.py`/`agent.py` already handle arbitrary
   customer payloads.
2. Search itself is meant to become a real customer lookup against a bank record system instead
   of a hardcoded 5-row array — that would be a new, distinct backend endpoint, unrelated to the
   FinDNA `findna-agent` chat-completions interface entirely.

Neither is implied by anything in the current session-4 work; flagging only because the task
asked whether it needs agent work.

---

## 7. What was verified vs. not verified

| Item | Status | Evidence |
|---|---|---|
| CORS preflight/live requests | ✅ Verified (session 1) | `curl -X OPTIONS` → `access-control-allow-origin: *` |
| Employee Dashboard UC4 (pre-split) end-to-end | ✅ Verified (session 1) | Headless Playwright run, all fields changed from placeholders |
| Customer App UC2 content-change | ❌ **Never verified** | Network layer confirmed (200 OK, no errors), content-change not observed within test windows up to 200s (session 1); not re-checked since |
| UC3 wiring (session 3's simpler card) | ❌ **Never verified** | Playwright check was started, interrupted by the user, never completed (`FINDNA_HANDOFF_CLAUDECODE_FULL.md` §3.5) |
| UC1 real call replacing onboarding timer | ❌ **Never verified live** | Static syntax checks only (`node --check`, grep counts); user said "All tests passed" and pushed without independent Claude Code confirmation |
| UC3 card rework (current, richer version) + Ahmed/Sara split | ❓ **Unknown — no session documented verifying this at all.** This was done by Afnan (`72ff778`), not by Claude Code, and no Claude Code session has driven either dashboard in a browser since the split. |
| Customer Search page | ❓ **Unknown** — never opened in a browser by any Claude Code session; static-analysis only, in this session |
| UC5 pipeline through Twilio's REST call (SMS, session 4) | ✅ Verified **up to the Twilio rejection** — a real live test request was fired (`curl` against the deployed agent), confirmed the model output, the buffering logic, and the Twilio error surfacing all work correctly |
| UC5 actual SMS delivery (session 4) | ❌ **Not working** — blocked on Twilio account config, error 21660 (§3) |
| UC5 WhatsApp switch (session 5) | ❓ **Deployed, not yet live-tested** — redeploy succeeded (exit 0, "Deployment complete!"), but no `[UC5]` call has been fired against the new WhatsApp code path yet. Needs the sandbox opt-in step first (§3a) or it will fail with a different Twilio error (63007/63016). |
| Deploy pipeline (`uv run cycls deploy agent.py`) | ✅ Verified — used repeatedly across sessions 1, 3, 4, 5, always exits 0 once network path is healthy (see §3b for one session-5 network detour, unrelated to the tool itself) |

**Bottom line: nothing in the frontend has been visually/behaviorally re-verified since session
1.** Sessions 3, 4 and 5's changes (UC1 real call, UC3 rework via the Afnan split, UC5 button, UC5
WhatsApp switch) are unverified in a live browser / against a real recipient. This is the single
biggest risk item for whoever picks this up next.

---

## 8. Open items — exact files to edit

1. **Complete the Twilio WhatsApp sandbox opt-in, then live-test UC5** (§3a) — send the sandbox's
   join code from `+966593038274` (WhatsApp) to `+14155238886`, then re-run the `curl` test in §3a
   (or click "🔔 تنبيه الإنفاق" in `FinDNA App.dc.html` in a real browser) to confirm the message
   actually lands. No code change needed unless it fails with 63007/63016 (§3a).
2. **Live-verify the UC3 card on both dashboards** — open
   `FinDNA-Banking-Application/FinDNA Dashboard - Ahmed.dc.html` and `...Sara.dc.html` over
   `http://localhost:PORT` (not `file://` — the design-system runtime's bootstrap fetch fails
   under `file://`, a known false-negative trap from session 1), confirm the 4-figure grid,
   probability bar, DTI bar, and both detail columns fill with real (not placeholder) content for
   each customer.
3. **Live-verify UC1's onboarding flow** in `FinDNA App.dc.html` — click through the 5-step
   onboarding, confirm "Continue" waits for a real `_runUC1()` response (not a timer) before
   showing Home, and that the DNA screen's `{{ dnaPersonality }}` (`:405`) isn't stuck on "جارٍ
   التحليل...".
4. **Live-verify UC2** in `FinDNA App.dc.html` — confirm `{{ aiMorningBriefing }}` (`:492`) and
   `{{ aiDailyInsight }}` (`:223`) actually change from their loading placeholders after
   `componentDidMount()` fires `_loadAIContent()`.
5. **Commit the uncommitted UC5 work** — `FinDNA App.dc.html` currently shows `M` (modified,
   uncommitted) in `git status` inside `FinDNA-Banking-Application`. Session 4 never ran `git add`/
   `git commit` for it. Decide on a commit message and push, or it risks being lost/overwritten.
6. **Initialize a repo for `hackthon/`** — `agent.py`/`prompt.py` still have zero git history
   across all 4 sessions now. Every session's changes to these two files exist only on disk + in
   the deployed Cycls container.
7. **Open a PR from `agent-integration` into `main`** — still hasn't happened across any session;
   `main` has none of this work.
8. **Fill in the 3 dead-link customers in Customer Search**, or remove them — `FinDNA Customer
   Search.dc.html:90–92` currently list خالد الدوسري/نوف الشمري/فهد العتيبي with `href: ''`;
   clicking them is a dead click with no error shown to the user.
9. **CORS is wide open** (`allow_origins=["*"]`, `agent.py:43`) — fine for a hackathon demo,
   tighten before anything more public.
10. **Pre-existing hardcoded secrets in `agent.py`** (not introduced by session 4, flagged again
    since it's adjacent to this session's Twilio-credential-handling decision in §4):
    `cycls.api_key` at `:64`, OpenRouter key in `.api_key(...)` on the `_llm_base` builder at
    `:431`. Both plaintext in source, in a directory not currently tracked by any git repo (item 6)
    — but if `hackthon/` ever is added to a repo, these need to move to `.env` first, matching the
    pattern already used for Twilio.
11. **Header docstring mismatch** — `agent.py:3–4` says `uv run cycls run main.py` /
    `uv run cycls deploy main.py`; the actual file is `agent.py`. Stale comment carried over from
    an original task brief that assumed a different filename (see `FINDNA_HANDOFF_CLAUDECODE_FULL.md`
    §1.1); cosmetic only, but worth fixing next time this file is touched since it's misleading to
    read.
12. **`agent.py`'s `findna.deploy()` (`:535`) is unguarded module-level code** — no
    `if __name__ == "__main__":`. Anything that merely imports/execs this file triggers a real
    deploy. No safe dry-run import exists for this file.

---

## 9. Deploy command and current agent endpoint

```bash
cd /Users/mhsn/VsCode/hackthon && uv run cycls deploy agent.py
```
- Deploys to: **`https://findna-agent.cycls.ai`**
- Endpoint: `POST /chat/completions` (also aliased at `/` and `/chat`)
- Request shape: `{"model":"findna-agent","messages":[{"role":"user","content":"[UC1|UC2|UC3|UC4|UC5]\n" + JSON.stringify(payload)}],"stream":false}` — `stream` is **ignored server-side**; every response is `text/event-stream` regardless.
- Response shape: SSE lines `data: {"choices":[{"delta":{"content": <string|thinking-object>}}]}`, terminated by `data: [DONE]`. Concatenate string-type `content` deltas in order; skip `{"type":"thinking",...}` objects (extended-thinking trace); extract the JSON via `indexOf('{')`/`lastIndexOf('}')` rather than assuming the whole reconstructed string parses cleanly on its own, since the model sometimes prefaces the JSON with plain-text reasoning.
- **Exception:** for `[UC5]` specifically, the response is still one SSE-wrapped JSON chunk, but it's the agent's own buffered-and-augmented JSON (with `sms_sent`/`sms_error` appended server-side, `agent.py:510–532`) — not a raw passthrough of the model's streamed output. **As of session 5, `sms_sent`/`sms_error` reflect a WhatsApp send via Twilio's sandbox (`agent.py:483`), not plain SMS** — see §3a.
- Image build: `cycls.Image().pip("requests", "python-dotenv").copy("prompt.py").copy(".env")` (`agent.py:55–63`) — both `prompt.py` and `.env` are copied into the deploy container at build time; `.env` never leaves the container / is never shipped to any browser-facing file.
- **Network note (session 5, §3b):** if `uv run cycls deploy agent.py` or a direct request to
  `*.cycls.ai` hangs/times out, don't assume Cycls is down — try `curl -4 https://api.cycls.ai`
  first. This sandbox's IPv6 path to `*.cycls.ai` resolves through a NAT64 synthesized address
  that has been unreliable; forcing IPv4 has consistently worked.
