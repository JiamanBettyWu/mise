# Multi-user support: plan

**Status:** deferred — revisit after the "friend-ready" milestone (see below).
**Last updated:** 2026-06-03.

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
   on a query leaks everyone's wardrobe. RLS-off + service_role is the right
   posture for a single-user app and the wrong posture for any multi-user one.
3. Cut A as a stepping stone tends to become permanent — we'd rather do the
   migration once.

## What changes (the surface area)

| Layer | Today | After |
|---|---|---|
| **Auth** | One shared `APP_PASSWORD` header (`backend/auth.py`) | Supabase Auth (email/magic-link); frontend stores JWT |
| **DB schema** | No `user_id` on `clothing_items` or `outfit_history` | `user_id uuid not null references auth.users(id)` on every user-owned table |
| **Supabase access** | service_role key, RLS off | User JWT for data calls; RLS policies (`auth.uid() = user_id`) on every table + storage bucket |
| **Storage paths** | Flat (`services/storage.py`) | Scoped `{user_id}/{filename}`; bucket RLS matches |
| **Daily cron** | One `EMAIL_RECIPIENT`, one `recommend()` call | Loop over users; per-user opt-in + email address in a settings table |
| **Per-user prefs** | None | Style notes + structured prefs spliced into Claude system prompts |

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
6. **Flip on RLS** with `auth.uid() = user_id` policies on every table and
   storage bucket. **Do this last** — RLS-on with a missing `user_id` on a row
   makes that row invisible to you and you'll think it's a bug. Easier to
   debug if isolation is the final flip, not the first one.
7. **Per-user style preferences** wired into the recommend/trip prompts.
   Small feature, big perceived "this feels like mine" win for new users.
8. **Daily-email job**: loop over users; honor per-user opt-in and email field.
9. **Invite 1-2 friends as a soft launch**, then widen.

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

BYO API keys is technically easy (per-user `anthropic_api_key` column) but
adds enough signup friction that non-technical friends bounce. Not pursuing.

## What blocks this

We're deferring multi-user until the app is good enough that friends will
actually want to use it. The "friend-ready" milestone is:

- [ ] **[#9](https://github.com/JiamanBettyWu/wardrobe-ai/issues/9)** — trip-planner crash on >5-day-out trips
- [ ] **[#10](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10)** — real purchase search (stub data lies to users)
- [ ] **[#2](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2) easy wins** — parallel weather/catalog, trim payload, progressive UI indicators. Skip streaming for v1.
- [ ] **UI pass** on the 3 screens that matter (catalog, daily outfit, trip planner). Coherent, not pretty.
- [ ] **Multi-item tagging** ([#24](https://github.com/JiamanBettyWu/wardrobe-ai/issues/24)) — quality-of-life win that should ship before friends arrive.

Things deliberately *not* blockers:
- [#4](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4) (prompt tuning) — needs real users to drive
- [#1](https://github.com/JiamanBettyWu/wardrobe-ai/issues/1), [#16](https://github.com/JiamanBettyWu/wardrobe-ai/issues/16), [#17](https://github.com/JiamanBettyWu/wardrobe-ai/issues/17), [#18](https://github.com/JiamanBettyWu/wardrobe-ai/issues/18) — polish, ship as we go

## Open questions for when we revisit

- **Auth method**: email/password vs magic link vs Google OAuth. Magic link is
  lowest friction but requires email infra we already have for daily-email.
- **Invitation flow**: open signup vs invite codes? For 5 friends, invite codes
  are simpler and bound the cost surface.
- **Settings UI scope**: minimum is email opt-in + style notes. Could extend
  to favorite colors, banned items, formality lean — but every field is a new
  UI surface, so start narrow.
