import streamlit as st
import json
import random
import string
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Firebase initialization
# ---------------------------------------------------------------------------
import firebase_admin
from firebase_admin import credentials, firestore

@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        # Easiest option: paste the whole Firebase JSON key file into secrets
        # as FIREBASE_JSON = '''{ ...contents... }'''
        if "FIREBASE_JSON" in st.secrets:
            cred_dict = json.loads(st.secrets["FIREBASE_JSON"])
        else:
            cred_dict = dict(st.secrets["firebase"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_firebase()

# ---------------------------------------------------------------------------
# Master recipe database (shown during onboarding)
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

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def generate_group_code():
    """Generate a short unique group code."""
    chars = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choices(chars, k=6))
        # Check if code already exists
        doc = db.collection("groups").document(code).get()
        if not doc.exists:
            return code

def get_available_recipes(meal_type, preference):
    """Get recipes available for a meal type based on group preference."""
    recipes = list(MASTER_RECIPES.get(meal_type, {}).get("veg", []))
    if preference in ("eggetarian", "non-veg"):
        recipes += MASTER_RECIPES.get(meal_type, {}).get("eggetarian", [])
    if preference == "non-veg":
        recipes += MASTER_RECIPES.get(meal_type, {}).get("non-veg", [])
    return recipes

def get_group(code):
    """Fetch group data from Firestore."""
    doc = db.collection("groups").document(code).get()
    if doc.exists:
        return doc.to_dict()
    return None

def get_daily_plan(code, date_str):
    """Fetch daily plan (suggestions, votes, logged meals) for a date."""
    doc = db.collection("groups").document(code).collection("daily_plans").document(date_str).get()
    if doc.exists:
        return doc.to_dict()
    return None

def save_daily_plan(code, date_str, plan_data):
    """Save/update daily plan."""
    db.collection("groups").document(code).collection("daily_plans").document(date_str).set(plan_data, merge=True)

def generate_kitchen_suggestions(group_data, meal_type, date_str, count=5):
    """Pick 3-5 recipes from group's list, prioritizing less recent ones."""
    group_recipes = [r for r in group_data.get("recipes", []) if meal_type in r.get("meal_types", [])]
    if not group_recipes:
        return []

    # Get recent history (last 7 days)
    recent_meals = []
    for i in range(1, 8):
        past_date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        past_plan = get_daily_plan(st.session_state.current_group, past_date)
        if past_plan:
            logged = past_plan.get("logged", {}).get(meal_type.lower())
            if logged:
                recent_meals.append(logged.get("recipe", ""))

    # Score recipes: higher score = better suggestion
    scored = []
    for recipe in group_recipes:
        name = recipe["name"]
        if name in recent_meals[:2]:
            # Skip if made in last 2 days
            continue
        score = random.uniform(0, 1)  # base randomness
        if name not in recent_meals:
            score += 3  # not made in a week = big boost
        elif name in recent_meals[3:]:
            score += 1  # made 4-7 days ago = small boost
        scored.append((recipe, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [r for r, s in scored[:count]]

def get_ai_suggestions(group_data, meal_type, groq_key):
    """Get 2 new recipe suggestions from Groq."""
    try:
        from groq import Groq
        client = Groq(api_key=groq_key)
    except Exception as e:
        return []

    existing_names = [r["name"] for r in group_data.get("recipes", []) if meal_type in r.get("meal_types", [])]
    preference = group_data.get("preference", "veg")

    # Get common ingredients from group's recipes
    all_ingredients = set()
    for r in group_data.get("recipes", []):
        all_ingredients.update(r.get("ingredients", "").split(", "))

    prompt = f"""You are a meal suggestion assistant for a group of Indian flatmates.

Their food preference: {preference}
Their existing {meal_type.lower()} recipes: {', '.join(existing_names) if existing_names else 'None yet'}
Ingredients they commonly use: {', '.join(list(all_ingredients)[:25]) if all_ingredients else 'Not specified'}

Suggest exactly 2 NEW {meal_type.lower()} recipes they should try.

Rules:
- Must respect their food preference ({preference})
- Different from their existing recipes
- Practical for home cooking in an Indian kitchen
- Not too complicated

Return ONLY valid JSON array with exactly 2 objects, no other text:
[
  {{
    "name": "Recipe Name",
    "ingredients": "ingredient1, ingredient2, ingredient3",
    "reason": "One line on why they would like this",
    "prep_time": "XX min"
  }},
  {{
    "name": "Recipe Name",
    "ingredients": "ingredient1, ingredient2, ingredient3",
    "reason": "One line on why they would like this",
    "prep_time": "XX min"
  }}
]"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a practical meal planner. Return ONLY valid JSON, no markdown, no explanation."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        text = response.choices[0].message.content.strip()
        # Try to extract JSON if wrapped in markdown
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception as e:
        return []

# ---------------------------------------------------------------------------
# UI: Page routing
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Meal Planner", page_icon="🍳", layout="wide")

st.markdown("""
<style>
    .stApp { max-width: 1100px; margin: 0 auto; }
    div[data-testid="stHorizontalBlock"] { gap: 0.5rem; }
    .vote-card {
        border: 2px solid #e0e0e0;
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        min-height: 140px;
    }
    .vote-card-winner {
        border: 2px solid #4CAF50;
        background-color: #f0fff0;
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        min-height: 140px;
    }
    .new-card {
        border: 2px solid #FFD700;
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        min-height: 140px;
        background-color: #fffef5;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
for key, default in {
    "user_name": "",
    "current_group": "",
    "page": "landing",
    "onboarding_step": 0,
    "onboarding_data": {},
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ===================================================================
# PAGE: Landing
# ===================================================================
def page_landing():
    st.title("🍳 Flatmate Meal Planner")
    st.caption("Plan meals together. Vote on what to eat. Never argue about dinner again.")

    st.text_input("Your name", key="input_name", placeholder="e.g. Tannu")

    if not st.session_state.input_name:
        st.info("Enter your name above to get started.")
        return

    st.session_state.user_name = st.session_state.input_name.strip()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🏠 Create a New Group")
        st.caption("Set up a group for your flat. You'll pick recipes and share a code with flatmates.")
        if st.button("Create Group", use_container_width=True, type="primary"):
            st.session_state.page = "create_group"
            st.session_state.onboarding_step = 0
            st.session_state.onboarding_data = {}
            st.rerun()

    with col2:
        st.subheader("🔗 Join an Existing Group")
        st.caption("Got a group code from a flatmate? Enter it below.")
        join_code = st.text_input("Group code", placeholder="e.g. F302XY", key="join_code_input")
        if st.button("Join Group", use_container_width=True):
            if join_code:
                code = join_code.strip().upper()
                group = get_group(code)
                if group:
                    # Add member if not already in
                    members = group.get("members", [])
                    if st.session_state.user_name not in members:
                        members.append(st.session_state.user_name)
                        db.collection("groups").document(code).update({"members": members})
                    st.session_state.current_group = code
                    st.session_state.page = "daily"
                    st.rerun()
                else:
                    st.error("Group not found. Check the code and try again.")

    # Show groups user is already in
    groups_ref = db.collection("groups").where("members", "array_contains", st.session_state.user_name).stream()
    user_groups = [(doc.id, doc.to_dict()) for doc in groups_ref]

    if user_groups:
        st.markdown("---")
        st.subheader("Your Groups")
        for code, group in user_groups:
            col1, col2, col3 = st.columns([3, 2, 1])
            col1.write(f"**{group['name']}**")
            pref_emoji = {"veg": "🥦", "eggetarian": "🥚", "non-veg": "🍗"}.get(group.get("preference", ""), "")
            col2.write(f"{pref_emoji} {group.get('preference', '')} | {len(group.get('members', []))} members")
            if col3.button("Open", key=f"open_{code}"):
                st.session_state.current_group = code
                st.session_state.page = "daily"
                st.rerun()


# ===================================================================
# PAGE: Create Group (onboarding)
# ===================================================================
def page_create_group():
    step = st.session_state.onboarding_step
    data = st.session_state.onboarding_data

    # Progress bar
    total_steps = 5  # name, preference, breakfast, lunch, dinner
    st.progress((step + 1) / total_steps, text=f"Step {step + 1} of {total_steps}")

    # --- Step 0: Group name ---
    if step == 0:
        st.title("🏠 Create Your Group")
        name = st.text_input("Group name", placeholder="e.g. Flat 302 Foodies", value=data.get("name", ""))
        if st.button("Next →", type="primary"):
            if name.strip():
                data["name"] = name.strip()
                st.session_state.onboarding_data = data
                st.session_state.onboarding_step = 1
                st.rerun()
            else:
                st.warning("Enter a group name.")

    # --- Step 1: Food preference ---
    elif step == 1:
        st.title(f"🥗 Food Preference for {data.get('name', 'Your Group')}")
        st.caption("This applies to the whole group. All suggestions will respect this choice.")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🥦\n\nVegetarian", use_container_width=True,
                         type="primary" if data.get("preference") == "veg" else "secondary"):
                data["preference"] = "veg"
                st.session_state.onboarding_data = data
                st.session_state.onboarding_step = 2
                st.rerun()
        with col2:
            if st.button("🥚\n\nEggetarian", use_container_width=True,
                         type="primary" if data.get("preference") == "eggetarian" else "secondary"):
                data["preference"] = "eggetarian"
                st.session_state.onboarding_data = data
                st.session_state.onboarding_step = 2
                st.rerun()
        with col3:
            if st.button("🍗\n\nNon-Veg", use_container_width=True,
                         type="primary" if data.get("preference") == "non-veg" else "secondary"):
                data["preference"] = "non-veg"
                st.session_state.onboarding_data = data
                st.session_state.onboarding_step = 2
                st.rerun()

        if st.button("← Back"):
            st.session_state.onboarding_step = 0
            st.rerun()

    # --- Steps 2-4: Pick recipes for breakfast, lunch, dinner ---
    elif step in (2, 3, 4):
        meal_idx = step - 2
        meal_type = MEAL_TYPES[meal_idx]
        emoji = MEAL_EMOJIS[meal_type]

        st.title(f"{emoji} Pick Your {meal_type} Recipes")
        st.caption(f"Select the {meal_type.lower()} dishes your group makes or wants to try.")

        available = get_available_recipes(meal_type, data.get("preference", "veg"))
        selected_key = f"selected_{meal_type.lower()}"

        # Show checkboxes for each recipe
        previously_selected = data.get(selected_key, [])
        selected = []

        cols = st.columns(2)
        for i, recipe in enumerate(available):
            with cols[i % 2]:
                default = recipe["name"] in previously_selected
                if st.checkbox(
                    f"**{recipe['name']}** ({recipe['prep_time']})",
                    value=default,
                    key=f"cb_{meal_type}_{recipe['name']}",
                    help=recipe["ingredients"]
                ):
                    selected.append(recipe)

        # Custom recipe input
        st.markdown("---")
        custom = st.text_input(
            f"Don't see your {meal_type.lower()} recipe? Add it:",
            placeholder="e.g. Pav Bhaji",
            key=f"custom_{meal_type}"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Back"):
                # Save current selections before going back
                data[selected_key] = [r["name"] for r in selected]
                st.session_state.onboarding_data = data
                st.session_state.onboarding_step = step - 1
                st.rerun()
        with col2:
            next_label = "Next →" if step < 4 else "Create Group ✅"
            if st.button(next_label, type="primary"):
                if custom and custom.strip():
                    selected.append({
                        "name": custom.strip(),
                        "ingredients": "",
                        "prep_time": "? min",
                    })

                if not selected:
                    st.warning(f"Pick at least one {meal_type.lower()} recipe.")
                else:
                    # Save selected recipes with meal_type tag
                    data[selected_key] = selected
                    st.session_state.onboarding_data = data

                    if step < 4:
                        st.session_state.onboarding_step = step + 1
                        st.rerun()
                    else:
                        # --- FINAL: Create group in Firestore ---
                        code = generate_group_code()

                        # Merge all recipes, tag with meal types
                        all_recipes = {}
                        for mt in MEAL_TYPES:
                            key = f"selected_{mt.lower()}"
                            for r in data.get(key, []):
                                name = r["name"] if isinstance(r, dict) else r
                                if isinstance(r, dict):
                                    if name not in all_recipes:
                                        all_recipes[name] = {
                                            "name": name,
                                            "ingredients": r.get("ingredients", ""),
                                            "prep_time": r.get("prep_time", ""),
                                            "meal_types": [mt],
                                        }
                                    else:
                                        if mt not in all_recipes[name]["meal_types"]:
                                            all_recipes[name]["meal_types"].append(mt)

                        group_doc = {
                            "name": data["name"],
                            "preference": data["preference"],
                            "members": [st.session_state.user_name],
                            "recipes": list(all_recipes.values()),
                            "created_by": st.session_state.user_name,
                            "created_at": datetime.now().isoformat(),
                        }

                        db.collection("groups").document(code).set(group_doc)

                        st.session_state.current_group = code
                        st.session_state.page = "group_created"
                        st.rerun()


# ===================================================================
# PAGE: Group Created (show code)
# ===================================================================
def page_group_created():
    st.balloons()
    st.title("🎉 Group Created!")

    group = get_group(st.session_state.current_group)
    if group:
        st.subheader(group["name"])
        pref_emoji = {"veg": "🥦", "eggetarian": "🥚", "non-veg": "🍗"}.get(group.get("preference", ""), "")
        st.write(f"Preference: {pref_emoji} {group.get('preference', '')}")
        st.write(f"Recipes added: {len(group.get('recipes', []))}")

    st.markdown("---")
    st.subheader("Share this code with your flatmates:")
    st.code(st.session_state.current_group, language=None)
    st.caption("They just need to enter this code + their name to join.")

    if st.button("Go to Meal Planner →", type="primary"):
        st.session_state.page = "daily"
        st.rerun()


# ===================================================================
# PAGE: Daily Planner (main screen)
# ===================================================================
def page_daily():
    code = st.session_state.current_group
    group = get_group(code)

    if not group:
        st.error("Group not found.")
        st.session_state.page = "landing"
        st.rerun()
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_display = datetime.now().strftime("%A, %B %d, %Y")

    # --- Header ---
    hcol1, hcol2 = st.columns([3, 1])
    with hcol1:
        st.title(f"🏠 {group['name']}")
        pref_emoji = {"veg": "🥦", "eggetarian": "🥚", "non-veg": "🍗"}.get(group.get("preference", ""), "")
        members_str = ", ".join(group.get("members", []))
        st.caption(f"👥 {members_str}  |  {pref_emoji} {group.get('preference', '')}  |  {today_display}")
    with hcol2:
        st.code(code, language=None)
        st.caption("Group code")

    # --- Sidebar ---
    with st.sidebar:
        st.header(f"👤 {st.session_state.user_name}")

        if st.button("← Switch Group"):
            st.session_state.page = "landing"
            st.rerun()

        st.markdown("---")
        st.subheader("⚙️ Settings")

        # Groq key is read from secrets so flatmates never have to enter it
        secret_key = st.secrets.get("GROQ_API_KEY", "")
        if secret_key:
            st.session_state["groq_key"] = secret_key
            st.caption("🤖 AI suggestions: ON")
        else:
            groq_key = st.text_input(
                "Groq API Key",
                type="password",
                help="Free at console.groq.com (or add GROQ_API_KEY to app secrets)",
                value=st.session_state.get("groq_key", ""),
            )
            if groq_key:
                st.session_state["groq_key"] = groq_key

        st.markdown("---")
        st.subheader("📝 Add New Recipe")
        with st.form("sidebar_add_recipe"):
            r_name = st.text_input("Recipe name")
            r_meals = st.multiselect("Meal type", MEAL_TYPES)
            r_ingredients = st.text_input("Ingredients (comma-separated)")
            r_time = st.text_input("Prep time", placeholder="e.g. 20 min")
            if st.form_submit_button("Add"):
                if r_name and r_meals:
                    new_recipe = {
                        "name": r_name.strip(),
                        "meal_types": r_meals,
                        "ingredients": r_ingredients.strip(),
                        "prep_time": r_time.strip(),
                    }
                    existing_names = [r["name"].lower() for r in group.get("recipes", [])]
                    if r_name.strip().lower() not in existing_names:
                        recipes = group.get("recipes", [])
                        recipes.append(new_recipe)
                        db.collection("groups").document(code).update({"recipes": recipes})
                        st.success(f"Added: {r_name}")
                        st.rerun()
                    else:
                        st.warning("Already exists!")

        st.markdown("---")
        st.subheader("👥 Members")
        for m in group.get("members", []):
            st.write(f"• {m}")

        st.markdown("---")
        if st.button("📊 View History"):
            st.session_state.page = "history"
            st.rerun()

    # --- Daily plan: generate or load ---
    plan = get_daily_plan(code, today_str)
    if plan is None:
        plan = {"suggestions": {}, "votes": {}, "logged": {}}

    # --- Each meal ---
    for meal_type in MEAL_TYPES:
        emoji = MEAL_EMOJIS[meal_type]
        meal_key = meal_type.lower()

        st.markdown(f"## {emoji} {meal_type}")

        # Check if already logged
        logged = plan.get("logged", {}).get(meal_key)
        if logged:
            st.success(
                f"✅ Today's {meal_type.lower()}: **{logged['recipe']}**"
                + (f"  (cooked by {logged['cooked_by']})" if logged.get("cooked_by") else "")
            )

        # Generate suggestions if not already done for today
        suggestions = plan.get("suggestions", {}).get(meal_key)
        if not suggestions:
            kitchen = generate_kitchen_suggestions(group, meal_type, today_str, count=5)
            kitchen_data = [{"name": r["name"], "ingredients": r.get("ingredients", ""), "prep_time": r.get("prep_time", "")} for r in kitchen]

            ai_data = []
            if st.session_state.get("groq_key"):
                ai_data = get_ai_suggestions(group, meal_type, st.session_state["groq_key"])

            suggestions = {"kitchen": kitchen_data, "new": ai_data}

            if "suggestions" not in plan:
                plan["suggestions"] = {}
            plan["suggestions"][meal_key] = suggestions
            save_daily_plan(code, today_str, plan)

        # Current votes
        votes = plan.get("votes", {}).get(meal_key, {})
        my_vote = votes.get(st.session_state.user_name, "")

        # --- SECTION 1: From Your Kitchen ---
        st.markdown("**🔄 From Your Kitchen**")
        kitchen_items = suggestions.get("kitchen", [])

        if kitchen_items:
            cols = st.columns(min(len(kitchen_items), 5))
            for i, recipe in enumerate(kitchen_items):
                with cols[i % len(cols)]:
                    name = recipe["name"] if isinstance(recipe, dict) else recipe
                    prep = recipe.get("prep_time", "") if isinstance(recipe, dict) else ""

                    vote_count = sum(1 for v in votes.values() if v == name)
                    voters = [k for k, v in votes.items() if v == name]
                    is_winner = vote_count > 0 and vote_count == max(
                        (sum(1 for v in votes.values() if v == n["name"]) for n in kitchen_items + suggestions.get("new", [])),
                        default=0,
                    )

                    # Card
                    card_class = "vote-card-winner" if is_winner else "vote-card"
                    voters_str = ", ".join(voters) if voters else ""
                    st.markdown(f"""<div class="{card_class}">
                        <strong>{name}</strong><br>
                        <small>{prep}</small><br><br>
                        🗳️ <strong>{vote_count}</strong><br>
                        <small>{voters_str}</small>
                    </div>""", unsafe_allow_html=True)

                    voted_for_this = my_vote == name
                    btn_label = "Voted ✓" if voted_for_this else "Vote!"
                    if st.button(btn_label, key=f"vote_{meal_key}_{name}", disabled=voted_for_this, use_container_width=True):
                        if "votes" not in plan:
                            plan["votes"] = {}
                        if meal_key not in plan["votes"]:
                            plan["votes"][meal_key] = {}
                        plan["votes"][meal_key][st.session_state.user_name] = name
                        save_daily_plan(code, today_str, plan)
                        st.rerun()
        else:
            st.caption("No recipes found for this meal. Add some in the sidebar!")

        # --- SECTION 2: New Suggestions ---
        st.markdown("**✨ Try Something New**")
        new_items = suggestions.get("new", [])

        if new_items:
            cols = st.columns(2)
            for i, recipe in enumerate(new_items):
                with cols[i % 2]:
                    name = recipe.get("name", "New Recipe")
                    ingredients = recipe.get("ingredients", "")
                    reason = recipe.get("reason", "")
                    prep = recipe.get("prep_time", "")

                    vote_count = sum(1 for v in votes.values() if v == name)
                    voters = [k for k, v in votes.items() if v == name]
                    voters_str = ", ".join(voters) if voters else ""

                    st.markdown(f"""<div class="new-card">
                        <strong>🆕 {name}</strong><br>
                        <small>{prep}</small><br><br>
                        <small>{ingredients}</small><br>
                        <em><small>"{reason}"</small></em><br><br>
                        🗳️ <strong>{vote_count}</strong><br>
                        <small>{voters_str}</small>
                    </div>""", unsafe_allow_html=True)

                    voted_for_this = my_vote == name
                    btn_label = "Voted ✓" if voted_for_this else "Vote!"
                    if st.button(btn_label, key=f"vote_{meal_key}_new_{name}", disabled=voted_for_this, use_container_width=True):
                        if "votes" not in plan:
                            plan["votes"] = {}
                        if meal_key not in plan["votes"]:
                            plan["votes"][meal_key] = {}
                        plan["votes"][meal_key][st.session_state.user_name] = name

                        # Auto-save new recipe to group's list
                        existing_names = [r["name"].lower() for r in group.get("recipes", [])]
                        if name.lower() not in existing_names:
                            recipes = group.get("recipes", [])
                            recipes.append({
                                "name": name,
                                "meal_types": [meal_type],
                                "ingredients": ingredients,
                                "prep_time": prep,
                            })
                            db.collection("groups").document(code).update({"recipes": recipes})

                        save_daily_plan(code, today_str, plan)
                        st.rerun()
        else:
            if not st.session_state.get("groq_key"):
                st.caption("Add your free Groq API key in the sidebar to get AI suggestions.")
            else:
                if st.button(f"🤖 Get new {meal_type.lower()} ideas", key=f"refresh_ai_{meal_key}"):
                    ai_data = get_ai_suggestions(group, meal_type, st.session_state["groq_key"])
                    if ai_data:
                        plan["suggestions"][meal_key]["new"] = ai_data
                        save_daily_plan(code, today_str, plan)
                        st.rerun()
                    else:
                        st.warning("Could not generate suggestions. Try again.")

        # --- Winner & Log ---
        if votes and not logged:
            vote_counts = {}
            all_recipe_names = [r["name"] if isinstance(r, dict) else r for r in kitchen_items] + [r.get("name", "") for r in new_items]
            for v in votes.values():
                vote_counts[v] = vote_counts.get(v, 0) + 1
            if vote_counts:
                winner = max(vote_counts, key=vote_counts.get)
                winner_count = vote_counts[winner]

                st.markdown(f"**🏆 Leading: {winner} ({winner_count} vote{'s' if winner_count > 1 else ''})**")

                log_col1, log_col2, log_col3 = st.columns([2, 2, 1])
                with log_col1:
                    log_recipe = st.text_input(
                        "Log meal (change if different)",
                        value=winner,
                        key=f"log_recipe_{meal_key}"
                    )
                with log_col2:
                    log_cook = st.selectbox(
                        "Who cooked?",
                        [""] + group.get("members", []),
                        key=f"log_cook_{meal_key}"
                    )
                with log_col3:
                    st.write("")  # spacing
                    st.write("")
                    if st.button("Log ✅", key=f"log_btn_{meal_key}", type="primary"):
                        if "logged" not in plan:
                            plan["logged"] = {}
                        plan["logged"][meal_key] = {
                            "recipe": log_recipe,
                            "cooked_by": log_cook,
                            "timestamp": datetime.now().isoformat(),
                        }
                        save_daily_plan(code, today_str, plan)
                        st.rerun()

        # Who hasn't voted yet
        members = group.get("members", [])
        not_voted = [m for m in members if m not in votes]
        if not_voted and not logged:
            st.caption(f"⏳ Waiting for: {', '.join(not_voted)}")

        st.markdown("---")


# ===================================================================
# PAGE: History
# ===================================================================
def page_history():
    code = st.session_state.current_group
    group = get_group(code)

    st.title(f"📊 Meal History - {group['name']}")

    if st.button("← Back to Planner"):
        st.session_state.page = "daily"
        st.rerun()

    # Fetch last 14 days
    history_data = []
    for i in range(14):
        date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        plan = get_daily_plan(code, date_str)
        if plan and plan.get("logged"):
            history_data.append((date_str, plan["logged"]))

    if not history_data:
        st.info("No meals logged yet. Start by voting and logging meals!")
        return

    for date_str, logged in history_data:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        st.subheader(date_obj.strftime("%A, %b %d"))

        for meal_type in MEAL_TYPES:
            meal_key = meal_type.lower()
            if meal_key in logged:
                entry = logged[meal_key]
                emoji = MEAL_EMOJIS[meal_type]
                cooked_by = f" (by {entry['cooked_by']})" if entry.get("cooked_by") else ""
                st.write(f"{emoji} **{meal_type}:** {entry['recipe']}{cooked_by}")

    # Stats
    st.markdown("---")
    st.subheader("📈 Quick Stats")

    all_meals = []
    cook_counts = {}
    recipe_counts = {}
    for date_str, logged in history_data:
        for meal_key, entry in logged.items():
            all_meals.append(entry)
            recipe_counts[entry["recipe"]] = recipe_counts.get(entry["recipe"], 0) + 1
            if entry.get("cooked_by"):
                cook_counts[entry["cooked_by"]] = cook_counts.get(entry["cooked_by"], 0) + 1

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Meals Logged", len(all_meals))
    col2.metric("Unique Recipes", len(recipe_counts))
    if cook_counts:
        top_cook = max(cook_counts, key=cook_counts.get)
        col3.metric("Top Chef 👨‍🍳", f"{top_cook} ({cook_counts[top_cook]})")

    if recipe_counts:
        st.subheader("Most Made Recipes")
        sorted_recipes = sorted(recipe_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        for name, count in sorted_recipes:
            st.write(f"• **{name}** - made {count} time{'s' if count > 1 else ''}")


# ===================================================================
# Main routing
# ===================================================================
page = st.session_state.page

if page == "landing":
    page_landing()
elif page == "create_group":
    page_create_group()
elif page == "group_created":
    page_group_created()
elif page == "daily":
    page_daily()
elif page == "history":
    page_history()
else:
    st.session_state.page = "landing"
    st.rerun()
