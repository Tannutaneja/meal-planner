"""
Flatmate Meal Planner (v3)
- Groups with shared recipes, daily voting, AI + cookbook suggestions
- Light / dark mode safe (only native, theme-aware Streamlit components)
- Calendar to log past meals; history feeds tomorrow's suggestions
"""

import json
import os
import random
import re
import string
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

# ---------------------------------------------------------------------------
# Branding (mint leaf). Drop a logo.png next to app.py to use your own image.
# ---------------------------------------------------------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_FILE = os.path.join(APP_DIR, "logo.png")
HAS_LOGO_FILE = os.path.exists(LOGO_FILE)
LEAF = "🌿"
APP_NAME = "Meal Planner"

st.set_page_config(
    page_title=f"{APP_NAME}",
    page_icon=LOGO_FILE if HAS_LOGO_FILE else LEAF,
    layout="centered",
)
if HAS_LOGO_FILE:
    try:
        st.logo(LOGO_FILE)
    except Exception:
        pass

import firebase_admin  # noqa: E402
from firebase_admin import credentials, firestore  # noqa: E402


def secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


# Streamlit Cloud servers run on UTC. Use Indian time so "today" is correct.
TZ = ZoneInfo(secret("TIMEZONE", "Asia/Kolkata"))
# Groq retired llama-3.1-8b-instant on 16 Aug 2026. Override via secrets if this one is retired too.
GROQ_MODEL = secret("GROQ_MODEL", "openai/gpt-oss-20b")

MAX_KITCHEN = 10       # max "From your kitchen" cards per meal
EXCLUDE_DAYS = 7       # don't suggest anything made in the last 7 days
HISTORY_DAYS = 14      # how much history the AI sees
CALENDAR_DAYS_BACK = 90
QUICK_MAX = 30         # minutes; above this a dish counts as "elaborate"
NEW_CARDS = 4          # "Try something new" cards per meal (cookbook + AI mix)
MODE_LABEL = {"quick": "⚡ Quick (up to 30 min)", "elaborate": "🍲 Elaborate (30+ min)"}
_TIME_RE = re.compile(r"(\d+)(?:\s*(?:-|to)\s*(\d+))?\s*(hours?|hrs?|hr|h\b|minutes?|mins?|min|m\b)", re.I)


def minutes_of(pt):
    """'20 min' -> 20, '~1 hr 15 min' -> 75, '' -> None."""
    found, total = False, 0
    for a, b, unit in _TIME_RE.findall(pt or ""):
        v = int(b or a)
        total += v * 60 if unit.lower().startswith("h") else v
        found = True
    return total if found else None


def time_class(pt):
    m = minutes_of(pt)
    if m is None:
        return "unknown"
    return "quick" if m <= QUICK_MAX else "elaborate"


def order_by_mode(items, mode, min_keep=5):
    """Matching dishes first, then unknown time. Mismatches only if the list would be too short."""
    match = [c for c in items if time_class(c.get("prep_time")) == mode]
    unknown = [c for c in items if time_class(c.get("prep_time")) == "unknown"]
    other = [c for c in items if time_class(c.get("prep_time")) not in (mode, "unknown")]
    out = match + unknown
    if len(out) < min_keep:
        out += other
    return out


def time_pref(group):
    tp = group.get("time_pref") or {}
    return {"weekday": tp.get("weekday", "quick"), "weekend": tp.get("weekend", "elaborate")}


def default_mode(group, d):
    return time_pref(group)["weekend" if d.weekday() >= 5 else "weekday"]


GUIDE_MD = """
**1. Pick today's style.** The toggle at the top switches between ⚡ quick dishes (up to 30 min) and 🍲 elaborate ones. It starts on your group's default for weekdays or weekends, and anyone can flip it.

**2. Vote.** Each meal shows up to 10 dishes **from your kitchen** (anything you made in the last 7 days is skipped) plus **4 new ideas**: picks from your cookbooks 📖 and fresh AI ideas ✨. Tap **Vote**; everyone sees votes live and the 🏆 leader. You can change your vote anytime.

**3. Log what you actually cooked.** Open **📝 Log what you actually made** under each meal. This is what teaches the app your taste, so log even if it wasn't the winner.

**4. Add dishes.** Use **➕ Add an option to today's vote** under a meal, or **📝 Add a recipe** in the sidebar. New dishes appear on today's vote for everyone.

**5. Fill in past days.** The **📅 Calendar** (sidebar) lets you record meals from earlier days. More history means better suggestions.

**6. Invite flatmates.** Share the app link and your 6-letter group code.

Tip: 🔄 **Refresh suggestions** gives a new list for that meal but clears its votes.
"""


def now():
    return datetime.now(TZ)


def today():
    return now().date()


def dstr(d):
    return d.strftime("%Y-%m-%d")


def norm(name):
    return " ".join((name or "").strip().lower().split())


# ---------------------------------------------------------------------------
# Firebase
# ---------------------------------------------------------------------------
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        if "FIREBASE_JSON" in st.secrets:
            cred_dict = json.loads(st.secrets["FIREBASE_JSON"])
        else:
            cred_dict = dict(st.secrets["firebase"])
        firebase_admin.initialize_app(credentials.Certificate(cred_dict))
    return firestore.client()


db = init_firebase()


def group_ref(code):
    return db.collection("groups").document(code)


def plan_ref(code, ds):
    return group_ref(code).collection("daily_plans").document(ds)


def fp(*parts):
    """Safe Firestore field path (handles names with spaces etc.)."""
    return firestore.FieldPath(*parts).to_api_repr()


def get_group(code):
    snap = group_ref(code).get()
    return snap.to_dict() if snap.exists else None


def get_plan(code, ds):
    snap = plan_ref(code, ds).get()
    return snap.to_dict() if snap.exists else {}


def get_plans_range(code, start, end):
    """All daily plans from start to end (inclusive), in one round trip."""
    n = (end - start).days + 1
    if n <= 0:
        return {}
    refs = [plan_ref(code, dstr(start + timedelta(days=i))) for i in range(n)]
    out = {}
    for snap in db.get_all(refs):
        if snap.exists:
            out[snap.id] = snap.to_dict()
    return out


