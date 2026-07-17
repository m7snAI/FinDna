# FinDNA Hackathon — Claude Code Task

## Your job
Complete the AI agent integration for the FinDNA hackathon project.
Two tasks: fix the prompt file, then integrate the agent into the HTML dashboard.

---

## File locations on disk

```
/Users/mhsn/VsCode/
├── hackthon/
│   ├── main.py           ← Cycls agent (deployed, do not touch)
│   └── prompt.py         ← FIX THIS FILE
└── FinDNA-Banking-Application/
    ├── FinDNA Employee Dashboard.dc.html   ← INTEGRATE AGENT HERE
    └── FinDNA App.dc.html                  ← INTEGRATE AGENT HERE (second)
```

---

## Task 1 — Fix prompt.py

Open `/Users/mhsn/VsCode/hackthon/prompt.py`.

In the prompt string, find each of the 4 UC sections: `[UC4]`, `[UC3]`, `[UC1]`, `[UC2]`.

Each one has a line that says:
```
Start your response with { and end with }. Nothing else.
```

Immediately after that line (before the JSON schema block), add this line:
```
⚠️ DO NOT use ```json or ``` anywhere. Your entire response must be valid JSON starting with { and ending with }.
```

Note: because the file uses Python f-strings, `{` and `}` in the template are written as `{{` and `}}`. Do not change that — only add the warning line as plain text (no curly braces in it).

After editing, the section should look like:
```
**Output:** Respond with ONLY raw JSON — no markdown fences, no preamble, no explanation.
Start your response with { and end with }. Nothing else.
⚠️ DO NOT use ```json or ``` anywhere. Your entire response must be valid JSON starting with { and ending with }.

{{
  "summary": ...
```

Do this for all 4 UC sections. Save the file.

Then run in terminal:
```bash
cd /Users/mhsn/VsCode/hackthon
uv run cycls deploy main.py
```

Wait for deployment to finish and confirm the URL is still `https://findna-agent.cycls.ai`.

---

## Task 2 — Integrate agent into Employee Dashboard

Open `/Users/mhsn/VsCode/FinDNA-Banking-Application/FinDNA Employee Dashboard.dc.html`.

Read the full file. Find the hardcoded content:
1. The AI summary paragraph (Arabic text about the customer, likely contains "يبدو العميل" or similar)
2. The status badges (مؤهل لتمويل مركبة, سجل سداد نظيف, etc.)
3. The eligibility cards for: تمويل مركبة, تمويل شخصي, تمويل عقاري
4. The product recommendation cards

Add `data-` attributes to these elements so the script can find them:
- `data-ai-summary` on the summary paragraph/div
- `data-badge` on each badge element
- `data-eligibility="car_loan"` on the car loan card
- `data-eligibility="personal_loan"` on the personal loan card
- `data-eligibility="mortgage"` on the mortgage card
- `data-status` on the status label inside each eligibility card
- `data-note` on the note/description inside each eligibility card
- `data-recommendations` on the wrapper around the recommendation cards

Then paste the following complete script block just before `</body>`:

