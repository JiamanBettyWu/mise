# Multi-user support: plan

**Status:** deferred — revisit after the "friend-ready" milestone (see below).
**Last updated:** 2026-09-08 (stale-doc sweep, [#167](https://github.com/JiamanBettyWu/mise/issues/167)).

> **What changed since the 2026-07-04 draft**, so the plan below can be trusted:
> RLS is now **enabled with zero policies** on every table (#161/#163) — the
> "RLS off" this doc originally described is no longer the starting state, and
> the migration sequence changes accordingly. Trip saving (#128), multi-item
> tagging (#24), usage metering (#114) and SSE streaming (#154) all shipped.
> Still open from the friend-ready list: the UI pass (#127) and the PWA shell
> (#126). Nothing here has been *re-decided* — Cut B still stands.

This is a planning doc, not a tracked issue. The work is big enough that it
shouldn't sit in the issue tracker until we're actually close to doing it.
When we are, this doc gets split into the actual sequence of issues/PRs.

---

## Goal

Let 3-5 friends use their own wardrobes in the same deployed app. Single-user
assumptions are baked into auth, DB schema, storage paths, and the daily-email
config — all need lifting.

## Decision: go straight to "Cut B," skip "Cut A"

There are two natural shapes:

- **Cut A** ("share with friends, low effort"): keep the shared-password model
  but make the password *per-user*; add `user_id` columns; rely on Python to put
  `.eq("user_id", ...)` on every query. ~1-2 days.
- **Cut B** ("real product"): Supabase Auth + JWT propagation + **RLS on** so
  Postgres enforces isolation, not application code. ~1-2 weeks.

**We're choosing Cut B.** Reasoning:

1. We don't have a real UI yet, so building the login screen *alongside* the
   rest of the UI is much cheaper than retrofitting it later.
2. Cut A leaves us with zero defense in depth — one forgotten `.eq("user_id")`
   on a query leaks everyone's wardrobe. Today's posture (**RLS on, zero
   policies**, service_role's `BYPASSRLS` carrying the app) is a deny-all wall
   against the public anon key, which is right for a single-tenant app — but it
   provides no *between-user* isolation at all, because there are no users to
   isolate. Multi-user needs real policies, not just the switch.
3. Cut A as a stepping stone tends to become permanent — we'd rather do the
   migration once.

## What changes (the surface area)

| Layer | Today | After |
|---|---|---|
| **Auth** | One shared `APP_PASSWORD` header (`backend/auth.py`) | Supabase Auth (email/magic-link); frontend stores JWT |
| **DB schema** | No `user_id` on any user-owned table (`clothing_items`, `outfit_history`, `preferences`, `profile`, `trip_plans`, `llm_usage` — the later migrations say so in a comment) | `user_id uuid not null references auth.users(id)` on every user-owned table |
| **Supabase access** | service_role key (`BYPASSRLS`); **RLS enabled, zero policies** on every table (#161/#163) — deny-all for the public anon key | User JWT for data calls; RLS **policies** (`auth.uid() = user_id`) on every table + storage bucket. The switch is already on; this step writes the rules |
| **Storage paths** | Flat (`services/storage.py`) | Scoped `{user_id}/{filename}`; bucket RLS matches |
| **Daily cron** | One `EMAIL_RECIPIENT`, one `recommend()` call | Loop over users; per-user opt-in + email address in a settings table |
| **Per-user prefs** | `preferences` table exists (#61/#62), single-tenant | Add `user_id`; weekly inference cron (#62) loops per user (multiplies its Claude calls by N — cheap, but budgeted) |
| **Calendar modes (#64)** | Single `CALENDAR_ICS_URL` Actions secret; presence = toggle | Nullable `calendar_ics_url` column on user settings (null = off for that user); cron reads per-user. NB: ICS URLs are secrets granting calendar read access — treat the column accordingly |
| **Feedback tokens (#39)** | Signed token assumes one recipient | Token payload carries `user_id` so friend A's emailed 👍/👎 link can't write verdicts attributed to friend B |
| **Usage metering (#114)** | `llm_usage` table, single-tenant | Add `user_id`; #115's stats dashboard becomes each user's transparency surface ("your usage cost $X this month") |

## Migration sequence (the order matters)

Do these as separate PRs, in this order:

1. **`users` and `user_preferences` tables** + add `user_id` columns to
   `clothing_items` and `outfit_history`. Backfill existing rows to Betty's
   user. RLS still off.
2. **Service-layer audit**: every Supabase query gets a `.eq("user_id", ...)`
   filter. Centralize in a `user_table()` helper so the audit surface is small.
3. **Storage scoping**: change upload paths to `{user_id}/{filename}` and write
   a migration script to move existing photos.
4. **Supabase Auth on the frontend**: login screen, token storage, attach JWT
   to `services/api.js`.
5. **Backend JWT propagation**: switch data-path Supabase calls to use the
   user's JWT instead of service_role. Keep service_role only for
   genuinely-admin operations (cron over all users, schema migrations).
6. **Write the RLS policies** — `auth.uid() = user_id` on every table and
   storage bucket. RLS itself is already enabled everywhere (#161/#163), so
   this step adds rules rather than flipping a switch; the moment a policy
   lands, service_role stops being the thing keeping queries working. **Do it
   last** — a policy plus a missing `user_id` on a row makes that row
   invisible to you, and you will think it's a bug. Easier to debug if
   isolation is the final change, not the first.
   NB: the convention from #163 is that every table-creating migration enables
   RLS in the same file, and `tests/test_sql_rls.py` fails CI otherwise — so
   the new `users` / `user_preferences` tables in step 1 carry the line from
   birth.
7. **Per-user style preferences** wired into the recommend/trip prompts.
   Small feature, big perceived "this feels like mine" win for new users.
8. **Daily-email job**: loop over users; honor per-user opt-in and email field.
   Includes user-scoped feedback tokens (#39) and the per-user
   `calendar_ics_url` column replacing the single Actions secret (#64).
9. **Onboarding flow** (see section below) — signup, 60-second profile,
   wardrobe upload with the catalog-readiness guardrail, first recommendation.
10. **Invite 1-2 friends as a soft launch**, then widen.

## Onboarding journey (added 2026-07-03)

Principle: **the app's differentiator is learning from behavior, so onboarding
collects the minimum to produce output #1 and lets the feedback loops do the
rest.** No style questionnaire — the preference-inference loop (#62) exists
precisely so preferences are learned from verdicts, not declared upfront.
Wardrobe upload is the real onboarding; everything else is form-filling kept
out of the way.

- **Step 0 — Invite + auth.** Invite code + magic link. One screen.
- **Step 1 — The 60-second profile.** Name, home location (drives weather),
  shopping department, daily-email opt-in. Four fields, one screen.
  Deliberately NOT here: calendar integration (highest-friction ask; lives in
  Settings, surfaced later as a "want smarter mornings?" prompt) and style
  preferences (one optional free-text box in Settings for the motivated).
- **Step 2 — Wardrobe upload**, framed as the activation goal ("add items to
  unlock your first recommendation"), leaning on multi-item tagging (#24).
- **Step 3 — First recommendation, same session.** Fire `POST /outfits/today`
  the moment the guardrail below clears — don't make them wait for tomorrow's
  cron. First impressions of an AI product are set by the first output.

### Catalog-readiness guardrail

Recommendations (both `POST /outfits/today` and the daily email) are **gated on
minimum per-category counts — at least N tops and M bottoms** (exact floors
TBD at implementation; start around 5 tops / 4 bottoms / 2 shoes and tune).
Below the floor, the API returns a structured "catalog not ready" response and
the UI shows progress ("3 of 5 tops added") instead of an outfit; the daily
job skips the user. Rationale: the recommender's per-category floors (#16)
assume a populated pool, and nobody's first impression should be the model
straining against a 4-item catalog. Count the **raw catalog**, not the
post-weather-gate pool (#18) — keep the guardrail simple and deterministic;
a hot day shrinking the effective pool shouldn't flip a user back to
"not ready".

## Cost (sanity check before inviting)

Anthropic is currently the only paid line. Rough math at Sonnet 4.x pricing
(~$3/MTok in, $15/MTok out):

| Call | Tokens (approx) | Cost/call |
|---|---|---|
| Daily outfit | ~3k in + ~1k out | ~$0.024 |
| Trip plan | ~4k in + ~1k out | ~$0.030 |
| Tag upload | ~1.5k in (image) + ~200 out | ~$0.007 |

5 active friends × 30 daily emails = ~$3.60/mo, plus trips and uploads.
Plausible ceiling **~$15-30/mo** for 5 friends. Eat it. If we ever need to
trim, the surgical move is to switch **only the tagging call** to Haiku —
single-image classification is the ideal Haiku use case. Keep Sonnet for
outfit reasoning.

**Before inviting anyone, replace this table with actuals from `llm_usage`**
(#114) — the estimates above pre-date measurement. As of 2026-09-08 the table
has ~2 months of real rows, so this is now a query rather than a wait. The
$3/$15 per-MTok figures still match `claude-sonnet-4-6`, the model the
recommender and trip planner use, but note the cheaper calls the estimates
omit entirely: Haiku query planning, the refine router, and mode
classification. Cached reads also make the daily call cheaper than the
sticker math suggests.

BYO API keys is technically easy (per-user `anthropic_api_key` column) but
adds enough signup friction that non-technical friends bounce. Not pursuing.

## What blocks this

We're deferring multi-user until the app is good enough that friends will
actually want to use it. The "friend-ready" milestone is:

- [x] **[#9](https://github.com/JiamanBettyWu/mise/issues/9)** — trip-planner crash on >5-day-out trips fixed in [PR #38](https://github.com/JiamanBettyWu/mise/pull/38)
- [x] **[#10](https://github.com/JiamanBettyWu/mise/issues/10)** — real purchase search shipped in [PR #80](https://github.com/JiamanBettyWu/mise/pull/80)
- [x] **[#81](https://github.com/JiamanBettyWu/mise/issues/81)** — purchase search now uses profile-aware planned queries in [PR #83](https://github.com/JiamanBettyWu/mise/pull/83)
- [x] **[#82](https://github.com/JiamanBettyWu/mise/issues/82)** — shopping department exposed in Profile UI
- [x] **[#2](https://github.com/JiamanBettyWu/mise/issues/2) easy wins** — START fan-out (PR #109), trimmed payload + Haiku query planning (PR #110), parallel gap searches (PR #108) all shipped. Remaining in #2 (progressive indicators, streaming) shipped later anyway as SSE node-progress for the trip planner, generate and refine (#154).
- [x] **Multi-item tagging** ([#24](https://github.com/JiamanBettyWu/mise/issues/24)) — shipped; onboarding Step 2 leans on it.
- [ ] **UI pass** on the 3 screens that matter (catalog, daily outfit, trip planner). Coherent, not pretty.
- [x] **[#114](https://github.com/JiamanBettyWu/mise/issues/114) accumulating data** — shipped 2026-07-03 and collecting since, so the cost table below can now be replaced with actuals. That replacement is still **to do**; it is the one piece of homework left on this list besides the UI pass.

Things deliberately *not* blockers:
- [#4](https://github.com/JiamanBettyWu/mise/issues/4) (prompt tuning) — needs real users to drive
- [#1](https://github.com/JiamanBettyWu/mise/issues/1), [#16](https://github.com/JiamanBettyWu/mise/issues/16), [#17](https://github.com/JiamanBettyWu/mise/issues/17), [#18](https://github.com/JiamanBettyWu/mise/issues/18) — polish, ship as we go

## Open questions for when we revisit

- **Auth method**: email/password vs magic link vs Google OAuth. Magic link is
  lowest friction but requires email infra we already have for daily-email.
  **Decided (2026-07-04): passwordless via Supabase Auth, but use the email
  OTP 6-digit code, not the clickable link** — a link opens in Safari's
  storage container, not the installed PWA's ([#126](https://github.com/JiamanBettyWu/mise/issues/126)),
  leaving the app logged out; the typed code lands in whichever window asked.
  (Can offer both: link for desktop, code for the installed app.)
- **Invitation flow**: open signup vs invite codes? For 5 friends, invite codes
  are simpler and bound the cost surface.
- **Settings UI scope**: minimum is email opt-in + style notes. Could extend
  to favorite colors, banned items, formality lean — but every field is a new
  UI surface, so start narrow.
