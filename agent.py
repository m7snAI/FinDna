# FinDNA — Financial DNA Agent built on Cycls.
#
# Run locally:   uv run cycls run main.py
# Deploy:        uv run cycls deploy main.py

import asyncio
import json
import os
import random as _random
import re as _re
from datetime import datetime, timedelta, timezone

import importlib

import requests
from dotenv import load_dotenv

import cycls
from prompt import build_prompt

# Twilio creds live in .env (gitignored, copied into the deploy image below)
# — never in source, never shipped to the browser. See _send_sms().
load_dotenv()

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

# ----------------------------------------------------------------------
# Image
# ----------------------------------------------------------------------
image = (
    cycls.Image()
    .pip(
        "requests",
        "python-dotenv",
    )
    .copy("prompt.py")
    .copy(".env")
)
cycls.api_key = os.environ.get("CYCLS_API_KEY")

web = (
    cycls.Web()
    .title("FinDNA — Financial DNA Agent")
    # Serves hackthon/findna-logo.jpg at /public/findna-logo.jpg. No header=/
    # intro= mechanism exists in the installed cycls (0.0.2.132, confirmed
    # against 0.0.2.134 too) to actually render this above the chat — this
    # only makes the file reachable, it isn't displayed anywhere yet.
    .copy_public("findna-logo.jpg")
)

# ----------------------------------------------------------------------
# Custom tools
# ----------------------------------------------------------------------
TOOLS = [
    {
        "name": "calculate_dna_score",
        "description": (
            "Calculate the Financial DNA score for a customer based on their financial profile. "
            "Use this whenever you need to compute or verify a DNA score. "
            "Pass the raw financial metrics and get back a weighted score out of 100."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "savings_rate": {
                    "type": "number",
                    "description": "Monthly savings as a fraction of income (e.g. 0.12 for 12%)",
                },
                "income_stability": {
                    "type": "number",
                    "description": "Income stability score as a fraction (e.g. 0.94 for 94%)",
                },
                "dti_ratio": {
                    "type": "number",
                    "description": "Debt-to-income ratio as a fraction (e.g. 0.21 for 21%)",
                },
                "commitment_score": {
                    "type": "number",
                    "description": "Payment commitment score out of 100 (e.g. 96)",
                },
            },
            "required": ["savings_rate", "income_stability", "dti_ratio", "commitment_score"],
        },
    },
    {
        "name": "assess_loan_eligibility",
        "description": (
            "Assess a customer's loan eligibility and calculate approval probability. "
            "Use this for UC3 loan recommendation flow. "
            "Returns current probability, blocking factors, and improvement scenarios."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "monthly_income": {
                    "type": "number",
                    "description": "Total monthly income in SAR",
                },
                "total_obligations": {
                    "type": "number",
                    "description": "Total current monthly obligations in SAR",
                },
                "requested_loan_monthly": {
                    "type": "number",
                    "description": "Estimated monthly payment for the requested loan in SAR",
                },
                "income_stability": {
                    "type": "number",
                    "description": "Income stability as a fraction (0-1)",
                },
                "late_payments_24m": {
                    "type": "number",
                    "description": "Number of late payments in the last 24 months",
                },
                "dna_score": {
                    "type": "number",
                    "description": "Current Financial DNA score out of 100",
                },
            },
            "required": [
                "monthly_income",
                "total_obligations",
                "requested_loan_monthly",
                "income_stability",
                "late_payments_24m",
                "dna_score",
            ],
        },
    },
    {
        "name": "analyze_goals",
        "description": (
            "Analyze customer goals against their current savings rate and financial capacity. "
            "Returns feasibility, required monthly savings, and projected completion dates."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "monthly_surplus": {
                    "type": "number",
                    "description": "Available monthly surplus in SAR after all expenses",
                },
                "goals": {
                    "type": "array",
                    "description": "List of financial goals",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "target": {"type": "number"},
                            "saved": {"type": "number"},
                            "deadline": {"type": "string", "description": "YYYY-MM format"},
                        },
                    },
                },
            },
            "required": ["monthly_surplus", "goals"],
        },
    },
]

# ----------------------------------------------------------------------
# Tool handlers
# ----------------------------------------------------------------------

def _calculate_dna_score_core(savings_rate, income_stability, dti_ratio, commitment_score) -> dict:
    """The actual DNA-score math — unchanged from the original tool handler,
    just extracted so get_customer_segment() (customer data layer, UC6) can
    call it directly without going through the async tool-call machinery."""
    # Weighted formula
    savings_component = min(savings_rate * 100, 100) * 0.30
    stability_component = min(income_stability * 100, 100) * 0.25
    dti_component = max(0, (1 - dti_ratio) * 100) * 0.25
    commitment_component = min(commitment_score, 100) * 0.20

    dna_score = round(
        savings_component +
        stability_component +
        dti_component +
        commitment_component
    )

    # Risk level
    risk_score = round(dti_ratio * 100 * 0.5 + (1 - income_stability) * 100 * 0.3 + max(0, 20 - savings_rate * 100) * 0.2)
    if risk_score < 30:
        risk_level = "منخفض"
    elif risk_score < 60:
        risk_level = "متوسط"
    else:
        risk_level = "مرتفع"

    return {
        "dna_score": dna_score,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "breakdown": {
            "savings_component": round(savings_component, 1),
            "stability_component": round(stability_component, 1),
            "dti_component": round(dti_component, 1),
            "commitment_component": round(commitment_component, 1),
        }
    }


def make_calculate_dna_score():
    async def handler(args):
        savings_rate = float(args.get("savings_rate", 0))
        income_stability = float(args.get("income_stability", 0))
        dti_ratio = float(args.get("dti_ratio", 0))
        commitment_score = float(args.get("commitment_score", 0))
        return _calculate_dna_score_core(savings_rate, income_stability, dti_ratio, commitment_score)

    return handler


