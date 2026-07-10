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
| `WEATHER_LAT` | e.g. `40.71` |
| `WEATHER_LON` | e.g. `-74.01` |
| `GMAIL_SENDER` | `you@example.com` |
| `GMAIL_APP_PASSWORD` | 16-char app password from step 1 |
| `EMAIL_RECIPIENT` | `you@example.com` |
| `FEEDBACK_SECRET` | any long random string — **must match the same secret in `.env` and Render** (signs the 👍/👎 links; Render verifies them) |
| `BACKEND_PUBLIC_URL` | `https://<your-render-app>.onrender.com` — base URL the job builds feedback links against |
| `CALENDAR_ICS_URL` | *(optional, #64)* Google Calendar "secret address in iCal format" URL. **Presence of this secret is the toggle** — set it to make the day's modes calendar-driven; leave it unset for the hardcoded three modes |

⚠️ Paste each value with no trailing newline (same gotcha that hit us on Render).
⚠️ `FEEDBACK_SECRET` lives in **three places** (repo-root `.env`, Render, and
here in Actions). The job *signs* tokens on the Actions runner; Render only
*verifies* — a mismatch makes every emailed link 400.

## 3. Test it manually

Go to your GitHub repo → **Actions** tab → **Daily outfit email** workflow → **Run workflow** (top right).

- Leave "Force" checked → it bypasses the time check and sends immediately.
- Watch the run; the final step should print `[done] sent 3 outfits to ...`.
- Check your inbox.

## 4. Wait for the scheduled run

Once manual works, the schedule kicks in automatically:
- The workflow fires **once a day** on a single cron line: `20 8 * * *` (08:20
  UTC). There is **no hour-check guard** — every scheduled fire sends one email.
- The time is deliberately offset early because GitHub's scheduled runs are
  best-effort and routinely delayed 1–3h; the email tends to land ~5:30–7:45am
  ET. The `:20` minute dodges `:00`, the platform's most congested slot.

## Caveats

- GitHub Actions schedules are **best effort** and can drift 1–3h late — which
  is exactly why the cron is offset early with no exact-hour guard. For a
  personal morning email, that's fine.
- To change the send time, edit the `cron:` line in
  [.github/workflows/daily-outfit.yml](../.github/workflows/daily-outfit.yml)
  (remember it's UTC, and pad early for the delay).
- If the email lands in spam: open it, "Mark as not spam", and Gmail will trust the sender for future messages (since you're sending to yourself, this should stick fast).
- A second cron, **Weekly preference inference** ([.github/workflows/infer-preferences.yml](../.github/workflows/infer-preferences.yml), #62), runs Sunday nights and needs **no new secrets** — it reuses `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `ANTHROPIC_API_KEY` from the table above. Trigger it the same way (Actions tab → Run workflow) to test.