# ---------------------------------------------------------------------------
# Recipes
# ---------------------------------------------------------------------------
MASTER_RECIPES = {
    "Breakfast": {
        "veg": [
            {"name": "Poha", "ingredients": "flattened rice, onion, peanuts, curry leaves, turmeric, lemon", "prep_time": "15 min"},
            {"name": "Upma", "ingredients": "semolina, onion, mustard seeds, curry leaves, vegetables", "prep_time": "20 min"},
            {"name": "Aloo Paratha", "ingredients": "wheat flour, potato, green chili, coriander, butter", "prep_time": "30 min"},
            {"name": "Besan Cheela", "ingredients": "besan, onion, tomato, green chili, coriander", "prep_time": "15 min"},
            {"name": "Masala Dosa", "ingredients": "dosa batter, potato, onion, mustard seeds, chutney", "prep_time": "25 min"},
            {"name": "Idli Sambhar", "ingredients": "idli batter, toor dal, vegetables, tamarind, spices", "prep_time": "25 min"},
            {"name": "Maggi", "ingredients": "maggi noodles, vegetables, butter", "prep_time": "10 min"},
            {"name": "Chole Kulche", "ingredients": "chickpeas, kulcha, onion, spices", "prep_time": "35 min"},
            {"name": "Cornflakes + Milk", "ingredients": "cornflakes, milk, sugar/honey, banana", "prep_time": "2 min"},
            {"name": "Sabudana Khichdi", "ingredients": "tapioca pearls, peanuts, potato, cumin, lemon", "prep_time": "20 min"},
            {"name": "Pav Bhaji", "ingredients": "pav, mixed vegetables, butter, pav bhaji masala", "prep_time": "30 min"},
            {"name": "Moong Dal Cheela", "ingredients": "moong dal batter, onion, green chili, spices", "prep_time": "20 min"},
            {"name": "Sandwich (veg)", "ingredients": "bread, vegetables, cheese, chutney, butter", "prep_time": "10 min"},
            {"name": "Puri Sabzi", "ingredients": "wheat flour, potato, tomato, spices, oil", "prep_time": "35 min"},
            {"name": "Paratha + Curd", "ingredients": "wheat flour, ghee, curd, pickle", "prep_time": "20 min"},
        ],
        "eggetarian": [
            {"name": "Bread Omelette", "ingredients": "eggs, bread, onion, tomato, green chili, butter", "prep_time": "10 min"},
            {"name": "Anda Bhurji", "ingredients": "eggs, onion, tomato, green chili, butter, pav", "prep_time": "10 min"},
            {"name": "Egg Paratha", "ingredients": "wheat flour, eggs, onion, spices, butter", "prep_time": "25 min"},
            {"name": "Boiled Egg Toast", "ingredients": "eggs, bread, butter, pepper, salt", "prep_time": "10 min"},
            {"name": "French Toast", "ingredients": "bread, eggs, milk, sugar, cinnamon, butter", "prep_time": "15 min"},
            {"name": "Egg Sandwich", "ingredients": "bread, eggs, mayo, lettuce, cheese", "prep_time": "10 min"},
        ],
        "non-veg": [
            {"name": "Chicken Sandwich", "ingredients": "bread, chicken, mayo, lettuce, cheese", "prep_time": "15 min"},
            {"name": "Keema Paratha", "ingredients": "wheat flour, minced meat, onion, spices", "prep_time": "35 min"},
        ],
    },
    "Lunch": {
        "veg": [
            {"name": "Dal Chawal", "ingredients": "toor dal, rice, onion, tomato, garlic, cumin, ghee", "prep_time": "30 min"},
            {"name": "Rajma Chawal", "ingredients": "kidney beans, rice, onion, tomato, ginger, garlic, spices", "prep_time": "45 min"},
            {"name": "Chole Rice", "ingredients": "chickpeas, rice, onion, tomato, spices", "prep_time": "40 min"},
            {"name": "Kadhi Chawal", "ingredients": "besan, curd, rice, onion, mustard seeds, curry leaves", "prep_time": "35 min"},
            {"name": "Paneer Butter Masala + Roti", "ingredients": "paneer, tomato, butter, cream, cashews, spices, wheat flour", "prep_time": "40 min"},
            {"name": "Aloo Gobi + Roti", "ingredients": "potato, cauliflower, onion, tomato, spices, wheat flour", "prep_time": "35 min"},
            {"name": "Veg Biryani", "ingredients": "basmati rice, mixed vegetables, biryani masala, curd, saffron", "prep_time": "45 min"},
            {"name": "Aloo Matar + Rice", "ingredients": "potato, peas, onion, tomato, spices, rice", "prep_time": "30 min"},
            {"name": "Dal Fry + Jeera Rice", "ingredients": "toor dal, rice, cumin, onion, tomato, garlic, ghee", "prep_time": "30 min"},
            {"name": "Khichdi", "ingredients": "rice, moong dal, ghee, cumin, turmeric, vegetables", "prep_time": "25 min"},
            {"name": "Palak Paneer + Roti", "ingredients": "spinach, paneer, onion, garlic, cream, spices, wheat flour", "prep_time": "35 min"},
            {"name": "Mix Veg + Roti", "ingredients": "mixed vegetables, onion, tomato, spices, wheat flour", "prep_time": "30 min"},
            {"name": "Puri Sabzi", "ingredients": "wheat flour, potato, tomato, spices, oil", "prep_time": "35 min"},
        ],
        "eggetarian": [
            {"name": "Egg Curry + Rice", "ingredients": "eggs, onion, tomato, ginger garlic paste, spices, rice", "prep_time": "30 min"},
            {"name": "Egg Biryani", "ingredients": "eggs, basmati rice, biryani masala, curd, onion", "prep_time": "40 min"},
            {"name": "Egg Fried Rice", "ingredients": "rice, eggs, vegetables, soy sauce, vinegar", "prep_time": "20 min"},
        ],
        "non-veg": [
            {"name": "Chicken Curry + Rice", "ingredients": "chicken, rice, onion, tomato, ginger garlic, spices", "prep_time": "45 min"},
            {"name": "Chicken Biryani", "ingredients": "chicken, basmati rice, biryani masala, curd, onion, saffron", "prep_time": "60 min"},
            {"name": "Butter Chicken + Naan", "ingredients": "chicken, tomato, butter, cream, naan, spices", "prep_time": "45 min"},
            {"name": "Chicken Fried Rice", "ingredients": "chicken, rice, vegetables, soy sauce, vinegar", "prep_time": "25 min"},
            {"name": "Fish Curry + Rice", "ingredients": "fish, rice, coconut milk, onion, spices", "prep_time": "35 min"},
            {"name": "Keema Matar + Roti", "ingredients": "minced meat, peas, onion, tomato, spices, wheat flour", "prep_time": "40 min"},
        ],
    },
    "Dinner": {
        "veg": [
            {"name": "Dal + Roti", "ingredients": "toor dal, wheat flour, onion, tomato, garlic, ghee", "prep_time": "30 min"},
            {"name": "Paneer Tikka + Roti", "ingredients": "paneer, bell pepper, onion, curd, spices, wheat flour", "prep_time": "35 min"},
            {"name": "Aloo Paratha + Curd", "ingredients": "wheat flour, potato, green chili, curd, pickle", "prep_time": "30 min"},
            {"name": "Mix Veg + Roti", "ingredients": "mixed vegetables, onion, tomato, spices, wheat flour", "prep_time": "30 min"},
            {"name": "Khichdi + Papad", "ingredients": "rice, moong dal, ghee, cumin, papad", "prep_time": "25 min"},
            {"name": "Maggi", "ingredients": "maggi noodles, vegetables, butter", "prep_time": "10 min"},
            {"name": "Curd Rice", "ingredients": "rice, curd, mustard seeds, curry leaves, pomegranate", "prep_time": "15 min"},
            {"name": "Palak Paneer + Roti", "ingredients": "spinach, paneer, onion, garlic, cream, wheat flour", "prep_time": "35 min"},
            {"name": "Veg Pulao", "ingredients": "basmati rice, mixed vegetables, whole spices, ghee", "prep_time": "25 min"},
            {"name": "Paneer Bhurji + Pav", "ingredients": "paneer, onion, tomato, green chili, pav", "prep_time": "15 min"},
        ],
        "eggetarian": [
            {"name": "Egg Bhurji + Roti", "ingredients": "eggs, onion, tomato, green chili, spices, wheat flour", "prep_time": "15 min"},
            {"name": "Omelette + Paratha", "ingredients": "eggs, onion, green chili, wheat flour, butter", "prep_time": "20 min"},
            {"name": "Egg Roll", "ingredients": "eggs, paratha, onion, chutney, lemon", "prep_time": "15 min"},
        ],
        "non-veg": [
            {"name": "Chicken Tikka", "ingredients": "chicken, curd, spices, lemon, onion", "prep_time": "30 min"},
            {"name": "Butter Chicken + Naan", "ingredients": "chicken, tomato, butter, cream, naan", "prep_time": "45 min"},
            {"name": "Chicken Roll", "ingredients": "chicken, paratha, onion, chutney, lemon", "prep_time": "25 min"},
            {"name": "Egg/Chicken Fried Rice", "ingredients": "chicken, eggs, rice, vegetables, soy sauce", "prep_time": "25 min"},
        ],
    },
}