def make_assess_loan_eligibility():
    async def handler(args):
        monthly_income = float(args.get("monthly_income", 0))
        total_obligations = float(args.get("total_obligations", 0))
        requested_loan_monthly = float(args.get("requested_loan_monthly", 0))
        income_stability = float(args.get("income_stability", 0))
        late_payments_24m = int(args.get("late_payments_24m", 0))
        dna_score = float(args.get("dna_score", 0))

        if monthly_income <= 0:
            return {"error": "Monthly income must be greater than 0"}

        # Current DTI
        current_dti = total_obligations / monthly_income
        # DTI after loan
        new_dti = (total_obligations + requested_loan_monthly) / monthly_income
        bank_dti_limit = 0.45

        # Calculate approval probability
        probability = 0
        blocking_factors = []

        # DTI scoring
        if new_dti > bank_dti_limit:
            blocking_factors.append(f"نسبة الدين إلى الدخل بعد القرض ({round(new_dti*100)}%) تتجاوز الحد الأقصى للبنك (45%)")
        elif new_dti < 0.25:
            probability += 30
        elif new_dti < 0.35:
            probability += 20
        elif new_dti < 0.45:
            probability += 10

        # Income stability scoring
        if income_stability >= 0.90:
            probability += 25
        elif income_stability >= 0.80:
            probability += 15
        else:
            blocking_factors.append(f"استقرار الدخل ({round(income_stability*100)}%) أقل من الحد المطلوب (80%)")

        # Payment history
        if late_payments_24m == 0:
            probability += 25
        elif late_payments_24m <= 2:
            probability += 10
            blocking_factors.append(f"وجود {late_payments_24m} تأخير في السداد خلال 24 شهراً")
        else:
            blocking_factors.append(f"وجود {late_payments_24m} تأخيرات في السداد خلال 24 شهراً — يؤثر سلباً على الأهلية")

        # DNA score
        if dna_score >= 80:
            probability += 20
        elif dna_score >= 60:
            probability += 10

        # Cap at 95 if no blocking factors, 0 if DTI exceeded
        if new_dti > bank_dti_limit:
            probability = 0
            status = "غير مؤهل"
        elif probability >= 70:
            status = "مرتفع"
        elif probability >= 40:
            status = "متوسط"
        else:
            status = "منخفض"

        # Improvement scenarios
        improvement_plan = []

        # Scenario 1: Reduce obligations
        if total_obligations > 0:
            reduce_by = monthly_income * 0.05
            new_obligations = total_obligations - reduce_by
            new_dti_improved = (new_obligations + requested_loan_monthly) / monthly_income
            new_prob = min(95, probability + 15)
            improvement_plan.append({
                "action": f"خفّض التزاماتك الشهرية بـ {round(reduce_by):,} ريال",
                "impact": f"تخفيض نسبة الدين إلى {round(new_dti_improved*100)}%",
                "timeframe": "2-3 أشهر",
                "new_probability": new_prob
            })

        # Scenario 2: Increase income
        if income_stability < 0.90:
            improvement_plan.append({
                "action": "تعزيز استقرار مصدر الدخل",
                "impact": "+25 نقطة على احتمالية الموافقة",
                "timeframe": "3-6 أشهر",
                "new_probability": min(95, probability + 25)
            })

        # Scenario 3: Improve DNA score
        if dna_score < 80:
            improvement_plan.append({
                "action": "رفع درجة حمضك المالي عبر الادخار المنتظم",
                "impact": "+20 نقطة على احتمالية الموافقة",
                "timeframe": "3-4 أشهر",
                "new_probability": min(95, probability + 20)
            })

        headroom = max(0, bank_dti_limit - new_dti)

        return {
            "current_approval_probability": probability,
            "approval_status": status,
            "blocking_factors": blocking_factors,
            "improvement_plan": improvement_plan,
            "dti_analysis": {
                "current_dti": round(current_dti * 100, 1),
                "dti_after_loan": round(new_dti * 100, 1),
                "bank_limit": 45,
                "headroom": round(headroom * 100, 1)
            }
        }

    return handler


def make_analyze_goals():
    async def handler(args):
        monthly_surplus = float(args.get("monthly_surplus", 0))
        goals = args.get("goals", [])

        results = []
        for goal in goals:
            name = goal.get("name", "")
            target = float(goal.get("target", 0))
            saved = float(goal.get("saved", 0))
            deadline_str = goal.get("deadline", "")

            remaining = max(0, target - saved)
            progress_pct = round((saved / target * 100) if target > 0 else 0)

            # Calculate months to deadline
            months_available = None
            if deadline_str:
                try:
                    deadline = datetime.strptime(deadline_str, "%Y-%m")
                    now = datetime.now()
                    months_available = (deadline.year - now.year) * 12 + (deadline.month - now.month)
                except Exception:
                    pass

            # Required monthly savings
            if months_available and months_available > 0:
                monthly_required = remaining / months_available
            else:
                monthly_required = remaining / 24  # default 2 years

            # Feasibility
            if monthly_surplus <= 0:
                feasibility = "صعب"
            elif monthly_required <= monthly_surplus * 0.3:
                feasibility = "ممكن"
            elif monthly_required <= monthly_surplus * 0.7:
                feasibility = "متحدٍّ"
            else:
                feasibility = "صعب"

            # Projected completion date at current savings rate
            if monthly_surplus > 0 and remaining > 0:
                months_to_complete = round(remaining / (monthly_surplus * 0.5))
                completion = datetime.now() + timedelta(days=months_to_complete * 30)
                completion_date = completion.strftime("%Y-%m")
            else:
                completion_date = "غير محدد"

            results.append({
                "goal": name,
                "target": target,
                "saved": saved,
                "remaining": remaining,
                "progress_pct": progress_pct,
                "monthly_required": round(monthly_required),
                "feasibility": feasibility,
                "completion_date": completion_date,
                "months_available": months_available,
            })

        return {"goals_analysis": results, "monthly_surplus": monthly_surplus}

    return handler


# ----------------------------------------------------------------------
# Dates
# ----------------------------------------------------------------------
_RIYADH_OFFSET = timedelta(hours=3)


def _riyadh_date() -> str:
    return (datetime.now(timezone.utc) + _RIYADH_OFFSET).date().strftime("%Y-%m-%d")


# ----------------------------------------------------------------------
# LLM
# ----------------------------------------------------------------------
_llm_base = (
    cycls.LLM()
    .model("openrouter/deepseek/deepseek-chat")
    .base_url("https://openrouter.ai/api/v1")
    .api_key(os.environ.get("OPENROUTER_API_KEY"))
    .max_tokens(4096)
    .tools(TOOLS)
    .on("calculate_dna_score", make_calculate_dna_score())
    .on("assess_loan_eligibility", make_assess_loan_eligibility())
    .on("analyze_goals", make_analyze_goals())
    .allowed_tools(["DataBase"])
    .sandbox(network=True)
)

