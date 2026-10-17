# Flatmate Meal Planner: Setup Guide

Goal: a link like `https://flat-meals.streamlit.app` that you and your flatmates can open anytime, from any phone, even when your laptop is off.

Total time: about 30 minutes, one time only. Cost: zero. No credit card anywhere.

---

## How it works (the big picture)

| Piece | Job | Where it lives |
|---|---|---|
| GitHub | Stores your code | github.com (free) |
| Streamlit Community Cloud | Runs the app 24/7 and gives you the link | share.streamlit.io (free) |
| Firebase Firestore | Stores groups, recipes, votes, history | Google cloud (free) |
| Groq | AI brain for "Try Something New" | groq.com (free) |

Your laptop is only used for setup. After that, it can be off.

---

## Part 1: Get your Groq key (3 min)

1. Open https://console.groq.com and sign in with Google.
2. Left menu: **API Keys**, then **Create API Key**. Name it `meal-planner`.
3. Copy the key (starts with `gsk_`). Paste it into Notepad. You can only see it once.

## Part 2: Set up Firebase (10 min)

1. Open https://console.firebase.google.com and sign in.
2. Click **Create a project**. Name: `meal-planner`. Turn **off** Google Analytics. Click **Create project**, then **Continue**.
3. Left menu: **Build > Firestore Database > Create database**.
   - Location: `asia-south1 (Mumbai)`.
   - Mode: choose **Production mode**. (The app uses an admin key that works regardless, and production mode never expires. Test mode stops working after 30 days.)
   - Click **Create**.
4. Click the **gear icon** next to "Project Overview" > **Project settings** > **Service accounts** tab.
5. Click **Generate new private key** > **Generate key**. A `.json` file downloads.
6. Treat this file like a password. Never upload it to GitHub.

## Part 3: Put the code on GitHub (5 min)

1. Sign up at https://github.com (free).
2. Top right **+** > **New repository**. Name: `meal-planner`. Choose **Public** (Private also works). Click **Create repository**.
3. Click **uploading an existing file**. Drag in exactly these files:
   - `app.py`
   - `requirements.txt`
   - `README.md`
4. Click **Commit changes**.

Do NOT upload the Firebase JSON file or your Groq key.

## Part 4: Deploy on Streamlit Community Cloud (7 min)

1. Open https://share.streamlit.io and click **Continue with GitHub**. Allow access.
2. Click **Create app** > **Deploy a public app from GitHub**.
3. Fill in:
   - Repository: `your-username/meal-planner`
   - Branch: `main`
   - Main file path: `app.py`
   - App URL: pick something like `flat-meals`
4. Click **Advanced settings**. In the **Secrets** box, paste this template:

```toml
GROQ_API_KEY = "paste-your-gsk-key-here"

FIREBASE_JSON = '''
PASTE THE ENTIRE CONTENTS OF YOUR FIREBASE .json FILE HERE
'''
```

5. Open the Firebase `.json` file in Notepad, select all (Ctrl+A), copy, and paste it between the two `'''` lines. Replace the Groq placeholder with your real key.
6. Click **Save**, then **Deploy**.
7. Wait 2 to 4 minutes. Your app opens at `https://flat-meals.streamlit.app`.

## Part 5: Start using it (2 min)

1. Open the link, type your name, click **Create Group**.
2. Group name > food preference > pick breakfast, lunch, dinner recipes > **Create Group**.
3. Copy the 6-letter group code.
4. Send the link and the code to your flatmates on WhatsApp.
5. They open the link, type their name, paste the code, click **Join Group**. Done.

Tip: on your phone, open the link in Chrome, tap the three dots menu > **Add to Home screen**. It now behaves like an app icon.

---

## "Will it run anytime?"

Yes, with one catch.

- The app runs on Streamlit's servers 24/7. Your laptop can be off.
- If **nobody opens the app for 12 hours**, Streamlit puts it to sleep to save resources.
- Whoever opens it next sees a "This app has gone to sleep" page. Tap **Yes, get this app back up!** Anyone can do this, not just you. It takes about 30 to 60 seconds.
- Your data is never lost. It lives in Firebase, not in the app.

For a flat that opens it every day, this happens at most once a morning. Not worth fixing.

---

## Option B: run on your own laptop (for testing or editing)

This works only while your laptop is on, and only you (or people on your Wi-Fi) can use it.

1. Install Python from https://www.python.org/downloads (on Windows, tick **Add Python to PATH**).
2. Put `app.py` and `requirements.txt` in a folder, e.g. `Desktop/meal-planner`.
3. Inside that folder, create a folder named `.streamlit`, and inside it a file named `secrets.toml` with the same content you pasted in Part 4.
4. Open Terminal (Mac) or Command Prompt (Windows), then:

```bash
cd Desktop/meal-planner
pip install -r requirements.txt
streamlit run app.py
```

5. Browser opens at `http://localhost:8501`.
6. To let flatmates on the same Wi-Fi use it: `streamlit run app.py --server.address 0.0.0.0`, then they open `http://<your-laptop-ip>:8501`.

Since both versions use the same Firebase, data you create locally also shows up on the hosted app.

---

## Updating the app later

Edit `app.py` on GitHub (pencil icon) and commit. Streamlit Cloud picks up the change automatically within a minute.

## If something breaks

| What you see | Likely cause | Fix |
|---|---|---|
| `KeyError: FIREBASE_JSON` or `firebase` | Secrets not saved | share.streamlit.io > your app > three dots > Settings > Secrets |
| `JSONDecodeError` | JSON pasted incompletely | Re-copy the whole file, including the first `{` and last `}` |
| `ModuleNotFoundError` | requirements.txt missing on GitHub | Upload it, then Reboot app |
| No "Try Something New" cards | Groq key missing or wrong | Check `GROQ_API_KEY` in secrets |
| Permission denied from Firestore | Wrong project's JSON key | Generate a new key from the correct Firebase project |

Full error details: on your app page, bottom right **Manage app** shows the logs.