MEAL_TYPES = ["Breakfast", "Lunch", "Dinner"]
MEAL_EMOJIS = {"Breakfast": "🌅", "Lunch": "☀️", "Dinner": "🌙"}
PREF_EMOJI = {"veg": "🥦", "eggetarian": "🥚", "non-veg": "🍗"}
DIET_ALLOWED = {
    "veg": {"veg"},
    "eggetarian": {"veg", "eggetarian"},
    "non-veg": {"veg", "eggetarian", "non-veg"},
}
OTHER = "✏️ Something else (type it)"


def get_available_recipes(meal_type, preference):
    recipes = list(MASTER_RECIPES.get(meal_type, {}).get("veg", []))
    if preference in ("eggetarian", "non-veg"):
        recipes += MASTER_RECIPES.get(meal_type, {}).get("eggetarian", [])
    if preference == "non-veg":
        recipes += MASTER_RECIPES.get(meal_type, {}).get("non-veg", [])
    return recipes


def norm_diet(x):
    x = norm(x).replace(" ", "-")
    if x in ("vegetarian", "veg"):
        return "veg"
    if x in ("egg", "eggetarian", "egg-veg"):
        return "eggetarian"
    if x in ("nonveg", "non-veg", "non-vegetarian", "meat"):
        return "non-veg"
    return "veg"


@st.cache_data
def load_cookbook():
    """Reads cookbook.json (next to app.py). Missing file = no cookbook suggestions."""
    path = os.path.join(APP_DIR, "cookbook.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("recipes", []) if isinstance(data, dict) else data
        return [r for r in items if isinstance(r, dict) and r.get("name")]
    except Exception:
        return []


def add_or_tag_recipe(code, group, name, meal_types, ingredients="", prep_time="", added_by=""):
    """Add a recipe to the group, or add missing meal types to an existing one.
    Returns (status, recipe) where status is 'added', 'tagged' or 'exists'."""
    name = (name or "").strip()
    recipes = group.get("recipes", [])
    for r in recipes:
        if norm(r.get("name")) == norm(name):
            missing = [m for m in meal_types if m not in r.get("meal_types", [])]
            if missing:
                r["meal_types"] = r.get("meal_types", []) + missing
                group_ref(code).update({"recipes": recipes})
                return "tagged", r
            return "exists", r
    new = {
        "name": name,
        "meal_types": list(meal_types),
        "ingredients": ingredients or "",
        "prep_time": prep_time or "",
        "added_by": added_by,
    }
    group_ref(code).update({"recipes": firestore.ArrayUnion([new])})
    recipes.append(new)
    group["recipes"] = recipes
    return "added", new


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
def history_info(code, ref_date, days=HISTORY_DAYS):
    """Returns last_made {norm_name: days_ago}, counts {norm_name: n}, timeline lines."""
    plans = get_plans_range(code, ref_date - timedelta(days=days), ref_date)
    last_made, counts, lines = {}, Counter(), []
    for ds in sorted(plans):
        logged = plans[ds].get("logged", {}) or {}
        d = datetime.strptime(ds, "%Y-%m-%d").date()
        ago = (ref_date - d).days
        parts = []
        for m in MEAL_TYPES:
            e = logged.get(m.lower())
            if e and e.get("recipe"):
                k = norm(e["recipe"])
                last_made[k] = min(last_made.get(k, 999), ago)
                counts[k] += 1
                parts.append(f"{m} {e['recipe']}")
        if parts:
            lines.append(f"{d.strftime('%a %d %b')}: " + "; ".join(parts))
    return last_made, counts, lines


# ---------------------------------------------------------------------------
# Suggestion engine
# ---------------------------------------------------------------------------
def card_from(r, source, reason="", last_made=None, added_by=""):
    return {
        "name": r.get("name", ""),
        "ingredients": r.get("ingredients", "") or "",
        "prep_time": r.get("prep_time", "") or "",
        "reason": reason or "",
        "source": source,
        "last_made": last_made,
        "added_by": added_by,
        "book": r.get("book", "") or "",
    }


def build_pool(group, meal_type, last_made, counts, mode="quick"):
    """Group recipes for this meal, excluding anything made in the last EXCLUDE_DAYS.
    Returns (pool, rule_order). If almost everything was made recently, the least recent
    ones are let back in so the list is never empty."""
    recipes = [r for r in group.get("recipes", []) if meal_type in r.get("meal_types", [])]
    eligible = [r for r in recipes if last_made.get(norm(r["name"]), 999) >= EXCLUDE_DAYS]
    if len(eligible) < 3:
        recent = [r for r in recipes if r not in eligible]
        recent.sort(key=lambda r: last_made.get(norm(r["name"]), 999), reverse=True)
        eligible += recent[: 3 - len(eligible)]

    def score(r):
        k = norm(r["name"])
        days = min(last_made.get(k, 30), 30)
        tc = time_class(r.get("prep_time"))
        fit = 20 if tc == mode else (8 if tc == "unknown" else 0)
        return days + fit + 0.5 * counts.get(k, 0) + random.uniform(0, 6)

    rule_order = sorted(eligible, key=score, reverse=True)
    return eligible, rule_order


def cookbook_candidates(group, meal_type, last_made, mode="quick", limit=12):
    allowed = DIET_ALLOWED.get(group.get("preference", "veg"), {"veg"})
    have = {norm(r["name"]) for r in group.get("recipes", [])}
    out = []
    for r in load_cookbook():
        mts = r.get("meal_types") or MEAL_TYPES
        if meal_type not in mts:
            continue
        if norm_diet(r.get("diet", "veg")) not in allowed:
            continue
        k = norm(r["name"])
        if k in have or last_made.get(k, 999) < EXCLUDE_DAYS:
            continue
        out.append(r)
    random.shuffle(out)
    return order_by_mode(out, mode, min_keep=NEW_CARDS)[:limit]


def _pick_schema():
    return {
        "type": "object",
        "properties": {"name": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["name", "reason"],
        "additionalProperties": False,
    }


def _meal_schema():
    new_item = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "ingredients": {"type": "string"},
            "prep_time": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["name", "ingredients", "prep_time", "reason"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "kitchen_picks": {"type": "array", "items": _pick_schema()},
            "cookbook_picks": {"type": "array", "items": _pick_schema()},
            "new_recipes": {"type": "array", "items": new_item},
        },
        "required": ["kitchen_picks", "cookbook_picks", "new_recipes"],
        "additionalProperties": False,
    }


def groq_key():
    return secret("GROQ_API_KEY", "") or st.session_state.get("groq_key", "")


def call_groq_json(system, user, schema, max_tokens=3500):
    from groq import Groq

    client = Groq(api_key=groq_key())
    base = dict(
        model=GROQ_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.6,
        max_completion_tokens=max_tokens,
    )
    extra = {"reasoning_effort": "low"} if "gpt-oss" in GROQ_MODEL else None
    try:
        resp = client.chat.completions.create(
            **base,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "meal_plan", "strict": True, "schema": schema},
            },
            extra_body=extra,
        )
    except Exception as e:
        msg = str(e).lower()
        if "rate" in msg or "429" in msg or "api key" in msg or "401" in msg:
            raise
        # Model may not support strict schemas: fall back to plain JSON mode
        resp = client.chat.completions.create(**base, response_format={"type": "json_object"})
    return json.loads(resp.choices[0].message.content)