# ----------------------------------------------------------------------
# ─── CUSTOMER DATA LAYER ───
# ----------------------------------------------------------------------
# calculate_dna_score / assess_loan_eligibility / analyze_goals above are
# real deterministic math — the gap was their INPUTS (dti_ratio, savings_rate,
# income_stability, commitment_score), which were previously free-estimated
# by the LLM from conversation text with no real data behind them. This
# section grounds those inputs in a synthetic transaction history for two
# fixed demo personas ("ahmed", "sara"), generated once at import time with
# fixed seeds so it's byte-identical on every run/redeploy — no live
# randomness, nothing regenerated per request.

_MERCHANTS = {
    "مطاعم": ["البيك", "كودو", "هرفي", "ستاربكس", "مطعم نجد", "بيتزا هت", "شاورمر بيت", "نادي الشيف"],
    "تسوق": ["إكسترا", "جرير", "سنتربوينت", "نمشي", "بنده", "لولو هايبرماركت", "الأندلس مول", "هوم سنتر"],
    "مواصلات": ["أرامكو", "بترومين", "أوبر", "كريم", "صيانة السيارات المتحدة"],
    "فواتير": ["الاتصالات السعودية STC", "الشركة السعودية للكهرباء", "شركة المياه الوطنية", "موبايلي", "زين السعودية"],
    "ترفيه": ["سينما VOX", "سينما امباير", "بارك ذا مول", "بولينج سنتر الرياض"],
    "صحة": ["صيدلية النهدي", "صيدلية الدواء", "مستشفى الدكتور سليمان الحبيب", "مستشفى المانع"],
    "تعليم": ["مكتبة جرير", "كورسيرا", "معهد الرياض للتدريب", "مدارس المنار الأهلية"],
    "أخرى": ["تحويل بنكي", "سحب نقدي - صراف آلي", "رسوم بنكية", "تبرع خيري"],
}

_CATEGORY_AMOUNT_RANGE = {
    "مطاعم": (25, 180),
    "تسوق": (60, 950),
    "مواصلات": (20, 250),
    "فواتير": (150, 600),
    "ترفيه": (40, 300),
    "صحة": (50, 500),
    "تعليم": (80, 600),
    "أخرى": (30, 800),
}

# Static per-persona profile. Ahmed: flat income, stable moderate spending,
# 0 late payments -> should land clearly approved. Sara: swinging income,
# spiky/irregular spending, 1 late payment, higher fixed obligations ->
# should land blocked/conditional once a real loan payment is added to her
# already-high DTI.
_CUSTOMER_PROFILES = {
    "ahmed": {
        "name": "أحمد السالم",
        "income_history": [15700.0, 15700.0, 15900.0],
        "monthly_obligations": 3280.0,  # car loan 1,850 + credit cards 650 + bills 780
        "late_payments_24m": 0,
        "monthly_spend_targets": [10200.0, 10700.0, 10750.0],
        "category_weights": {
            "مطاعم": 0.22, "تسوق": 0.18, "مواصلات": 0.14, "فواتير": 0.16,
            "ترفيه": 0.10, "صحة": 0.08, "تعليم": 0.06, "أخرى": 0.06,
        },
        "monthly_txn_counts": [110, 118, 108],
        "goals": [
            {"name": "تويوتا كامري", "target": 123000, "saved": 52000, "deadline": "2028-03"},
            {"name": "شقة تمليك", "target": 585000, "saved": 70200, "deadline": "2031-06"},
        ],
        "seed": 1001,
    },
    "sara": {
        "name": "سارة القحطاني",
        "income_history": [12400.0, 9800.0, 13100.0],
        "monthly_obligations": 4220.0,  # personal loan 2,400 + credit cards 1,150 + bills 670
        "late_payments_24m": 1,
        "monthly_spend_targets": [7600.0, 12400.0, 9400.0],
        "category_weights": {
            "مطاعم": 0.28, "تسوق": 0.26, "مواصلات": 0.10, "فواتير": 0.12,
            "ترفيه": 0.12, "صحة": 0.05, "تعليم": 0.02, "أخرى": 0.05,
        },
        "monthly_txn_counts": [95, 150, 118],
        "goals": [
            {"name": "سيارة هيونداي", "target": 85000, "saved": 29750, "deadline": "2027-02"},
            {"name": "مقدم شقة", "target": 150000, "saved": 13500, "deadline": "2032-10"},
        ],
        "seed": 2002,
    },
}


def _generate_month_transactions(rng, category_weights, count, target_total):
    categories = list(category_weights.keys())
    weights = list(category_weights.values())
    rows = []
    for _ in range(count):
        cat = rng.choices(categories, weights=weights, k=1)[0]
        lo, hi = _CATEGORY_AMOUNT_RANGE[cat]
        rows.append({
            "day": rng.randint(1, 28),
            "category": cat,
            "merchant": rng.choice(_MERCHANTS[cat]),
            "amount": round(rng.uniform(lo, hi), 2),
        })
    # Individual amounts are randomly drawn per category range; scale the
    # whole month to the target so the demo's DTI/savings-rate narrative is
    # controlled while every line item is still a real generated row.
    raw_total = sum(r["amount"] for r in rows)
    scale = (target_total / raw_total) if raw_total > 0 else 1.0
    for r in rows:
        r["amount"] = round(r["amount"] * scale, 2)
    return rows


def _build_transaction_history() -> dict:
    history = {}
    for customer_id, profile in _CUSTOMER_PROFILES.items():
        rng = _random.Random(profile["seed"])  # fixed seed -> identical every run
        months = []
        for i in range(3):
            months.append(_generate_month_transactions(
                rng,
                profile["category_weights"],
                profile["monthly_txn_counts"][i],
                profile["monthly_spend_targets"][i],
            ))
        history[customer_id] = months
    return history


# Built once at import time. Fixed seeds above make this byte-identical on
# every process start / redeploy — no regeneration, no drift.
_TRANSACTION_HISTORY = _build_transaction_history()