```html
<style>
@keyframes fdShimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}
.fd-loading {
  background: linear-gradient(90deg, #f0eef8 25%, #e0ddf0 50%, #f0eef8 75%);
  background-size: 400px 100%;
  animation: fdShimmer 1.4s infinite;
  border-radius: 8px;
  color: transparent !important;
  min-height: 1em;
}
.fd-badge-ok    { background: #e6f8f2 !important; color: #1a7a55 !important; }
.fd-badge-warn  { background: #fdf3e3 !important; color: #a05c00 !important; }
.fd-badge-danger{ background: #fde8e7 !important; color: #8b2020 !important; }
.fd-status-ok   { color: #3DBF8F !important; }
.fd-status-warn { color: #E0A45E !important; }
.fd-status-danger{ color: #E0564E !important; }
</style>

<script>
(function () {
  const CUSTOMER_DATA = {
    customer: {
      id: "100482913",
      name: "أحمد السالم",
      salary: 15700,
      additional_income: 0,
      balance: 44400,
      obligations: { car_loan: 1850, credit_cards: 650, monthly_bills: 780, personal_loan: 0, mortgage: 0 },
      total_obligations: 3280,
      monthly_surplus: 3900,
      dna_score: 82,
      commitment_score: 96,
      risk_level: "low",
      savings_rate: 0.12,
      income_stability: 0.94,
      dti_ratio: 0.21,
      spending_behavior: { restaurant_spending: 1860, weekend_spending_pct: 0.38, late_payments_24m: 0, impulse_score: 27 },
      loan_history: { car_loan_remaining: 44400, car_loan_monthly: 1850, on_time_payments_streak: 24 },
      goals: [
        { type: "car",       name: "تويوتا كامري",  target: 123000, saved: 52000,  deadline: "2028-03", progress: 0.42 },
        { type: "apartment", name: "شقة تمليك",     target: 585000, saved: 70200,  deadline: "2031-06", progress: 0.12 },
        { type: "travel",    name: "رحلة اليابان",  target: 25000,  saved: 17000,  deadline: "2026-12", progress: 0.68 }
      ]
    }
  };

  function safeParseJSON(raw) {
    let text = (raw || '').trim();
    text = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```\s*$/i, '');
    const start = text.indexOf('{');
    const end   = text.lastIndexOf('}');
    if (start === -1 || end === -1) throw new Error('No JSON found');
    return JSON.parse(text.slice(start, end + 1));
  }

  async function callAgent(mode, data) {
    const res = await fetch('https://findna-agent.cycls.ai/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'findna-agent',
        messages: [{ role: 'user', content: `[${mode}]\n` + JSON.stringify(data) }],
        stream: false
      })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    return safeParseJSON(d?.choices?.[0]?.message?.content || '');
  }

  async function loadDashboard() {
    console.log('[FinDNA] 🧬 Calling agent...');

    const summaryEl = document.querySelector('[data-ai-summary]');
    if (summaryEl) {
      summaryEl.dataset.orig = summaryEl.textContent;
      summaryEl.classList.add('fd-loading');
    }

    try {
      const r = await callAgent('UC4', CUSTOMER_DATA);
      console.log('[FinDNA] ✅', r);

      // Summary
      if (summaryEl) {
        summaryEl.classList.remove('fd-loading');
        summaryEl.textContent = r.summary;
      }

      // Badges
      const badgeEls = document.querySelectorAll('[data-badge]');
      (r.badges || []).forEach((b, i) => {
        if (badgeEls[i]) {
          badgeEls[i].textContent = b.text;
          badgeEls[i].className = badgeEls[i].className.replace(/fd-badge-\w+/g, '');
          badgeEls[i].classList.add('fd-badge-' + b.tone);
        }
      });

      // Eligibility cards
      ['car_loan', 'personal_loan', 'mortgage'].forEach(key => {
        const card = document.querySelector(`[data-eligibility="${key}"]`);
        const data = r.eligibility?.[key];
        if (!card || !data) return;

        const statusEl = card.querySelector('[data-status]');
        const noteEl   = card.querySelector('[data-note]');
        if (statusEl) {
          statusEl.textContent = data.status;
          statusEl.className = statusEl.className.replace(/fd-status-\w+/g, '');
          statusEl.classList.add('fd-status-' + data.tone);
        }
        if (noteEl) noteEl.textContent = data.note;
      });

      // Recommendations
      const recWrapper = document.querySelector('[data-recommendations]');
      if (recWrapper && r.recommendations?.length) {
        const cards = recWrapper.querySelectorAll('[data-rec-card]');
        r.recommendations.forEach((rec, i) => {
          if (cards[i]) {
            const t = cards[i].querySelector('[data-rec-title]');
            const d = cards[i].querySelector('[data-rec-reason]');
            if (t) t.textContent = rec.title;
            if (d) d.textContent = rec.reason;
          }
        });
      }

      console.log('[FinDNA] 🎯 Done');
    } catch (err) {
      console.error('[FinDNA] ❌', err);
      if (summaryEl) {
        summaryEl.classList.remove('fd-loading');
        summaryEl.textContent = summaryEl.dataset.orig || 'تعذّر تحميل التحليل.';
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(loadDashboard, 500));
  } else {
    setTimeout(loadDashboard, 500);
  }
})();
</script>
```

Save the file. Open it in a browser. Open DevTools console. Confirm you see:
- `[FinDNA] ✅` followed by the JSON object
- `[FinDNA] 🎯 Done`
- The Arabic summary text has changed on screen from hardcoded to AI-generated

---

## Task 3 — Integrate agent into the Customer App (FinDNA App.dc.html)

Open `/Users/mhsn/VsCode/FinDNA-Banking-Application/FinDNA App.dc.html`.

Read the file carefully. Find the JavaScript `Component` class that extends `DCLogic`.

Inside the class, find the `state` object. Add these new keys to it:
```javascript
aiMorningBriefing: 'جارٍ تحميل تحليلك المالي...',
aiDailyInsight: '',
aiRec1Title: '',
aiRec1Subtitle: '',
aiRec2Title: '',
aiRec2Subtitle: '',
aiRec3Title: '',
aiRec3Subtitle: '',
aiLoaded: false,
```

Find the `renderVals()` method. Add these fields to its return object (matching the keys above).

Find or add `componentDidMount()`. Inside it, call `this._loadAIContent()`.

Add this method to the class:

```javascript
async _loadAIContent() {
  const CUSTOMER_DATA = {
    customer: {
      id: "100482913",
      name: "أحمد السالم",
      salary: 15700,
      dna_score: 82,
      commitment_score: 96,
      risk_level: "low",
      savings_rate: 0.12,
      income_stability: 0.94,
      dti_ratio: 0.21,
      monthly_surplus: 3900,
      total_obligations: 3280,
      spending_behavior: { restaurant_spending: 1860, weekend_spending_pct: 0.38, late_payments_24m: 0, impulse_score: 27 },
      goals: [
        { type: "car",       name: "تويوتا كامري",  target: 123000, saved: 52000,  deadline: "2028-03", progress: 0.42 },
        { type: "apartment", name: "شقة تمليك",     target: 585000, saved: 70200,  deadline: "2031-06", progress: 0.12 },
        { type: "travel",    name: "رحلة اليابان",  target: 25000,  saved: 17000,  deadline: "2026-12", progress: 0.68 }
      ]
    }
  };

  try {
    const res = await fetch('https://findna-agent.cycls.ai/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'findna-agent',
        messages: [{ role: 'user', content: '[UC2]\n' + JSON.stringify(CUSTOMER_DATA) }],
        stream: false
      })
    });
    const d = await res.json();
    let text = (d?.choices?.[0]?.message?.content || '').trim();
    text = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```\s*$/i, '');
    const start = text.indexOf('{');
    const end   = text.lastIndexOf('}');
    const r = JSON.parse(text.slice(start, end + 1));

    this.setState({
      aiMorningBriefing: r.morning_briefing || '',
      aiDailyInsight:    r.daily_insight    || '',
      aiRec1Title:    r.recommendations?.[0]?.title    || '',
      aiRec1Subtitle: r.recommendations?.[0]?.subtitle || '',
      aiRec2Title:    r.recommendations?.[1]?.title    || '',
      aiRec2Subtitle: r.recommendations?.[1]?.subtitle || '',
      aiRec3Title:    r.recommendations?.[2]?.title    || '',
      aiRec3Subtitle: r.recommendations?.[2]?.subtitle || '',
      aiLoaded: true,
    });
  } catch (err) {
    console.error('[FinDNA App] ❌', err);
  }
}
```

Then in the HTML template, find the hardcoded morning briefing text (in the `ai` screen section) and replace it with `{{ aiMorningBriefing }}`.

Find the hardcoded recommendation titles/subtitles and replace with:
- `{{ aiRec1Title }}`, `{{ aiRec1Subtitle }}`
- `{{ aiRec2Title }}`, `{{ aiRec2Subtitle }}`
- `{{ aiRec3Title }}`, `{{ aiRec3Subtitle }}`

Find the home screen "رؤية اليوم" insight text and replace with `{{ aiDailyInsight }}`.

Save and test in browser.

---

## Summary of what to do, in order

1. Edit `prompt.py` → add ⚠️ line to all 4 UC sections → redeploy
2. Edit `FinDNA Employee Dashboard.dc.html` → add data attributes + paste script → test in browser
3. Edit `FinDNA App.dc.html` → add state + method + wire up template bindings → test in browser

Report back with any errors from the browser console.