def friendly_ai_error(e):
    s = str(e)
    low = s.lower()
    if "429" in s or "rate limit" in low or "rate_limit" in low:
        return "Groq's free limit is busy. Wait a minute, then tap Refresh suggestions."
    if "401" in s or "invalid api key" in low or "invalid_api_key" in low:
        return "The Groq key is invalid. Check GROQ_API_KEY in the app's Secrets."
    if "model" in low and ("decommission" in low or "not found" in low or "does not exist" in low):
        return (f"The AI model '{GROQ_MODEL}' is not available. Add GROQ_MODEL = \"<current model>\" "
                "to Secrets (see console.groq.com/docs/models).")
    return f"AI error: {s[:200]}"


def ai_rank_and_suggest(group, meals_ctx, history_lines, ref_date, mode="quick"):
    """One Groq call for all requested meals. meals_ctx[meal] = {pool, cookbook, existing}."""
    pref = group.get("preference", "veg")
    style = ("QUICK: dishes that take at most 30 minutes in total" if mode == "quick" else
             "ELABORATE: more involved, weekend-style dishes taking over 30 minutes")
    payload = {}
    for meal, ctx in meals_ctx.items():
        payload[meal] = {
            "kitchen_pool": [
                {"name": r["name"], "time": r.get("prep_time") or "unknown",
                 "last_made_days_ago": ctx["last_made"].get(norm(r["name"]), "not in last 2 weeks")}
                for r in ctx["pool"]
            ],
            "cookbook_candidates": [
                {"name": r["name"], "time": r.get("prep_time") or "unknown"} for r in ctx["cookbook"]
            ],
            "already_known_dishes": ctx["existing"],
        }
    system = (
        "You plan home-cooked meals for a group of Indian flatmates. Reply with JSON only. "
        f"Strict diet rule: the group is {pref}. veg = no egg, meat or fish. "
        "eggetarian = veg plus eggs, no meat or fish. non-veg = anything."
    )
    user = f"""Today is {ref_date.strftime('%A, %d %B %Y')}.
Today's cooking style: {style}. Times marked "~" are rough estimates.

What the group ate in the last {HISTORY_DAYS} days:
{chr(10).join(history_lines) if history_lines else 'Nothing logged yet.'}

For each meal below:
1. kitchen_picks: order the kitchen_pool from best to worst choice for today (max {MAX_KITCHEN}). Use exact names from kitchen_pool only. Put dishes that fit today's cooking style first, and prefer variety vs recent days (don't repeat yesterday's main ingredient).
2. cookbook_picks: choose up to 3 from cookbook_candidates (exact names) that fit today's cooking style and are practical with ingredients easily found in India. Empty list if none given.
3. new_recipes: invent exactly 3 practical dishes that fit today's cooking style and are NOT in kitchen_pool, cookbook_candidates, already_known_dishes, or recent history. Must follow the diet rule. Short comma-separated ingredients, realistic prep_time like "20 min".
Every reason must be under 12 words and specific to this group.

Meals:
{json.dumps(payload, ensure_ascii=False)}"""
    schema = {
        "type": "object",
        "properties": {m: _meal_schema() for m in meals_ctx},
        "required": list(meals_ctx),
        "additionalProperties": False,
    }
    return call_groq_json(system, user, schema, max_tokens=4000)