def get_customer_metrics(customer_id: str) -> dict | None:
    """Compute UC1/UC3/UC4's grounding inputs from the synthetic transaction
    history above. Nothing here is LLM-estimated. Returns None for unknown
    customer_ids so callers can fall back to normal (non-grounded) behavior.
    """
    key = (customer_id or "").strip().lower()
    profile = _CUSTOMER_PROFILES.get(key)
    if not profile:
        return None

    months = _TRANSACTION_HISTORY[key]
    monthly_totals = [round(sum(t["amount"] for t in month), 2) for month in months]
    avg_monthly_spend = round(sum(monthly_totals) / len(monthly_totals), 2)

    incomes = profile["income_history"]
    avg_income = round(sum(incomes) / len(incomes), 2)

    obligations = profile["monthly_obligations"]
    monthly_surplus = round(avg_income - obligations - avg_monthly_spend, 2)
    savings_rate = round(monthly_surplus / avg_income, 4) if avg_income > 0 else 0.0

    # Income stability: 1 minus the coefficient of variation (stdev/mean) of
    # the 3 tracked monthly income deposits, scaled by 3 so a freelance-level
    # swing (~10-15% CV) reads as meaningfully less stable than a near-flat
    # salary (<1% CV); clamped to [0, 1]. Documented here since it's a design
    # choice, not a "magic number": there's no universal standard for this
    # scaling, this is a reasonable, deterministic mapping for demo purposes.
    variance = sum((x - avg_income) ** 2 for x in incomes) / len(incomes)
    stdev = variance ** 0.5
    cv = (stdev / avg_income) if avg_income > 0 else 1.0
    income_stability = max(0.0, min(1.0, round(1 - cv * 3, 4)))

    dti_ratio = round(obligations / avg_income, 4) if avg_income > 0 else 0.0

    # Commitment score: 100 minus 15 points per late payment in the last 24
    # months, floored at 0 (0 late -> 100, 1 -> 85, 2 -> 70, ...). Simple,
    # documented, linear penalty — not itself a tool formula (those are
    # untouched), just how this layer turns a raw count into the 0-100
    # input calculate_dna_score expects.
    late_payments = profile["late_payments_24m"]
    commitment_score = max(0, 100 - late_payments * 15)

    return {
        "customer_id": key,
        "name": profile["name"],
        "monthly_income": avg_income,
        "income_history": incomes,
        "total_obligations": obligations,
        "avg_monthly_spend": avg_monthly_spend,
        "monthly_spend_by_month": monthly_totals,
        "monthly_surplus": monthly_surplus,
        "savings_rate": savings_rate,
        "income_stability": income_stability,
        "dti_ratio": dti_ratio,
        "commitment_score": commitment_score,
        "late_payments_24m": late_payments,
        "goals": profile["goals"],
    }


_DEMO_CUSTOMER_PATTERN = _re.compile(r"\b(ahmed|sara)\b", _re.IGNORECASE)


def _detect_demo_customer(text: str | None) -> str | None:
    """Case-insensitive customer_id match against the two demo personas.
    Returns None for anything else (live onboarding conversation, other
    customers) so that path is left completely untouched."""
    if not isinstance(text, str):
        return None
    m = _DEMO_CUSTOMER_PATTERN.search(text)
    return m.group(1).lower() if m else None


def _inject_computed_metrics(context, prefix: str) -> None:
    """Prepend `prefix` to the last user message's text content, in place.

    Must target context.messages.raw, not context.messages itself: cycls'
    web server wraps the incoming request in a `Messages` list (see
    cycls/agent/web/server.py) whose *transformed* elements are what
    _last_user_text reads, but the LLM harness (cycls/agent/harness/main.py
    `_run()`) builds the turn actually sent to the model from
    `context.messages.raw[-1]` — the untouched original request dicts.
    Mutating the transformed list has no effect on what the model receives;
    confirmed by a live test where the injected block was silently dropped
    until this was pointed at `.raw` instead.
    """
    targets = getattr(context.messages, "raw", None)
    if targets is None:
        targets = context.messages
    for msg in reversed(targets):
        is_dict = isinstance(msg, dict)
        role = msg.get("role") if is_dict else getattr(msg, "role", None)
        if role != "user":
            continue
        content = msg.get("content") if is_dict else getattr(msg, "content", None)
        if isinstance(content, str):
            new_content = prefix + content
        elif isinstance(content, list) and content:
            new_content = list(content)
            first = dict(new_content[0]) if isinstance(new_content[0], dict) else {"type": "text", "text": ""}
            first["text"] = prefix + (first.get("text") or "")
            new_content[0] = first
        else:
            new_content = prefix
        if is_dict:
            msg["content"] = new_content
        else:
            setattr(msg, "content", new_content)
        return


# ─── UC6 segmentation layer ───
# Same "ground the LLM's input in real computed data" principle as UC1/3/4
# above, applied to segmented-offer generation: financing_type/need are
# derived from the customer's own stated goals (not guessed), and
# eligibility_tier is derived from the real DNA score (via
# _calculate_dna_score_core), not invented.

_REAL_ESTATE_KEYWORDS = ("شقة", "منزل", "عقار", "فيلا", "بيت", "تمليك", "سكن")
_AUTO_KEYWORDS = ("سيارة", "كامري", "هيونداي", "مركبة")


def _primary_goal(metrics: dict) -> dict | None:
    """The goal driving financing need: the one with the largest remaining
    (target - saved) amount. Documented choice — "largest/most urgent" is
    ambiguous in the abstract, so this picks the goal that would require the
    most financing to close, which is the one most likely to prompt an
    actual loan offer."""
    goals = metrics.get("goals") or []
    if not goals:
        return None
    return max(goals, key=lambda g: max(0, g.get("target", 0) - g.get("saved", 0)))


def classify_financing_type(customer_id: str) -> str | None:
    """"شخصي" / "عقاري" / "استهلاكي", based on the customer's primary goal
    (see _primary_goal). Keyword-matched against the goal's Arabic name —
    real-estate goals -> عقاري, vehicle goals -> استهلاكي, everything else
    (education, travel, general savings, ...) -> شخصي."""
    metrics = get_customer_metrics(customer_id)
    if not metrics:
        return None
    goal = _primary_goal(metrics)
    if not goal:
        return "شخصي"
    name = goal.get("name", "")
    if any(kw in name for kw in _REAL_ESTATE_KEYWORDS):
        return "عقاري"
    if any(kw in name for kw in _AUTO_KEYWORDS):
        return "استهلاكي"
    return "شخصي"


