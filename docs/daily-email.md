# Phase 4 — daily email setup

## 1. Get a Gmail App Password

A regular Gmail password won't work for SMTP. You need a one-off "app password".

1. Google Account → **Security** → enable **2-Step Verification** if not already on.
2. Visit [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Create one named "Wardrobe AI". Copy the 16-character password.

## 2. Add GitHub repo secrets

GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.

Add each of these (paste values from your local `.env`):

| Secret | Value |
|---|---|
| `SUPABASE_URL` | `https://<project>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | (long jwt) |
| `ANTHROPIC_API_KEY` | `sk-ant-...` |
| `OPENWEATHERMAP_API_KEY` | (32-char hex) |
| `WEATHER_LAT` | e.g. `38.92` |
| `WEATHER_LON` | e.g. `-77.23` |
| `GMAIL_SENDER` | `jiaman.betty.wu@gmail.com` |
| `GMAIL_APP_PASSWORD` | 16-char app password from step 1 |
| `EMAIL_RECIPIENT` | `jiaman.betty.wu@gmail.com` |

⚠️ Paste each value with no trailing newline (same gotcha that hit us on Render).

## 3. Test it manually

Go to your GitHub repo → **Actions** tab → **Daily outfit email** workflow → **Run workflow** (top right).

- Leave "Force" checked → it bypasses the time check and sends immediately.
- Watch the run; the final step should print `[done] sent 3 outfits to ...`.
- Check your inbox.

## 4. Wait for the scheduled run

Once manual works, the schedule kicks in automatically:
- Workflow fires at **11:00 UTC** and **12:00 UTC** every day.
- The Python script checks the current hour in `America/New_York`. Whichever fire lands at 7am ET sends; the other no-ops.
- DST is handled automatically: 11:00 UTC = 7am EDT (summer), 12:00 UTC = 7am EST (winter).

## Caveats

- GitHub Actions schedules are **best effort**. Real fire time can drift ~5–15 min late. For a personal morning email, that's fine.
- If you want to change the recipient timezone, edit `TZ` in [jobs/daily_outfit.py](../jobs/daily_outfit.py) and adjust the cron times in [.github/workflows/daily-outfit.yml](../.github/workflows/daily-outfit.yml).
- If the email lands in spam: open it, "Mark as not spam", and Gmail will trust the sender for future messages (since you're sending to yourself, this should stick fast).