def assemble_meal(meal_type, ctx, ai_meal, mode="quick"):
    pool_by = {norm(r["name"]): r for r in ctx["pool"]}
    lm = ctx["last_made"]
    kitchen, seen = [], set()
    if ai_meal:
        for p in ai_meal.get("kitchen_picks", []):
            k = norm(p.get("name"))
            if k in pool_by and k not in seen:
                kitchen.append(card_from(pool_by[k], "kitchen", p.get("reason", ""), lm.get(k)))
                seen.add(k)
    for r in ctx["rule_order"]:
        k = norm(r["name"])
        if k not in seen:
            kitchen.append(card_from(r, "kitchen", "", lm.get(k)))
            seen.add(k)
    kitchen = order_by_mode(kitchen, mode)[:MAX_KITCHEN]
    seen = {norm(c["name"]) for c in kitchen}

    # Cookbook: AI's picks first, then the remaining candidates as backup
    cb_by = {norm(r["name"]): r for r in ctx["cookbook"]}
    cookbook, cb_seen = [], set()
    if ai_meal:
        for p in ai_meal.get("cookbook_picks", []):
            k = norm(p.get("name"))
            if k in cb_by and k not in seen and k not in cb_seen:
                cookbook.append(card_from(cb_by[k], "cookbook", p.get("reason", "")))
                cb_seen.add(k)
    for r in ctx["cookbook"]:
        k = norm(r["name"])
        if k not in seen and k not in cb_seen:
            cookbook.append(card_from(r, "cookbook", "From your cookbook"))
            cb_seen.add(k)

    known = seen | cb_seen | {norm(n) for n in ctx["existing"]} | set(lm)
    ai_new = []
    if ai_meal:
        for r in ai_meal.get("new_recipes", []):
            k = norm(r.get("name"))
            if k and k not in known:
                ai_new.append(card_from(r, "ai", r.get("reason", "")))
                known.add(k)

    # Mix: aim for 2 cookbook + 2 AI; whichever side is short is filled by the other
    take_ai = min(NEW_CARDS // 2, len(ai_new))
    take_cb = min(NEW_CARDS - take_ai, len(cookbook))
    take_ai = min(len(ai_new), NEW_CARDS - take_cb)
    cb_part, ai_part = cookbook[:take_cb], ai_new[:take_ai]
    mixed = []
    for i in range(max(len(cb_part), len(ai_part))):
        mixed += cb_part[i:i + 1] + ai_part[i:i + 1]
    return {"kitchen": kitchen, "cookbook": [], "new": mixed, "mode": mode,
            "ai": bool(ai_meal), "generated_at": now().isoformat()}


def generate_suggestions(code, group, meal_types, ref_date, mode="quick"):
    """Returns ({meal_key: suggestions}, error_message_or_empty)."""
    last_made, counts, lines = history_info(code, ref_date)
    ctxs = {}
    for m in meal_types:
        pool, order = build_pool(group, m, last_made, counts, mode)
        ctxs[m] = {
            "pool": pool,
            "rule_order": order,
            "cookbook": cookbook_candidates(group, m, last_made, mode),
            "existing": [r["name"] for r in group.get("recipes", []) if m in r.get("meal_types", [])],
            "last_made": last_made,
        }
    ai, err = {}, ""
    if groq_key():
        try:
            ai = ai_rank_and_suggest(group, ctxs, lines, ref_date, mode) or {}
        except Exception as e:  # never break the page because of AI
            err = friendly_ai_error(e)
    else:
        err = "AI is off: add GROQ_API_KEY to the app's Secrets."
    return {m.lower(): assemble_meal(m, ctxs[m], ai.get(m), mode) for m in meal_types}, err


def ensure_today(code, group, ds, mode):
    plan = get_plan(code, ds)

    def stale(sugg, logged, mk):
        s_ = (sugg or {}).get(mk) or {}
        if "generated_at" not in s_:
            return True  # never generated, or an old-version list
        return s_.get("mode", "quick") != mode and mk not in logged

    logged = plan.get("logged") or {}
    missing = [m for m in MEAL_TYPES if stale(plan.get("suggestions"), logged, m.lower())]
    if missing:
        with st.spinner("Planning today's menu..."):
            sugg, err = generate_suggestions(code, group, missing, today(), mode)
        latest = get_plan(code, ds)  # a flatmate may have generated it meanwhile
        sugg = {k: v for k, v in sugg.items()
                if stale(latest.get("suggestions"), latest.get("logged") or {}, k)}
        if sugg:
            plan_ref(code, ds).set({"date": ds, "suggestions": sugg, "ai_error": err}, merge=True)
        plan = get_plan(code, ds)
    return plan


def set_mode(code, ds, plan, new_mode):
    """Switch today's cooking style; meals not yet logged get re-planned and their votes reset."""
    ref = plan_ref(code, ds)
    ref.set({"date": ds, "time_mode": new_mode}, merge=True)
    logged = plan.get("logged") or {}
    upd = {}
    for m in MEAL_TYPES:
        mk = m.lower()
        if mk not in logged:
            upd[fp("suggestions", mk)] = firestore.DELETE_FIELD
            upd[fp("votes", mk)] = firestore.DELETE_FIELD
    if upd:
        try:
            ref.update(upd)
        except Exception:
            pass


def refresh_meal(code, group, ds, meal_type, mode):
    mk = meal_type.lower()
    sugg, err = generate_suggestions(code, group, [meal_type], today(), mode)
    ref = plan_ref(code, ds)
    ref.set({"date": ds, "suggestions": {mk: sugg[mk]}, "ai_error": err}, merge=True)
    try:
        ref.update({fp("votes", mk): firestore.DELETE_FIELD})
    except Exception:
        pass
    return err


def invalidate_today_unvoted(code):
    """After history changes, re-plan today's meals nobody has voted on yet."""
    ds = dstr(today())
    plan = get_plan(code, ds)
    votes = plan.get("votes", {}) or {}
    logged = plan.get("logged", {}) or {}
    upd = {}
    for m in MEAL_TYPES:
        mk = m.lower()
        if mk in (plan.get("suggestions") or {}) and not votes.get(mk) and mk not in logged:
            upd[fp("suggestions", mk)] = firestore.DELETE_FIELD
    if upd:
        plan_ref(code, ds).update(upd)


def save_logged(code, ds, mk, dish, cook, user, backfilled=False):
    plan_ref(code, ds).set({"date": ds, "logged": {mk: {
        "recipe": dish.strip(),
        "cooked_by": cook or "",
        "logged_by": user,
        "backfilled": backfilled,
        "timestamp": now().isoformat(),
    }}}, merge=True)


def clear_logged(code, ds, mk):
    try:
        plan_ref(code, ds).update({fp("logged", mk): firestore.DELETE_FIELD})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------------
def flash(msg, kind="success"):
    st.session_state.setdefault("flash", []).append((kind, msg))


def show_flash():
    for kind, msg in st.session_state.pop("flash", []):
        getattr(st, kind, st.info)(msg)


def safe_md(text):
    """Avoid accidental markdown/colour syntax from user-typed names."""
    return (text or "").replace("[", "(").replace("]", ")").replace("*", "").replace("_", " ")


for key, default in {"user_name": "", "current_group": "", "page": "landing",
                     "onboarding_step": 0, "onboarding_data": {}}.items():
    if key not in st.session_state:
        st.session_state[key] = default


@st.dialog("👋 Quick guide", width="large")
def show_guide():
    st.markdown(GUIDE_MD)
    if st.button("Got it", type="primary"):
        st.rerun()


def maybe_show_guide(code, group):
    """Opens the guide once for each person the first time they enter a group."""
    user = st.session_state.user_name
    flag = f"guide_done_{code}"
    if st.session_state.get(flag) or user in (group.get("guide_seen") or []):
        return
    st.session_state[flag] = True
    try:
        group_ref(code).update({"guide_seen": firestore.ArrayUnion([user])})
    except Exception:
        pass
    show_guide()


def generate_group_code():
    chars = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choices(chars, k=6))
        if not group_ref(code).get().exists:
            return code


# ===================================================================
# PAGE: Landing
# ===================================================================
def page_landing():
    st.title(f"{LEAF} {APP_NAME}")
    st.caption("Plan meals together. Vote on what to eat. Never argue about dinner again.")
    with st.expander("👋 New here? How it works"):
        st.markdown("One person creates a group for the flat and shares a 6-letter code. "
                    "Everyone else joins with that code. Then, every day:")
        st.markdown(GUIDE_MD)

    name = st.text_input("Your name", key="input_name", placeholder="e.g. Tannu")
    if not name.strip():
        st.info("Enter your name above to get started.")
        return
    st.session_state.user_name = name.strip()

    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.subheader("🏠 Create a group")
            st.caption("Set up your flat, pick recipes, share a code.")
            if st.button("Create group", type="primary"):
                st.session_state.page = "create_group"
                st.session_state.onboarding_step = 0
                st.session_state.onboarding_data = {}
                st.rerun()
    with col2:
        with st.container(border=True):
            st.subheader("🔗 Join a group")
            join_code = st.text_input("Group code", placeholder="e.g. F302XY", key="join_code_input")
            if st.button("Join group"):
                code = (join_code or "").strip().upper()
                group = get_group(code) if code else None
                if group:
                    if st.session_state.user_name not in group.get("members", []):
                        group_ref(code).update({"members": firestore.ArrayUnion([st.session_state.user_name])})
                    st.session_state.current_group = code
                    st.session_state.page = "daily"
                    st.rerun()
                else:
                    st.error("Group not found. Check the code and try again.")

    groups = db.collection("groups").where("members", "array_contains", st.session_state.user_name).stream()
    user_groups = [(d.id, d.to_dict()) for d in groups]
    if user_groups:
        st.divider()
        st.subheader("Your groups")
        for code, g in user_groups:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                pref = g.get("preference", "")
                c1.markdown(f"**{safe_md(g['name'])}**")
                c1.caption(f"{PREF_EMOJI.get(pref, '')} {pref} · {len(g.get('members', []))} members")
                if c2.button("Open", key=f"open_{code}"):
                    st.session_state.current_group = code
                    st.session_state.page = "daily"
                    st.rerun()