def infer_need_from_goals(customer_id: str) -> str | None:
    """Short Arabic phrase describing the likely financing need, built from
    the same primary goal used by classify_financing_type — never invented,
    always traceable back to a real stated goal."""
    metrics = get_customer_metrics(customer_id)
    if not metrics:
        return None
    goal = _primary_goal(metrics)
    if not goal:
        return "تمويل شخصي عام"
    name = goal.get("name", "")
    financing_type = classify_financing_type(customer_id)
    if financing_type == "عقاري":
        return f"تمويل عقاري لتحقيق هدف: {name}"
    if financing_type == "استهلاكي":
        return f"تمويل شراء مركبة لتحقيق هدف: {name}"
    return f"تمويل شخصي لتحقيق هدف: {name}"


def get_customer_segment(customer_id: str) -> dict | None:
    """Combines classify_financing_type + eligibility_tier (derived from the
    real DNA score) + infer_need_from_goals into one object for UC6. Returns
    None for unknown customer_ids."""
    metrics = get_customer_metrics(customer_id)
    if not metrics:
        return None
    dna = _calculate_dna_score_core(
        metrics["savings_rate"], metrics["income_stability"],
        metrics["dti_ratio"], metrics["commitment_score"],
    )
    dna_score = dna["dna_score"]
    # Thresholds chosen so each demo persona lands in a distinct tier:
    # Ahmed (dna_score ~68) -> مؤهل فورًا, Sara (dna_score ~43) -> غير مؤهل.
    if dna_score >= 65:
        eligibility_tier = "مؤهل فورًا"
    elif dna_score >= 45:
        eligibility_tier = "يحتاج مراجعة"
    else:
        eligibility_tier = "غير مؤهل"

    return {
        "customer_id": metrics["customer_id"],
        "name": metrics["name"],
        "dna_score": dna_score,
        "risk_level": dna["risk_level"],
        "financing_type": classify_financing_type(customer_id),
        "eligibility_tier": eligibility_tier,
        "inferred_need": infer_need_from_goals(customer_id),
    }


# ─── Branded logo — per-chat "shown once" tracker ───
# In-memory only: resets on redeploy/restart and won't be shared across
# multiple server instances if this ever scales beyond a single process.
# Acceptable for a single-demo deployment; not a durable solution.
_logo_shown_chats = set()


# ─── Fallback cache (demo reliability) ───
# One known-good response per (customer_id, uc) pair, captured verbatim
# from a real successful call against the live grounded pipeline above
# (see verification transcript). Used only as a safety net when the live
# LLM call times out or errors for ahmed/sara — never for real user
# conversations, which always hit the live model and error normally on
# failure, exactly as before this change.
_FALLBACK_TIMEOUT_SECONDS = 18

