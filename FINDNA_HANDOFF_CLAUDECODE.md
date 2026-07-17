# FinDNA — Session Handoff (Claude Code)

Session date: 2026-07-14
Scope: wire the deployed FinDNA Cycls agent into the two hackathon HTML dashboards, per `/Users/mhsn/VsCode/hackthon/CLAUDE_CODE_TASK.md`.

This document is written for whoever picks this up next — human or AI. It covers every bug found, the exact fix applied, what was verified and how, what's still open, and files/paths you'll need.

---

## 1. Files touched this session

| File | Repo | Committed? |
|---|---|---|
| `/Users/mhsn/VsCode/hackthon/prompt.py` | none (untracked, `hackthon/` isn't part of any git repo) | **No** |
| `/Users/mhsn/VsCode/hackthon/agent.py` | none (untracked) | **No** |
| `/Users/mhsn/VsCode/FinDNA-Banking-Application/FinDNA Employee Dashboard.dc.html` | `FinDNA-Banking-Application` (remote: `github.com/Afnan-Jadidi/FinDNA-Banking-Application`) | **Yes** — branch `agent-integration`, commit `0ff649e` |
| `/Users/mhsn/VsCode/FinDNA-Banking-Application/FinDNA App.dc.html` | same | **Yes** — same commit |

**Important:** `prompt.py` and `agent.py` live in `/Users/mhsn/VsCode/hackthon/`, which is not a git repository (confirmed via `git -C /Users/mhsn/VsCode status --short hackthon/` → `?? hackthon/`, untracked in the parent monorepo). The only record of the prompt/CORS fixes is the deployed container and the files on disk. **If you want these changes preserved anywhere durable, commit them somewhere before touching the files again.**

The dashboard changes were pushed:
```
branch: agent-integration
commit: 0ff649e "feat: integrate FinDNA live AI agent — UC2/UC4, SSE parsing, CORS fix, data attributes"
remote: https://github.com/Afnan-Jadidi/FinDNA-Banking-Application.git
```
No PR opened yet against `main`.

---

## 2. Task 1 — `prompt.py` fix + redeploy

### What the task asked
Add a warning line after `Start your response with { and end with }. Nothing else.` in all 4 UC sections ([UC4], [UC3], [UC1], [UC2]), telling the model not to use ` ```json ` fences.

### Bug found #1 — brace-escaping in an f-string
The task file's literal instruction said to add the line as "plain text (no curly braces in it)":
```
⚠️ DO NOT use ```json or ``` anywhere. Your entire response must be valid JSON starting with { and ending with }.
```
This is wrong — the sentence **does** contain literal `{` and `}`. `prompt.py`'s `build_prompt()` returns an f-string (`return f"""..."""`), so any literal brace must be doubled (`{{` / `}}`) or Python raises `SyntaxError: f-string: expecting a valid expression after '{'`. Confirmed this exact error on the first deploy attempt.

**Fix applied:** inserted the line with escaped braces after all 4 occurrences of `Start your response with {{ and end with }}. Nothing else.`:
```
⚠️ DO NOT use ```json or ``` anywhere. Your entire response must be valid JSON starting with {{ and ending with }}.
```
Verified by importing `build_prompt()` locally and regex-checking the *rendered* output has single braces (`{` / `}`), not doubled — confirms the f-string escaping round-trips correctly.

### Bug found #2 — wrong filename
The task file's file map says the agent is `hackthon/main.py`. That file does not exist. The real (only) agent file is `hackthon/agent.py`. All deploy commands below use `agent.py`.

### Deploy
```bash
cd /Users/mhsn/VsCode/hackthon
uv run cycls deploy agent.py
```
Deployed successfully, URL unchanged: `https://findna-agent.cycls.ai`.

---

## 3. Task 2 — Employee Dashboard integration

File: `FinDNA-Banking-Application/FinDNA Employee Dashboard.dc.html`

### Data attributes added
| Attribute | Where | Line(s) as of last edit |
|---|---|---|
| `data-ai-summary` | wrapper div around the AI summary paragraph | 88 |
| `data-badge` (×3) | `<span>` wrapping each badge's `<x-import>` | 92–94 |
| `data-eligibility="car_loan"` / `"personal_loan"` / `"mortgage"` | the 3 eligibility row `<div>`s | 167, 174, 181 |
| `data-status` | `<span>` wrapping each eligibility badge's `<x-import>`, nested inside the matching `data-eligibility` div | 171, 178, 185 |
| `data-note` | the amount/note `<span>` inside each eligibility row | 170, 177, 184 |
| `data-recommendations` | wrapper `<div>` around the 4 recommendation cards | 240 |
| `data-rec-card` (×4) | each recommendation card `<div>` | 241, 249, 254, 259 |
| `data-rec-title` / `data-rec-reason` | title/reason elements inside each rec card | e.g. 243/246 |

`data-rec-card`, `data-rec-title`, `data-rec-reason` were **not** in the task file's attribute list, but the pasted script's Recommendations block requires them (`recWrapper.querySelectorAll('[data-rec-card]')` etc.) — added them to make the given script actually functional.

### Bug found #3 — `<x-import>` custom elements get destroyed on render
Initially placed `data-badge` / `data-status` directly on the `<x-import component-from-global-scope="...Badge" ...>` elements. Headless-browser inspection (Playwright) showed these attributes vanished from the live DOM after page load — `document.querySelectorAll('[data-badge]')` returned 0 elements even though the source HTML had them.

**Root cause:** this project's design-system runtime (`_ds_bundle.js`, loaded via `<script>` in `<helmet>`) walks the DOM, finds `<x-import>` tags, and replaces them wholesale with freshly rendered markup — any attribute placed directly on the `<x-import>` tag that isn't part of its own known prop set gets dropped in the process. Plain HTML elements (`<div>`, `<span>`) are untouched and keep custom `data-*` attributes fine.

**Fix:** wrapped each Badge `<x-import>` in a plain `<span data-badge>` / `<span data-status>`. The pasted script's `textContent = ...` assignment then replaces the whole wrapper's contents (destroying the inner `<x-import>`, replacing it with plain text) and applies the `fd-badge-*` / `fd-status-*` CSS classes to the wrapper — which is what the task's own CSS block was designed for in the first place (`.fd-badge-ok { background:...; color:... }` etc. targets a plain element, not a design-system component).

Verified via Playwright: `[data-badge]` count = 3, `[data-status]` count = 3 after page load.

### Bug found #4 — the endpoint always streams SSE, `stream: false` is ignored
The task's given script does:
```js
const d = await res.json();
return safeParseJSON(d?.choices?.[0]?.message?.content || '');
```
This can **never** work. Confirmed via `curl -D -` that the response headers are always `content-type: text/event-stream; charset=utf-8`, regardless of `"stream": false` in the request body. Traced this to the Cycls framework itself:

`~/.venv/lib/python3.13/site-packages/cycls/agent/web/server.py`, inside `web(func, config, ...)`:
```python
@app.post("/")
@app.post("/chat")
@app.post("/chat/completions")
async def back(request: Request, user: Optional[User] = auth):
    ...
    stream = openai_encoder(stream) if request.url.path == "/chat/completions" else encoder(...)
    return StreamingResponse(stream, media_type="text/event-stream")
```
`StreamingResponse` with `text/event-stream` is hardcoded — the `stream` field in the request body is never even read by this handler. So every response is SSE: a sequence of `data: {...}\n\n` lines, each `{"choices":[{"delta":{"content": ... }}]}`, terminated by `data: [DONE]`. The `content` value is sometimes a string (real output token) and sometimes an object `{"type": "thinking", "thinking": "..."}` (the model's extended-thinking trace) — these must be filtered out, not concatenated into the answer.

**Fix applied** — in `callAgent()` (Employee Dashboard) and `_loadAIContent()` (Customer App), replaced the `res.json()` call with:
```js
const raw = await res.text();
let text = '';
for (const line of raw.split('\n')) {
  const trimmed = line.trim();
  if (!trimmed.startsWith('data:')) continue;
  const payload = trimmed.slice(5).trim();
  if (payload === '[DONE]') continue;
  let evt;
  try { evt = JSON.parse(payload); } catch { continue; }
  const content = evt?.choices?.[0]?.delta?.content ?? evt?.choices?.[0]?.message?.content;
  if (typeof content === 'string') text += content;
}
return safeParseJSON(text); // (or JSON.parse after brace-slicing, in the Customer App version)
```
This skips non-string (`thinking`) deltas, concatenates real content deltas in order, and reconstructs the full JSON text — which `safeParseJSON` then extracts via `indexOf('{')` / `lastIndexOf('}')`, tolerant of any leading prose the model emits before the JSON (observed: the model sometimes narrates its tool-calling plan in plain text before starting the JSON object).

Verified by writing a Node script that ran this exact parsing logic over a captured real response (`curl` output saved to a file) — reconstructed text parsed cleanly as JSON with all expected top-level keys (`summary`, `badges`, `eligibility`, `recommendations`, `investment_potential`, `risk_flags`, `confidence`).

### Script block
Pasted as given in the task, just before `</body>`, with only the `callAgent` fetch/parsing internals modified as above. Styling block (`fd-loading` shimmer, `fd-badge-*`, `fd-status-*`) pasted unmodified.

---

## 4. Task 3 — Customer App integration

File: `FinDNA-Banking-Application/FinDNA App.dc.html`

### State keys added (in the `Component extends DCLogic` class' `state = {...}`, around line 977)
```js
aiMorningBriefing: 'جارٍ تحميل تحليلك المالي...',
aiDailyInsight: '',
aiRec1Title: '', aiRec1Subtitle: '',
aiRec2Title: '', aiRec2Subtitle: '',
aiRec3Title: '', aiRec3Subtitle: '',
aiLoaded: false,
```

### `renderVals()` return object
Added a block near the end of the return object (before the closing `};`, around line 1391):
```js
// ai content (AI-generated)
aiMorningBriefing: s.aiMorningBriefing,
aiDailyInsight: s.aiDailyInsight,
aiRec1Title: s.aiRec1Title, aiRec1Subtitle: s.aiRec1Subtitle,
aiRec2Title: s.aiRec2Title, aiRec2Subtitle: s.aiRec2Subtitle,
aiRec3Title: s.aiRec3Title, aiRec3Subtitle: s.aiRec3Subtitle,
aiLoaded: s.aiLoaded,
```

### Lifecycle hook + method (around line 1000–1067)
```js
componentDidMount() { this._loadAIContent(); }
```
`componentWillUnmount()` already existed in the original file, confirming the framework supports this lifecycle pair.

`_loadAIContent()` — same shape as the task file's given method, with the **same SSE-parsing fix** as the dashboard's `callAgent()` applied inline (see §3, bug #4). Calls `[UC2]` mode, populates the 8 `ai*` state keys via `this.setState(...)`, logs to console only on error (`console.error('[FinDNA App] ❌', err)`).

### Template bindings replaced
| Was (hardcoded) | Now | Line |
|---|---|---|
| Home screen "رؤية اليوم" insight paragraph | `{{ aiDailyInsight }}` | 223 |
| AI screen morning-briefing paragraph | `{{ aiMorningBriefing }}` | 491 |
| Rec card 1 title / subtitle | `{{ aiRec1Title }}` / `{{ aiRec1Subtitle }}` | 499–500 |
| Rec card 2 title / subtitle | `{{ aiRec2Title }}` / `{{ aiRec2Subtitle }}` | 512–513 |
| Rec card 3 title / subtitle | `{{ aiRec3Title }}` / `{{ aiRec3Subtitle }}` | 525–526 |

No `data-*` attributes were needed here since this file uses the framework's own template-binding syntax (`{{ }}`) rather than raw DOM queries.

---

## 5. Bug found #5 (the big one) — CORS: no browser could ever reach the agent

Not in the task file at all. Discovered while verifying Task 2 in a headless browser: every fetch to `https://findna-agent.cycls.ai/chat/completions` failed with
```
Access to fetch ... has been blocked by CORS policy: Response to preflight request
doesn't pass access control check: No 'Access-Control-Allow-Origin' header is present
```
Reproduced from both `file://` origin and `http://localhost:8934` — this wasn't an origin-specific quirk, the server sent **no** CORS headers to anyone. Without this fix, neither dashboard could ever work from a real browser, regardless of how correct the client-side code was.

### Investigation
- `cycls.Web()` (the builder used in `agent.py`) exposes no `.cors()` or equivalent option — confirmed via `dir(cycls.Web)` → `['analytics', 'auth', 'cms', 'copy_public', 'suggestions', 'theme', 'title']`.
- `cycls.App` / `cycls.Agent` likewise expose nothing CORS-related.
- Traced into the framework source: `cycls/agent/web/server.py`'s `web(func, config, ...)` builds a bare `app = FastAPI()` with **zero** middleware registered, ever.
- `cycls/agent/main.py`'s `Agent._prepare_func` defines:
  ```python
  def runner(port):
      ...
      _serve(web(user_func, config, extra_routers=routers, auth=provider), port)
  self.func = runner
  ```
  `web` here is a **free variable** resolved from `cycls.agent.main`'s own module globals at call time (not captured at def time) — so reassigning `cycls.agent.main.web` before the container starts serving changes what `runner()` actually calls, without touching any framework internals.

### Bug found #6 — `cycls.agent` is a function, not the submodule
First attempt: `import cycls.agent.main as _cycls_agent_main`. This fails **unconditionally** (reproduced even in a bare `python3 -c` with no other code involved):
```
ImportError: cannot import name 'main' from 'factory' (unknown location)
```
Root cause: `cycls/__init__.py` does `from .agent.main import agent`, binding the top-level name `cycls.agent` to the `@cycls.agent` **decorator function** (its actual `__name__` is `factory`, from `_make_decorator`'s inner function in `cycls/app/main.py`). This overwrites the attribute Python's import machinery would otherwise have set (`cycls.agent` → the submodule). So any code doing plain attribute-style dotted import (`import cycls.agent.main`) breaks, while `sys.modules['cycls.agent.main']` is still perfectly intact underneath.

**Fix:** use `importlib.import_module("cycls.agent.main")`, which resolves through `sys.modules` and sidesteps the attribute shadowing entirely. Verified working in isolation before touching `agent.py`.

### The fix, as landed in `agent.py` (top of file, after the `cycls` import)
```python
import importlib

import cycls
from prompt import build_prompt

# ----------------------------------------------------------------------
# CORS
# ----------------------------------------------------------------------
# cycls.Web() exposes no CORS option and the FastAPI app built inside
# cycls.agent.web.server.web() has no CORSMiddleware, so browser fetches
# from the dashboard HTML files are blocked. Agent._prepare_func's runner()
# resolves `web` dynamically from cycls.agent.main's module globals at call
# time, so patching the name here redirects it without touching the
# framework's own FastAPI route/streaming logic.
# (cycls.agent is the @cycls.agent decorator function, not the submodule,
# so `import cycls.agent.main` fails — importlib.import_module sidesteps
# that shadowing by resolving through sys.modules instead of attributes.)
_cycls_agent_main = importlib.import_module("cycls.agent.main")
_original_web = _cycls_agent_main.web


def _web_with_cors(*args, **kwargs):
    app = _original_web(*args, **kwargs)
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


_cycls_agent_main.web = _web_with_cors
```
`allow_origins=["*"]` was used for hackathon speed. **Tighten this before anything resembling production** — see §7.

### Deploy caveat worth knowing
`agent.py`'s last line, `findna.deploy()`, is unguarded module-level code (no `if __name__ == "__main__":`). Any script that `exec`s or imports this file — including a "just check it imports cleanly" sanity check — **will actually trigger a real deploy**. This happened once during this session (a diagnostic re-run of the CLI's own `_load_target` loading logic ended up deploying for real). Harmless here since the deploy succeeded and was the desired end state anyway, but be aware: **there is no safe "just import it" dry run for this file.**

### Verification
1. **Preflight check** — `curl -X OPTIONS .../chat/completions -H "Origin: ..." -H "Access-Control-Request-Method: POST"` → `access-control-allow-origin: *` present. Confirmed live post-redeploy.
2. **Full end-to-end, Employee Dashboard** — headless Playwright, serving the dashboard over a local `python3 -m http.server 8934` (not `file://` — see §6 for why), waited for the `[FinDNA] 🎯 Done` console log. **Fully succeeded**: summary text, all 3 badges, all 3 eligibility statuses/notes, and the recommendation titles all changed from the hardcoded Arabic placeholders to genuinely different agent-generated Arabic text. No errors.
3. **Full end-to-end, Customer App** — same approach. Network layer confirmed working (POST fires, 200 response, no `[FinDNA App] ❌` error ever observed across three separate test runs), but the automated "did the placeholder text change" check did not observe a change within the test's 200-second window in the last run. See §8 for why this is inconclusive rather than a known failure.

---

## 6. Test infrastructure set up this session (for whoever wants to re-verify)

- Playwright (`playwright@1.61.1` + Chromium) installed into a throwaway npm project at `/private/tmp/claude-501/-Users-mhsn-VsCode/533490ca-eaab-4188-a960-142412766389/scratchpad/pw_test/`. **This is a session-scratchpad path and will not survive** — if you want to re-run these tests, redo `npm install playwright && npx playwright install chromium` somewhere durable.
- Testing must go over `http://` (e.g. `python3 -m http.server 8934` from inside `FinDNA-Banking-Application/`), not `file://`. Under `file://`, the design-system runtime's own self-bootstrap fetch fails (`Fetch API cannot load file:///... URL scheme "file" is not supported`), which prevents the `<x-import>` components (including the Badge elements) from ever rendering at all — an unrelated failure mode that has nothing to do with the agent integration and will confuse you if you don't know about it going in.
- Test scripts used (not preserved beyond the scratchpad): a `test_dashboard.js` that navigates to the Employee Dashboard, listens for console messages, and asserts `[data-ai-summary]`, `[data-badge]`, `[data-status]`, `[data-note]`, `[data-rec-title]` content; a `test_app.js` that navigates to the Customer App and polls `document.querySelector('x-dc').textContent` for the placeholder string disappearing, since that file has no `data-*` hooks to query directly.

---

## 7. Known issues / follow-ups for the next developer

1. **CORS is wide open (`allow_origins=["*"]`).** Fine for a hackathon demo, not fine beyond that. Tighten to the actual dashboard origin(s) once those have real hosting URLs.
2. **Agent response latency is high and unpredictable.** Directly measured full-response times: ~62s and ~130s (via `curl -w "%{time_total}"`) for UC4 (Employee Dashboard, which per `prompt.py`'s tool rules calls `calculate_dna_score` + `assess_loan_eligibility` for each product); the Customer App's UC2 call (which per the same tool rules calls **no** tools) took longer than 200s in the last observed run with no error, just still-pending. There's no obvious explanation for UC2 being slower than UC4 — worth instrumenting/logging on the agent side if this matters for the demo.
3. **Neither dashboard script sets a fetch timeout or shows request progress.** The loading shimmer (`fd-loading` class / `جارٍ تحميل تحليلك المالي...`) will just sit there for however long the agent takes — potentially minutes — with zero feedback to the user about whether it's still working or stuck. Worth adding a timeout + a "still thinking, hang tight" message if this ships to an actual demo audience.
4. **The Customer App integration is not fully confirmed end-to-end.** The network layer works (200 responses, zero errors across every test run), and the code is structurally identical to the Employee Dashboard's confirmed-working integration, but automated content-change verification never completed within a 200s test window on this file specifically. Do a **manual browser check** (see §8) before considering this done.
5. **`hackthon/` has no git repo at all.** `prompt.py` and `agent.py` changes exist only on disk and in the deployed container — there's no commit history, no diff trail, nothing to `git blame`. If this matters, initialize a repo (or move these files into an existing one) and commit.
6. **Hardcoded secrets in `agent.py`** (pre-existing, not introduced this session): `cycls.api_key = "ak_..."` and an OpenRouter key passed to `.api_key(...)` on the `cycls.LLM()` builder, both in plaintext in the source file. Not this session's problem to fix, but flagging it since it's sitting right next to code that just got touched — worth moving to environment variables / secrets manager before this goes anywhere more public than a hackathon.
7. **`REPO_CONTEXT.md`** was picked up by `git add -A` and committed alongside the dashboard changes (it was a pre-existing untracked file in `FinDNA-Banking-Application/`, not authored this session — a briefing doc written for an AI describing the repo's structure). Not a problem, just noting it's now part of the `agent-integration` branch's diff if you're reviewing it.
8. **No PR opened yet** for the `agent-integration` branch. It's pushed to `origin` and ready: `https://github.com/Afnan-Jadidi/FinDNA-Banking-Application/pull/new/agent-integration`.

---

## 8. Suggested next step: manual verification of the Customer App

Quickest way to close out the one open question from this session:
1. `cd "/Users/mhsn/VsCode/FinDNA-Banking-Application" && python3 -m http.server 8934`
2. Open `http://localhost:8934/FinDNA%20App.dc.html` in a real browser (not `file://`).
3. Open DevTools console.
4. Navigate to the "AI" tab/screen (bottom nav, "المساعد" icon) and watch the morning-briefing card.
5. Wait up to ~2–3 minutes. Watch for `[FinDNA App] ❌` in the console (failure) vs. the briefing text changing from the placeholder Arabic sentence to something new (success).
6. Also check the home screen's "رؤية اليوم" card and the AI screen's 3 recommendation cards update similarly.

If it works, this handoff's only open item is closed and both integrations are fully confirmed.

---

## 9. Quick reference — deployed endpoint

- URL: `https://findna-agent.cycls.ai`
- Chat endpoint: `POST /chat/completions` (also aliased at `POST /` and `POST /chat`)
- Request body: `{"model": "findna-agent", "messages": [{"role": "user", "content": "[UC2]\n" + JSON.stringify(customerData)}], "stream": false}` — the `stream` field is currently ignored server-side; response is **always** SSE.
- Response: `text/event-stream`, lines of `data: {"choices":[{"delta":{"content": <string|thinking-object>}}]}`, terminated by `data: [DONE]`. Concatenate string-type `content` deltas in order to reconstruct the model's full text output, then extract the JSON object from within it (model sometimes prefaces the JSON with plain-text reasoning).
- Modes: prefix the `content` with `[UC1]` / `[UC2]` / `[UC3]` / `[UC4]` to select the flow (see `prompt.py` for each mode's expected input/output shape).