# ===================================================================
# PAGE: Create group (onboarding)
# ===================================================================
def page_create_group():
    step = st.session_state.onboarding_step
    data = st.session_state.onboarding_data
    st.progress((step + 1) / 6, text=f"Step {step + 1} of 6")

    if step == 0:
        st.title(f"{LEAF} Create your group")
        name = st.text_input("Group name", placeholder="e.g. Flat 302 Foodies", value=data.get("name", ""))
        c1, c2 = st.columns(2)
        if c1.button("← Cancel"):
            st.session_state.page = "landing"
            st.rerun()
        if c2.button("Next →", type="primary"):
            if name.strip():
                data["name"] = name.strip()
                st.session_state.onboarding_step = 1
                st.rerun()
            else:
                st.warning("Enter a group name.")

    elif step == 1:
        st.title("🥗 Food preference")
        st.caption("Applies to the whole group. Every suggestion will respect it.")
        c1, c2, c3 = st.columns(3)
        for col, key, label in ((c1, "veg", "🥦 Vegetarian"), (c2, "eggetarian", "🥚 Eggetarian"),
                                (c3, "non-veg", "🍗 Non-veg")):
            if col.button(label, type="primary" if data.get("preference") == key else "secondary"):
                data["preference"] = key
                st.session_state.onboarding_step = 2
                st.rerun()
        if st.button("← Back"):
            st.session_state.onboarding_step = 0
            st.rerun()

    elif step == 2:
        st.title("⏱️ How long do you like to cook?")
        st.caption("This sets each day's default. Anyone can switch it from the toggle at the top of the menu.")
        tp = data.get("time_pref", {"weekday": "quick", "weekend": "elaborate"})
        opts = ["quick", "elaborate"]
        wd = st.radio("On weekdays (Mon to Fri)", opts, index=opts.index(tp["weekday"]),
                      format_func=MODE_LABEL.get, horizontal=True, key="tp_weekday")
        we = st.radio("On weekends (Sat, Sun)", opts, index=opts.index(tp["weekend"]),
                      format_func=MODE_LABEL.get, horizontal=True, key="tp_weekend")
        c1, c2 = st.columns(2)
        if c1.button("← Back"):
            st.session_state.onboarding_step = 1
            st.rerun()
        if c2.button("Next →", type="primary"):
            data["time_pref"] = {"weekday": wd, "weekend": we}
            st.session_state.onboarding_step = 3
            st.rerun()

    elif step in (3, 4, 5):
        meal_type = MEAL_TYPES[step - 3]
        st.title(f"{MEAL_EMOJIS[meal_type]} Pick your {meal_type.lower()} recipes")
        st.caption(f"Select the {meal_type.lower()} dishes your group makes or wants to try.")
        available = get_available_recipes(meal_type, data.get("preference", "veg"))
        sel_key = f"selected_{meal_type.lower()}"
        prev = [r["name"] if isinstance(r, dict) else r for r in data.get(sel_key, [])]
        selected = []
        cols = st.columns(2)
        for i, recipe in enumerate(available):
            with cols[i % 2]:
                if st.checkbox(f"{recipe['name']} ({recipe['prep_time']})", value=recipe["name"] in prev,
                               key=f"cb_{meal_type}_{recipe['name']}", help=recipe["ingredients"]):
                    selected.append(recipe)
        st.divider()
        custom = st.text_input(f"Missing a {meal_type.lower()} dish? Add it (comma-separate several):",
                               placeholder="e.g. Puri Sabzi, Dhokla", key=f"custom_{meal_type}")
        c1, c2 = st.columns(2)
        if c1.button("← Back"):
            data[sel_key] = selected
            st.session_state.onboarding_step = step - 1
            st.rerun()
        if c2.button("Next →" if step < 5 else "Create group ✅", type="primary"):
            for c in (custom or "").split(","):
                if c.strip() and norm(c) not in {norm(r["name"]) for r in selected}:
                    selected.append({"name": c.strip(), "ingredients": "", "prep_time": ""})
            if not selected:
                st.warning(f"Pick at least one {meal_type.lower()} recipe.")
                return
            data[sel_key] = selected
            if step < 5:
                st.session_state.onboarding_step = step + 1
                st.rerun()
            all_recipes = {}
            for mt in MEAL_TYPES:
                for r in data.get(f"selected_{mt.lower()}", []):
                    if not isinstance(r, dict):
                        continue
                    k = norm(r["name"])
                    if k not in all_recipes:
                        all_recipes[k] = {"name": r["name"], "ingredients": r.get("ingredients", ""),
                                          "prep_time": r.get("prep_time", ""), "meal_types": [mt]}
                    elif mt not in all_recipes[k]["meal_types"]:
                        all_recipes[k]["meal_types"].append(mt)
            code = generate_group_code()
            group_ref(code).set({
                "name": data["name"],
                "preference": data["preference"],
                "time_pref": data.get("time_pref", {"weekday": "quick", "weekend": "elaborate"}),
                "members": [st.session_state.user_name],
                "recipes": list(all_recipes.values()),
                "created_by": st.session_state.user_name,
                "created_at": now().isoformat(),
            })
            st.session_state.current_group = code
            st.session_state.page = "group_created"
            st.rerun()


def page_group_created():
    st.balloons()
    st.title("🎉 Group created!")
    group = get_group(st.session_state.current_group)
    if group:
        pref = group.get("preference", "")
        st.subheader(safe_md(group["name"]))
        st.write(f"{PREF_EMOJI.get(pref, '')} {pref} · {len(group.get('recipes', []))} recipes")
    st.divider()
    st.subheader("Share this code with your flatmates")
    st.code(st.session_state.current_group, language=None)
    st.caption("They open the app, type their name, and enter this code.")
    if st.button("Go to today's menu →", type="primary"):
        st.session_state.page = "daily"
        st.rerun()


# ===================================================================
# Sidebar (daily + calendar)
# ===================================================================
def render_sidebar(code, group):
    with st.sidebar:
        st.markdown(f"### {LEAF} {APP_NAME}")
        st.caption(f"Signed in as **{safe_md(st.session_state.user_name)}**")
        c1, c2 = st.columns(2)
        if c1.button("🍽️ Today"):
            st.session_state.page = "daily"
            st.rerun()
        if c2.button("📅 Calendar"):
            st.session_state.page = "calendar"
            st.rerun()
        if st.button("← Switch group"):
            st.session_state.page = "landing"
            st.rerun()
        if st.button("❓ Quick guide"):
            show_guide()

        with st.expander("⏱️ Cooking-time defaults"):
            tp = time_pref(group)
            opts = ["quick", "elaborate"]
            wd = st.radio("Weekdays", opts, index=opts.index(tp["weekday"]), format_func=MODE_LABEL.get,
                          key="sb_tp_weekday")
            we = st.radio("Weekends", opts, index=opts.index(tp["weekend"]), format_func=MODE_LABEL.get,
                          key="sb_tp_weekend")
            if st.button("Save defaults"):
                group_ref(code).update({"time_pref": {"weekday": wd, "weekend": we}})
                flash("Cooking-time defaults saved. They apply from the next day you haven't switched manually.")
                st.rerun()

        st.divider()
        if not secret("GROQ_API_KEY", ""):
            k = st.text_input("Groq API key", type="password", value=st.session_state.get("groq_key", ""),
                              help="Better: add GROQ_API_KEY to the app's Secrets so nobody has to type it.")
            if k:
                st.session_state["groq_key"] = k
        else:
            st.caption(f"🤖 AI suggestions on · {GROQ_MODEL}")
        cb = load_cookbook()
        st.caption(f"📖 Cookbook: {len(cb)} recipes" if cb else "📖 No cookbook added yet")

        st.divider()
        st.markdown("**📝 Add a recipe**")
        with st.form("sidebar_add_recipe", clear_on_submit=True):
            r_name = st.text_input("Recipe name")
            r_meals = st.multiselect("Meal type", MEAL_TYPES)
            r_ing = st.text_input("Ingredients (optional)")
            r_time = st.text_input("Prep time (optional)", placeholder="e.g. 20 min")
            pin = st.checkbox("Also add to today's vote", value=True)
            if st.form_submit_button("Add"):
                if not r_name.strip() or not r_meals:
                    st.warning("Give it a name and at least one meal type.")
                else:
                    status, rec = add_or_tag_recipe(code, group, r_name, r_meals, r_ing, r_time,
                                                    st.session_state.user_name)
                    if pin:
                        ds = dstr(today())
                        plan_ref(code, ds).set({"date": ds, "extra": {
                            m.lower(): {norm(rec["name"]): card_from(rec, "member",
                                                                     added_by=st.session_state.user_name)}
                            for m in r_meals}}, merge=True)
                    where = ", ".join(r_meals)
                    msg = {
                        "added": f"Added **{safe_md(rec['name'])}** to your recipes ({where}).",
                        "tagged": f"**{safe_md(rec['name'])}** was already in your recipes; it now also counts for {where}.",
                        "exists": f"**{safe_md(rec['name'])}** was already in your recipes for {where}.",
                    }[status]
                    if pin:
                        msg += " It's now on today's vote."
                    flash(msg)
                    st.rerun()

        st.divider()
        st.markdown("**👥 Members**")
        for m in group.get("members", []):
            st.write(f"• {m}")