FALLBACK_RESPONSES = {
    ("ahmed", "UC1"): {
        "dna_score": 68, "commitment_score": 100, "risk_level": "منخفض", "risk_score": 12,
        "personality": {
            "label": "مدخر ملتزم",
            "description": "لديك التزام قوي بالتزاماتك المالية وتوفير جزء من دخلك، لكن لديك فرص لتحسين معدل الادخار.",
        },
        "indicators": {"saving": 3.7, "commitment": 20, "investment": 0, "risk": 12, "spending": 0, "impulse": 0},
        "strengths": ["التزام قوي بالدفع في الوقت المحدد", "استقرار دخل مرتفع"],
        "weaknesses": ["معدل ادخار منخفض نسبيًا", "أهداف مالية كبيرة تتجاوز القدرة الحالية على التوفير"],
        "recommendations": [
            {"rank": 1, "action": "زيادة معدل الادخار الشهري", "impact": "تحسين القدرة على تحقيق الأهداف المالية"},
            {"rank": 2, "action": "مراجعة المواعيد النهائية للأهداف", "impact": "جعلها أكثر واقعية وفقًا للدخل والمصاريف الحالية"},
        ],
        "goals_analysis": [
            {"goal": "تويوتا كامري", "target": 123000, "monthly_required": 3550, "feasibility": "صعب", "completion_date": "2032-07"},
            {"goal": "شقة تمليك", "target": 585000, "monthly_required": 8725, "feasibility": "صعب", "completion_date": "2070-03"},
        ],
        "daily_insight": "ركز على زيادة مدخراتك الشهرية لتحقيق أهدافك بشكل أسرع.",
        "morning_briefing": "صباح الخير أحمد، لديك التزام قوي بالتزاماتك المالية، لكن معدل ادخارك الحالي قد لا يكون كافياً لتحقيق أهدافك في الوقت المحدد. فكر في زيادة مدخراتك أو تعديل أهدافك.",
    },
    ("sara", "UC1"): {
        "dna_score": 43, "commitment_score": 85, "risk_level": "متوسط", "risk_score": 37,
        "personality": {
            "label": "في دائرة الخطر",
            "description": "الالتزام المالي موجود لكن المعدل السلبي للادخار وعدم الاستقرار في الدخل يعرض الأهداف للخطر.",
        },
        "indicators": {"saving": -5.7, "commitment": 17, "investment": 0, "risk": 37, "spending": 0, "impulse": 0},
        "strengths": ["الالتزام بالسداد"],
        "weaknesses": ["معدل ادخار سلبي", "عدم استقرار الدخل"],
        "recommendations": [
            {"rank": 1, "action": "زيادة الدخل أو تقليل المصروفات لتحقيق معدل ادخار إيجابي", "impact": "تحسين الفرص لتحقيق الأهداف المالية"},
            {"rank": 2, "action": "تأجيل شراء السيارة حتى تحقيق استقرار مالي أفضل", "impact": "تجنب زيادة الديون وتحسين القدرة على الادخار"},
        ],
        "goals_analysis": [
            {"goal": "سيارة هيونداي", "target": 85000, "monthly_required": 7893, "feasibility": "صعب", "completion_date": "غير محدد"},
            {"goal": "مقدم شقة", "target": 150000, "monthly_required": 1820, "feasibility": "صعب", "completion_date": "غير محدد"},
        ],
        "daily_insight": "تحتاج إلى زيادة دخلك أو تقليل مصروفاتك لتحقيق أهدافك المالية.",
        "morning_briefing": "وضعك المالي حاليًا يتطلب تحسينًا في معدل الادخار واستقرار الدخل لتجنب المزيد من الديون وتحقيق أهدافك.",
    },
    ("ahmed", "UC3"): {
        "loan_type": "سيارة", "current_approval_probability": 90, "approval_status": "مرتفع",
        "blocking_factors": [],
        "improvement_suggestions": [
            "خفّض التزاماتك الشهرية بـ 788 ريال خلال 2-3 أشهر لرفع نسبة الموافقة إلى 95%",
        ],
        "best_product": {
            "name": "قرض السيارة", "max_amount": 60000, "estimated_monthly": 1200,
            "reason": "نسبة الموافقة مرتفعة مع نسبة دين إلى دخل آمنة",
        },
        "dti_analysis": {"current_dti": 20.8, "dti_after_loan": 28.4, "bank_limit": 45, "headroom": 16.6},
    },
    ("sara", "UC3"): {
        "loan_type": "شخصي - إعادة تمويل", "current_approval_probability": 0, "approval_status": "غير مؤهل",
        "blocking_factors": [
            "نسبة الدين إلى الدخل بعد القرض (52%) تتجاوز الحد الأقصى للبنك (45%)",
            "استقرار الدخل (64%) أقل من الحد المطلوب (80%)",
            "وجود 1 تأخير في السداد خلال 24 شهرًا",
        ],
        "improvement_suggestions": [
            "خفّض التزاماتك الشهرية بـ 588 ريال خلال 2-3 أشهر لخفض نسبة الدين إلى 47%",
            "عزز استقرار مصدر الدخل لزيادة احتمالية الموافقة بـ 25 نقطة خلال 3-6 أشهر",
        ],
        "best_product": {
            "name": "غير متاح", "max_amount": 0, "estimated_monthly": 0,
            "reason": "عدم التأهل الحالي للقروض",
        },
        "dti_analysis": {"current_dti": 35.9, "dti_after_loan": 52.0, "bank_limit": 45, "headroom": 0},
    },
    ("ahmed", "UC4"): {
        "summary": "أحمد السالم لديه ملف مالي قوي مع دخل شهري مستقر وقدرة على الادخار بنسبة 12.28%. لديه التزامات شهرية منخفضة نسبيًا ونسبة دين إلى الدخل تبلغ 20.8%، مما يجعله مؤهلاً للعديد من المنتجات التمويلية.",
        "badges": [{"text": "دخل مستقر", "tone": "ok"}, {"text": "سجل دفع ممتاز", "tone": "ok"}],
        "eligibility": {
            "car_loan": {"status": "مؤهل", "max_amount": 180000, "note": "نسبة الدين إلى الدخل بعد القرض ستكون 36%", "tone": "ok"},
            "personal_loan": {"status": "مؤهل", "max_amount": 120000, "note": "نسبة الدين إلى الدخل بعد القرض ستكون 28.4%", "tone": "ok"},
            "mortgage": {"status": "غير مؤهل", "max_amount": 0, "note": "نسبة الدين إلى الدخل بعد القرض ستتجاوز الحد الأقصى للبنك (45%)", "tone": "danger"},
        },
        "recommendations": [
            {"title": "قرض سيارة", "reason": "مؤهل بالكامل مع دفعات شهرية مريحة", "priority": "highest"},
            {"title": "قرض شخصي", "reason": "مؤهل بحد أقصى 120,000 ريال", "priority": "high"},
            {"title": "حساب توفير", "reason": "خيار منخفض المخاطر لبناء احتياطي مالي إضافي", "priority": "medium"},
            {"title": "استشارة استثمارية", "reason": "لاستكشاف خيارات استثمارية تناسب وضعك المالي الحالي", "priority": "medium"},
        ],
        "investment_potential": {"monthly_investable": 1936.66, "note": "يمكن استثمار هذا الفائض لتحقيق أهداف مالية طويلة المدى"},
        "risk_flags": [],
        "confidence": "high",
    },
    ("sara", "UC4"): {
        "summary": "الوضع المالي لسارة القحطاني يشير إلى تحديات في الاستقرار المالي مع معدل ادخار سلبي واستقرار دخلي منخفض. هناك حاجة لتحسين العادات المالية لتعزيز الفرص التمويلية.",
        "badges": [{"text": "معدل ادخار منخفض", "tone": "danger"}, {"text": "استقرار دخلي متذبذب", "tone": "warn"}],
        "eligibility": {
            "car_loan": {"status": "غير مؤهل", "max_amount": 0, "note": "معدل الادخار السلبي يحد من القدرة على السداد", "tone": "danger"},
            "personal_loan": {"status": "غير مؤهل", "max_amount": 0, "note": "انخفاض استقرار الدخل يقلل من فرص الموافقة", "tone": "danger"},
            "mortgage": {"status": "غير مؤهل", "max_amount": 0, "note": "عدم كفاية المدخرات لمقدم الشقة المطلوب", "tone": "danger"},
        },
        "recommendations": [
            {"title": "برنامج توفير مخصص", "reason": "لتحسين معدل الادخار وزيادة الفرص التمويلية", "priority": "highest"},
            {"title": "مراجعة الالتزامات الشهرية", "reason": "لتقليل نسبة الدخل إلى الديون وتعزيز الاستقرار المالي", "priority": "high"},
            {"title": "حساب توفير", "reason": "خيار منخفض المخاطر لبناء احتياطي مالي إضافي", "priority": "medium"},
            {"title": "استشارة استثمارية", "reason": "لاستكشاف خيارات استثمارية تناسب وضعك المالي الحالي", "priority": "medium"},
        ],
        "investment_potential": {"monthly_investable": 0, "note": "لا يوجد فائض شهري متاح للاستثمار حالياً"},
        "risk_flags": ["معدل ادخار سلبي", "استقرار دخلي منخفض", "وجود تأخير في السداد"],
        "confidence": "medium",
    },
    ("ahmed", "UC6"): {
        "customer_id": "ahmed",
        "offer_message": "أهلاً بك أحمد السالم! نرى أنك مؤهل فورًا للحصول على تمويل عقاري لتحقيق هدفك في امتلاك شقة. نقدم لك حلول تمويلية متعددة تناسب احتياجاتك.",
    },
    ("sara", "UC6"): {
        "customer_id": "sara",
        "offer_message": "أهلاً بك سارة القحطاني! نأسف لإعلامك بأنك غير مؤهلة حاليًا للحصول على تمويل عقاري لهدفك في امتلاك شقة. ننصحك بمراجعة ملفك المالي لتحسين فرص التأهيل.",
    },
}


