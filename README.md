# Meal Planner v3: what changed and how to update

## What's new

| # | Change |
|---|---|
| 1 | Dark mode fixed. All custom colours removed; cards are native Streamlit boxes that follow the phone's light/dark setting. Mint accent colour in both modes. |
| 2 | Up to 10 "From your kitchen" options per meal, inside a scrollable box. Anything logged in the last 7 days is skipped. AI ranks the list for the day (variety vs yesterday, quick on weekdays, elaborate on weekends). |
| 3 | Mint leaf 🌿 in the browser tab, page titles and sidebar. Upload a `logo.png` to use a real image instead. |
| 4 | AI fixed (the old model was shut down by Groq on 16 Aug 2026). Now uses `openai/gpt-oss-20b`. "Try something new" shows up to 2 cookbook picks + 2 AI ideas. Errors are shown on screen instead of failing silently. |
| 5 | Recipes added by anyone now appear on today's vote immediately (tagged "added by ..."). Each meal also has "Add an option to today's vote". The sidebar now tells you exactly what happened when a recipe already exists. |
| 6 | New Calendar page: pick any day in the last 90 days, record breakfast/lunch/dinner and who cooked. Feeds future suggestions. Includes a 14-day table and stats. |
| Also | "Today" is now Indian time (Streamlit servers run on UTC, so before 5:30 AM the app used to think it was yesterday). |

## v4 additions

| Change | Detail |
|---|---|
| Quick / elaborate toggle | At the top of the menu. Off = dishes up to 30 min, on = longer dishes. Shared by the whole group for that day. Switching re-plans meals not yet logged and resets their votes. |
| Cooking-time defaults | New onboarding step asks what the group prefers on weekdays and weekends. Existing groups default to quick on weekdays, elaborate on weekends; change it in the sidebar under "Cooking-time defaults". |
| 4 new ideas per meal | Aim is 2 cookbook picks + 2 AI ideas. If one side has fewer, the other fills the gap. |
| Cookbook times | Estimated from timings written in each recipe's method, plus 10 min prep. Shown with "~". 142 of 199 recipes have one; they tend to run low. |
| Quick guide | Opens once for each person the first time they enter a group. Reopen anytime from the sidebar. Also on the landing page under "New here?". |

## How to update (10 min)

Your Firebase data stays as it is. Nothing to redo.

1. Open your GitHub repo.
2. Replace `app.py` and `requirements.txt` with the new versions: click the file > pencil icon > select all > paste > Commit. Or **Add file > Upload files** and drop the new files in (same names overwrite).
3. Upload `cookbook.json` (empty for now).
4. Create the theme file: **Add file > Create new file**. In the name box type exactly `.streamlit/config.toml` (typing the `/` creates the folder). Paste the contents of `config.toml`. Commit.
5. Optional: **Add file > Upload files** > `logo.png` (a square mint-leaf PNG, 256x256 or bigger).
6. Go to share.streamlit.io > your app > three dots > **Reboot app**.
7. Check Secrets (three dots > Settings > Secrets) still contain `GROQ_API_KEY` and `FIREBASE_JSON`. Nothing new is required. Optional extras:

```toml
GROQ_MODEL = "openai/gpt-oss-20b"   # change here if Groq retires this one too
TIMEZONE = "Asia/Kolkata"
```

## Checks after updating

- Open on your phone in dark mode: all text should be readable.
- The AI status line in the sidebar should say "AI suggestions on".
- Breakfast should show up to 10 kitchen options in a box you can scroll inside.
- Today's suggestions are rebuilt once automatically with the new logic. Votes already cast today may need to be redone; tap "Refresh suggestions" on a meal if anything looks off.

If the app does not switch with your phone's dark mode, delete `.streamlit/config.toml` from GitHub and reboot. You can always switch manually: three dots (top right of the app) > Settings > Theme.

## Cookbook format

`cookbook.json` holds a list of recipes. The app filters them by the group's diet and meal, skips anything the group already has or ate this week, and the AI picks the best 2.

```json
{
  "recipes": [
    {
      "name": "Rava Idli",
      "meal_types": ["Breakfast"],
      "diet": "veg",
      "ingredients": "semolina, curd, mustard seeds, curry leaves",
      "prep_time": "25 min"
    }
  ]
}
```

- `diet`: `veg`, `eggetarian` or `non-veg`
- `meal_types`: any of `Breakfast`, `Lunch`, `Dinner`

## Free limits (Groq, gpt-oss-20b)

30 requests/minute, 1,000/day, 8,000 tokens/minute. The app makes 1 AI call per group per day, plus 1 per "Refresh suggestions" tap. If you tap refresh rapidly you may see "Groq's free limit is busy"; wait a minute.

## Troubleshooting

| Message | Fix |
|---|---|
| "AI is off: add GROQ_API_KEY" | Add the key in Secrets, reboot |
| "The Groq key is invalid" | Make a new key at console.groq.com, update Secrets |
| "The AI model ... is not available" | Pick a current model at console.groq.com/docs/models, set `GROQ_MODEL` in Secrets |
| "Groq's free limit is busy" | Wait 1 minute, tap Refresh suggestions |
| Any red error box | Manage app (bottom right) > copy the log and send it over |