# ===================================================================
# PAGE: Daily planner
# ===================================================================
SOURCE_BADGE = {
    "member": ":blue-background[➕ added by {who}]",
    "cookbook": ":violet-background[📖 {book}]",
    "ai": ":orange-background[✨ New idea]",
}


def render_card(c, mk, idx, votes, counts, top, code, group, meal_type, ds):
    name = c["name"]
    user = st.session_state.user_name
    with st.container(border=True):
        title = f"**{safe_md(name)}**" + (f" · {safe_md(c['prep_time'])}" if c.get("prep_time") else "")
        st.markdown(title)
        badge = SOURCE_BADGE.get(c.get("source"))
        if badge:
            st.markdown(badge.format(who=safe_md(c.get("added_by") or "a flatmate"),
                                     book=safe_md(c.get("book") or "Cookbook")))
        elif c.get("last_made") is not None:
            st.caption(f"Last made {c['last_made']} days ago")
        if c.get("reason"):
            st.caption(c["reason"])
        if c.get("source") in ("cookbook", "ai") and c.get("ingredients"):
            st.caption(f"🧂 {c['ingredients']}")
        n = counts.get(name, 0)
        voters = [k for k, v in votes.items() if v == name]
        line = f"🗳️ **{n}**" + (f" · {safe_md(', '.join(voters))}" if voters else "")
        if n and n == top:
            line += " · :green[**🏆 leading**]"
        st.markdown(line)
        mine = votes.get(user) == name
        if st.button("Voted ✓" if mine else "Vote", key=f"vote_{mk}_{c.get('source')}_{idx}_{name}",
                     disabled=mine, type="secondary" if mine else "primary"):
            plan_ref(code, ds).set({"date": ds, "votes": {mk: {user: name}}}, merge=True)
            if c.get("source") in ("cookbook", "ai"):
                add_or_tag_recipe(code, group, name, [meal_type], c.get("ingredients", ""),
                                  c.get("prep_time", ""), user)
            st.rerun()


def render_meal(code, group, plan, meal_type, ds, mode):
    mk = meal_type.lower()
    user = st.session_state.user_name
    data = (plan.get("suggestions") or {}).get(mk, {})
    votes = (plan.get("votes") or {}).get(mk, {}) or {}
    logged = (plan.get("logged") or {}).get(mk)
    extra = list(((plan.get("extra") or {}).get(mk) or {}).values())
    counts = Counter(votes.values())
    top = max(counts.values()) if counts else 0

    st.header(f"{MEAL_EMOJIS[meal_type]} {meal_type}", divider="green")

    if logged:
        cook = f" · cooked by {safe_md(logged['cooked_by'])}" if logged.get("cooked_by") else ""
        st.success(f"Today's {mk}: **{safe_md(logged['recipe'])}**{cook}")
        if st.button("Undo log", key=f"undo_{mk}"):
            clear_logged(code, ds, mk)
            st.rerun()

    # Kitchen list (member-added first), de-duplicated
    kitchen, seen = [], set()
    for c in extra + data.get("kitchen", []):
        if norm(c["name"]) not in seen:
            kitchen.append(c)
            seen.add(norm(c["name"]))
    newer = [c for c in data.get("cookbook", []) + data.get("new", []) if norm(c["name"]) not in seen][:NEW_CARDS]

    st.markdown("**🔄 From your kitchen**")
    if kitchen:
        st.caption(f"{len(kitchen)} options for {MODE_LABEL[mode].split(' (')[0].lower()} cooking, "
                   f"skipping anything made in the last {EXCLUDE_DAYS} days"
                   + (". Scroll inside the box for more ↓" if len(kitchen) > 2 else ""))
        box = st.container(height=430, border=False) if len(kitchen) > 2 else st.container()
        with box:
            cols = st.columns(2)
            for i, c in enumerate(kitchen):
                with cols[i % 2]:
                    render_card(c, mk, i, votes, counts, top, code, group, meal_type, ds)
    else:
        st.caption("No recipes for this meal yet. Add one below or from the sidebar.")

    st.markdown("**✨ Try something new**")
    if newer:
        n_cb = sum(1 for c in newer if c.get("source") == "cookbook")
        st.caption(f"{n_cb} from your cookbooks 📖 · {len(newer) - n_cb} AI ideas ✨"
                   + (" · cookbook times are rough estimates" if n_cb else ""))
        cols = st.columns(2)
        for i, c in enumerate(newer):
            with cols[i % 2]:
                render_card(c, mk, 100 + i, votes, counts, top, code, group, meal_type, ds)
    else:
        st.caption("No new ideas right now. Tap Refresh suggestions (see the note at the top if AI is off).")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Refresh suggestions", key=f"refresh_{mk}",
                     help="Gets a fresh list. Clears today's votes for this meal."):
            with st.spinner("Thinking..."):
                err = refresh_meal(code, group, ds, meal_type, mode)
            flash(err, "warning") if err else flash(f"New {mk} suggestions ready.")
            st.rerun()

    with st.expander("➕ Add an option to today's vote"):
        others = sorted({r["name"] for r in group.get("recipes", []) if norm(r["name"]) not in seen
                         and norm(r["name"]) not in {norm(c['name']) for c in newer}})
        pick = st.selectbox("Pick from your recipes", others, index=None,
                            placeholder="Choose a recipe", key=f"addpick_{mk}")
        typed = st.text_input("...or type a new dish", key=f"addtyped_{mk}")
        if st.button("Add to vote", key=f"addbtn_{mk}"):
            dish = (typed or "").strip() or pick
            if not dish:
                st.warning("Pick or type a dish first.")
            else:
                _, rec = add_or_tag_recipe(code, group, dish, [meal_type], added_by=user)
                plan_ref(code, ds).set({"date": ds, "extra": {mk: {
                    norm(rec["name"]): card_from(rec, "member", added_by=user)}}}, merge=True)
                flash(f"**{safe_md(rec['name'])}** added to today's {mk} vote.")
                st.rerun()

    with st.expander("📝 Log what you actually made", expanded=bool(votes) and not logged):
        options = [c["name"] for c in kitchen + newer]
        winner = counts.most_common(1)[0][0] if counts else None
        if winner and winner not in options:
            options.insert(0, winner)
        idx = options.index(winner) if winner in options else None
        choice = st.selectbox("Dish", options + [OTHER], index=idx, placeholder="Choose a dish",
                              key=f"logsel_{mk}_{winner}")
        other = st.text_input("Dish name", key=f"logother_{mk}") if choice == OTHER else ""
        cook = st.selectbox("Who cooked?", ["Not specified"] + group.get("members", []), key=f"logcook_{mk}")
        if st.button("Save ✅", key=f"logbtn_{mk}", type="primary"):
            dish = other.strip() if choice == OTHER else (choice or "")
            if not dish:
                st.warning("Choose or type the dish.")
            else:
                save_logged(code, ds, mk, dish, "" if cook == "Not specified" else cook, user)
                add_or_tag_recipe(code, group, dish, [meal_type], added_by=user)
                flash(f"Logged {mk}: **{safe_md(dish)}**")
                st.rerun()

    not_voted = [m for m in group.get("members", []) if m not in votes]
    if not_voted and not logged:
        st.caption(f"⏳ Waiting for votes from: {', '.join(not_voted)}")