def _uc_label(text: str) -> str | None:
    for label in ("UC1", "UC2", "UC3", "UC4", "UC5", "UC6"):
        if text.strip().startswith(f"[{label}]"):
            return label
    return None


# UC4's dashboard UI has exactly 4 fixed recommendation card slots. A
# prompt-level "return exactly 4" instruction was tested live and did not
# work — deepseek-chat returned the same 2 recommendations across 6/6
# trials for both demo personas, regardless of wording. Padding/truncating
# in code instead, applied uniformly to every UC4 call (not just the demo
# personas) since this is a UI-contract requirement, not a grounding one.
_UC4_RECOMMENDATIONS_COUNT = 4
_UC4_FILLER_RECOMMENDATIONS = [
    {"title": "حساب توفير", "reason": "خيار منخفض المخاطر لبناء احتياطي مالي إضافي", "priority": "medium"},
    {"title": "استشارة استثمارية", "reason": "لاستكشاف خيارات استثمارية تناسب وضعك المالي الحالي", "priority": "medium"},
    {"title": "خطة ادخار لهدف محدد", "reason": "لتنظيم الادخار نحو أحد أهدافك المالية القائمة", "priority": "medium"},
    {"title": "مراجعة مالية شاملة", "reason": "لتقييم كامل لوضعك المالي وتحديد أفضل الفرص المتاحة", "priority": "medium"},
]


def _pad_uc4_recommendations(data: dict) -> dict:
    """Pad `data['recommendations']` up to exactly 4 items with generic
    fillers (same {title,reason,priority} shape as genuine ones, so nothing
    looks structurally different — only the generic content signals a
    filler), or truncate down to 4 if the model returned more."""
    recs = data.get("recommendations")
    recs = list(recs) if isinstance(recs, list) else []
    recs = recs[:_UC4_RECOMMENDATIONS_COUNT]
    if len(recs) < _UC4_RECOMMENDATIONS_COUNT:
        existing_titles = {r.get("title") for r in recs if isinstance(r, dict)}
        for filler in _UC4_FILLER_RECOMMENDATIONS:
            if len(recs) >= _UC4_RECOMMENDATIONS_COUNT:
                break
            if filler["title"] in existing_titles:
                continue
            recs.append(filler)
    data["recommendations"] = recs[:_UC4_RECOMMENDATIONS_COUNT]
    return data


async def _buffer_llm_response(system: str, context) -> tuple[str, list]:
    """Run the LLM to completion, returning (full_text, other_ui_events).
    Split out so callers can wrap the whole thing in asyncio.wait_for for a
    hard deadline — a per-event yield inside the loop can't be time-bounded
    piecemeal without collecting into this first."""
    full_text = ""
    ui_events = []
    async for ev in _llm_base.system(system).run(context=context):
        if isinstance(ev, str):
            full_text += ev
        else:
            ui_events.append(ev)
    return full_text, ui_events


# ----------------------------------------------------------------------
# UC5 — spending alert SMS
# ----------------------------------------------------------------------
# Sent server-side only. Credentials come from the environment (.env,
# gitignored, copied into the image above) so they never appear in the
# browser-shipped FinDNA App.dc.html or in git history.

def _last_user_text(context) -> str | None:
    """Best-effort plain text of the last user message. `content` is either
    a bare string (plain OpenAI-style callers, e.g. the FinDNA frontend) or
    a list of Anthropic-style content blocks — UC-prefix detection only
    needs the leading text either way."""
    for msg in reversed(context.messages):
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
        if role != "user":
            continue
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for block in content:
                text = block.get("text") if isinstance(block, dict) else None
                if text:
                    return text
        return None
    return None


def _send_sms(body: str) -> tuple[bool, str | None]:
    """POST to the Twilio Messages API. Returns (sent, error)."""
    sid = os.environ.get("TWILIO_SID")
    token = os.environ.get("TWILIO_TOKEN")
    from_number = os.environ.get("TWILIO_FROM")
    to_number = os.environ.get("TWILIO_TO")
    if not all([sid, token, from_number, to_number]):
        return False, "Twilio env vars not configured"
    if to_number.strip().upper().endswith("XXXXXXXXX"):
        return False, "TWILIO_TO is still a placeholder — set a real number in .env"
    try:
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            auth=(sid, token),
            data={"To": f"whatsapp:{to_number}", "From": "whatsapp:+14155238886", "Body": body[:1600]},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return True, None
        return False, f"Twilio {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, str(e)