def page_daily():
    code = st.session_state.current_group
    group = get_group(code)
    if not group:
        st.error("Group not found.")
        st.session_state.page = "landing"
        st.rerun()
        return
    render_sidebar(code, group)
    ds = dstr(today())

    st.title(f"{LEAF} {safe_md(group['name'])}")
    pref = group.get("preference", "")
    st.caption(f"👥 {', '.join(group.get('members', []))} · {PREF_EMOJI.get(pref, '')} {pref} · "
               f"{now().strftime('%A, %d %B %Y')} · Code **{code}**")
    maybe_show_guide(code, group)

    # Cooking-style toggle (shared by the whole group for today)
    plan0 = get_plan(code, ds)
    mode = plan0.get("time_mode") or default_mode(group, today())
    with st.container(border=True):
        on = st.toggle("🍲 Elaborate cooking today", value=(mode == "elaborate"), key=f"mode_{ds}_{mode}",
                       help="Off: quick dishes, up to 30 min. On: longer, more involved dishes. "
                            "Switching re-plans meals that aren't logged yet and resets their votes.")
        day_type = "weekend" if today().weekday() >= 5 else "weekday"
        st.caption(f"Showing **{MODE_LABEL[mode]}** dishes for everyone. "
                   f"Group default on {day_type}s: {MODE_LABEL[time_pref(group)[day_type]]}.")
    new_mode = "elaborate" if on else "quick"
    if new_mode != mode:
        set_mode(code, ds, plan0, new_mode)
        flash(f"Switched to {MODE_LABEL[new_mode]} for today.", "info")
        st.rerun()

    show_flash()
    plan = ensure_today(code, group, ds, mode)
    if plan.get("ai_error"):
        st.warning(f"{plan['ai_error']} Showing suggestions from your own history meanwhile.")

    for meal_type in MEAL_TYPES:
        render_meal(code, group, plan, meal_type, ds, mode)


# ===================================================================
# PAGE: Calendar (log past meals)
# ===================================================================
def page_calendar():
    code = st.session_state.current_group
    group = get_group(code)
    if not group:
        st.session_state.page = "landing"
        st.rerun()
        return
    render_sidebar(code, group)
    user = st.session_state.user_name

    st.title("📅 Meal calendar")
    st.caption("Pick any past day and record what you ate. This history shapes future suggestions.")
    show_flash()

    sel = st.date_input("Day", value=today(), min_value=today() - timedelta(days=CALENDAR_DAYS_BACK),
                        max_value=today(), format="DD/MM/YYYY")
    ds = dstr(sel)
    st.subheader(sel.strftime("%A, %d %B %Y"))
    logged = get_plan(code, ds).get("logged", {}) or {}
    members = group.get("members", [])

    for meal_type in MEAL_TYPES:
        mk = meal_type.lower()
        cur = logged.get(mk)
        with st.container(border=True):
            st.markdown(f"**{MEAL_EMOJIS[meal_type]} {meal_type}**")
            if cur:
                cook = f" · cooked by {safe_md(cur['cooked_by'])}" if cur.get("cooked_by") else ""
                st.markdown(f":green[✅ **{safe_md(cur['recipe'])}**]{cook}")
            names = [r["name"] for r in group.get("recipes", []) if meal_type in r.get("meal_types", [])]
            names += sorted(r["name"] for r in group.get("recipes", []) if meal_type not in r.get("meal_types", []))
            idx = names.index(cur["recipe"]) if cur and cur.get("recipe") in names else None
            choice = st.selectbox("What did you make?", names + [OTHER], index=idx,
                                  placeholder="Choose a dish", key=f"cal_{ds}_{mk}")
            other = st.text_input("Dish name", key=f"calother_{ds}_{mk}") if choice == OTHER else ""
            cook_opts = ["Not specified"] + members
            cidx = cook_opts.index(cur["cooked_by"]) if cur and cur.get("cooked_by") in cook_opts else 0
            cook = st.selectbox("Who cooked?", cook_opts, index=cidx, key=f"calcook_{ds}_{mk}")
            b1, b2 = st.columns(2)
            if b1.button("Save", key=f"calsave_{ds}_{mk}", type="primary"):
                dish = other.strip() if choice == OTHER else (choice or "")
                if not dish:
                    st.warning("Choose or type the dish.")
                else:
                    save_logged(code, ds, mk, dish, "" if cook == "Not specified" else cook, user,
                                backfilled=(sel != today()))
                    add_or_tag_recipe(code, group, dish, [meal_type], added_by=user)
                    if (today() - sel).days <= EXCLUDE_DAYS:
                        invalidate_today_unvoted(code)
                    flash(f"Saved {mk} for {sel.strftime('%d %b')}: **{safe_md(dish)}**")
                    st.rerun()
            if cur and b2.button("Clear", key=f"calclear_{ds}_{mk}"):
                clear_logged(code, ds, mk)
                if (today() - sel).days <= EXCLUDE_DAYS:
                    invalidate_today_unvoted(code)
                flash(f"Cleared {mk} for {sel.strftime('%d %b')}.", "info")
                st.rerun()

    # Last 14 days at a glance + stats
    st.divider()
    st.subheader("Last 14 days")
    plans = get_plans_range(code, today() - timedelta(days=13), today())
    rows, cooks, dishes = [], Counter(), Counter()
    for i in range(14):
        d = today() - timedelta(days=i)
        lg = (plans.get(dstr(d), {}) or {}).get("logged", {}) or {}
        row = {"Day": d.strftime("%a %d %b")}
        for m in MEAL_TYPES:
            e = lg.get(m.lower())
            row[m] = e["recipe"] if e else ""
            if e:
                dishes[e["recipe"]] += 1
                if e.get("cooked_by"):
                    cooks[e["cooked_by"]] += 1
        rows.append(row)
    st.dataframe(rows, hide_index=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Meals logged", sum(dishes.values()))
    c2.metric("Different dishes", len(dishes))
    if cooks:
        who, n = cooks.most_common(1)[0]
        c3.metric("Top chef 👨‍🍳", f"{who} ({n})")
    if dishes:
        st.caption("Most made: " + ", ".join(f"{k} ({v})" for k, v in dishes.most_common(5)))


# ===================================================================
# Routing
# ===================================================================
PAGES = {
    "landing": page_landing,
    "create_group": page_create_group,
    "group_created": page_group_created,
    "daily": page_daily,
    "calendar": page_calendar,
    "history": page_calendar,
}
PAGES.get(st.session_state.page, page_landing)()