# ----------------------------------------------------------------------
# Agent
# ----------------------------------------------------------------------
@cycls.agent(image=image, web=web, name="findna-agent")
async def findna(context):
    if not context.messages:
        return

    last_user_text = _last_user_text(context)

    # [SEND_OFFER]: lightweight WhatsApp passthrough for offer text the
    # dashboard has already composed client-side (name/product/amount are
    # already on screen by the time these buttons are clickable) — nothing
    # left to generate, so this skips the LLM round-trip entirely and just
    # reuses the same _send_sms/Twilio pipeline UC5 already sends through.
    if isinstance(last_user_text, str) and last_user_text.strip().startswith("[SEND_OFFER]"):
        body = last_user_text.strip()[len("[SEND_OFFER]"):].strip()
        try:
            payload = json.loads(body)
            message = str(payload.get("message") or "").strip()
        except Exception:
            message = ""
        if not message:
            yield cycls.to_ui(json.dumps({"sent": False, "error": "no message provided"}, ensure_ascii=False))
            return
        sent, error = _send_sms(message)
        yield cycls.to_ui(json.dumps({"sent": sent, "error": error}, ensure_ascii=False))
        return

    system = build_prompt(gregorian_date=_riyadh_date())

    uc_label = _uc_label(last_user_text) if isinstance(last_user_text, str) else None
    is_uc5 = uc_label == "UC5"
    is_uc6 = uc_label == "UC6"

    # Ground UC1/UC3/UC4 in real computed metrics for the two demo personas
    # only — any other customer_id (i.e. the live onboarding/conversational
    # flow) falls straight through to the untouched LLM-estimated path.
    demo_customer_id = None
    if uc_label in ("UC1", "UC3", "UC4"):
        demo_customer_id = _detect_demo_customer(last_user_text)
        if demo_customer_id:
            metrics = get_customer_metrics(demo_customer_id)
            if metrics:
                prefix = (
                    "[COMPUTED METRICS — use these exact values, do not estimate or override]: "
                    + json.dumps(metrics, ensure_ascii=False)
                    + "\n\n"
                )
                _inject_computed_metrics(context, prefix)

    # UC6: build a segment object per requested customer_id server-side and
    # inject them the same way, before the model ever sees the message.
    uc6_customer_ids = []
    if is_uc6:
        body = last_user_text.strip()[len("[UC6]"):].strip()
        try:
            parsed_ids = json.loads(body)
            if isinstance(parsed_ids, list):
                uc6_customer_ids = [str(cid).strip().lower() for cid in parsed_ids]
        except Exception:
            uc6_customer_ids = []
        segments = [seg for seg in (get_customer_segment(cid) for cid in uc6_customer_ids) if seg]
        if segments:
            prefix = (
                "[COMPUTED METRICS — use these exact values, do not estimate or override]: "
                + json.dumps(segments, ensure_ascii=False)
                + "\n\n"
            )
            _inject_computed_metrics(context, prefix)

    # Demo-persona fallback safety net (UC1/UC3/UC4): only when the request
    # is grounded to ahmed/sara AND a cached response exists for that exact
    # (customer_id, uc) pair. Anything else (real conversation, non-demo
    # customer, UC2) skips this block entirely and falls through to the
    # untouched live-streaming path below — no timeout, no fallback, errors
    # normally exactly as before this change.
    single_fallback_key = (
        (demo_customer_id, uc_label)
        if demo_customer_id and uc_label in ("UC1", "UC3", "UC4")
        else None
    )
    if single_fallback_key and single_fallback_key in FALLBACK_RESPONSES:
        try:
            full_text, ui_events = await asyncio.wait_for(
                _buffer_llm_response(system, context), timeout=_FALLBACK_TIMEOUT_SECONDS
            )
            for ev in ui_events:
                yield cycls.to_ui(ev)
            if uc_label == "UC4":
                try:
                    data = _pad_uc4_recommendations(json.loads(full_text.strip()))
                    full_text = json.dumps(data, ensure_ascii=False)
                except Exception:
                    pass  # leave full_text as-is; outer except only covers the buffering step
            yield cycls.to_ui(full_text)
        except Exception as e:
            print(f"[FinDNA] fallback used for {single_fallback_key}: {e}")
            yield cycls.to_ui(json.dumps(FALLBACK_RESPONSES[single_fallback_key], ensure_ascii=False))
        return

    if is_uc6:
        # Same safety net for UC6, but only when EVERY requested customer_id
        # is a known demo persona — a mixed or unknown request just runs
        # live with no timeout and no fallback, same "error normally" rule.
        uc6_all_demo = bool(uc6_customer_ids) and all(
            (cid, "UC6") in FALLBACK_RESPONSES for cid in uc6_customer_ids
        )
        try:
            if uc6_all_demo:
                full_text, ui_events = await asyncio.wait_for(
                    _buffer_llm_response(system, context), timeout=_FALLBACK_TIMEOUT_SECONDS
                )
            else:
                full_text, ui_events = await _buffer_llm_response(system, context)
            for ev in ui_events:
                yield cycls.to_ui(ev)
        except Exception as e:
            if not uc6_all_demo:
                raise
            print(f"[FinDNA] fallback used for UC6 {uc6_customer_ids}: {e}")
            fallback_array = [FALLBACK_RESPONSES[(cid, "UC6")] for cid in uc6_customer_ids]
            yield cycls.to_ui(json.dumps(fallback_array, ensure_ascii=False))
            return

        try:
            parsed = json.loads(full_text.strip())
            out_text = json.dumps(parsed, ensure_ascii=False)
        except Exception:
            out_text = full_text.strip()
            print("[FinDNA] UC6 response failed JSON-array validation — passing raw text through")
        yield cycls.to_ui(out_text)
        return

    if uc_label == "UC4":
        # Every UC4 call, demo or not, needs exactly 4 recommendations — the
        # dashboard UI has 4 fixed card slots regardless of which customer
        # this is. No timeout/fallback here (that's the demo-only branch
        # above); just buffer so the JSON can be padded before it's sent.
        full_text, ui_events = await _buffer_llm_response(system, context)
        for ev in ui_events:
            yield cycls.to_ui(ev)
        try:
            data = _pad_uc4_recommendations(json.loads(full_text.strip()))
            out_text = json.dumps(data, ensure_ascii=False)
        except Exception:
            out_text = full_text.strip()
            print("[FinDNA] UC4 response failed JSON validation — passing raw text through, recommendations not padded")
        yield cycls.to_ui(out_text)
        return

    # Branded header image — plain conversational path only. uc_label is
    # None exactly when the message carries no [UCx] prefix at all, which
    # mechanically excludes every UC1-6 path (including real, non-demo
    # UC1/UC2/UC3 calls that fall through to this same branch below) and
    # SEND_OFFER (already returned above). Shown once per chat_id (tracked
    # in _logo_shown_chats above) rather than per-turn — chat_id is a
    # stable per-conversation identifier here (confirmed against the query
    # param it's derived from), so this is a real "first turn of this
    # conversation" check, not the len(context.messages) approximation
    # used previously.
    if uc_label is None and context.chat_id not in _logo_shown_chats:
        _logo_shown_chats.add(context.chat_id)
        yield cycls.to_ui({
            "type": "image",
            "src": "/public/findna-logo.jpg",
            "alt": "FinDNA",
        })

    if not is_uc5:
        async for ev in _llm_base.system(system).run(context=context):
            yield cycls.to_ui(ev)
        return

    # UC5: unchanged — buffer the model's JSON, send the SMS server-side,
    # yield ONE augmented JSON chunk. No timeout/fallback wrapper here;
    # Twilio/WhatsApp send logic is out of scope for this pass.
    full_text = ""
    async for ev in _llm_base.system(system).run(context=context):
        if isinstance(ev, str):
            full_text += ev
        else:
            yield cycls.to_ui(ev)

    try:
        data = json.loads(full_text.strip())
    except Exception:
        data = {"sms_message": full_text.strip()[:160] or "تنبيه: تجاوزت حد الإنفاق اليومي."}

    sms_text = data.get("sms_message") or "تنبيه: تجاوزت حد الإنفاق اليومي."
    sent, error = _send_sms(sms_text)
    data["sms_sent"] = sent
    if error:
        data["sms_error"] = error

    yield cycls.to_ui(json.dumps(data, ensure_ascii=False))


findna.deploy()

