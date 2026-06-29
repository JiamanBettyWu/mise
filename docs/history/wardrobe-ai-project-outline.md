> ⚠️ **Historical document.** This is the original project outline from before
> the app was built. It is kept as a record of the initial vision and no longer
> reflects the current architecture (e.g. the daily job runs on GitHub Actions,
> not Render Cron; calendar logic is a service, not a router). For how the
> system actually works today, see [AGENTS.md](../../AGENTS.md) and the design
> records under [docs/](../).

# Wardrobe AI — Project Outline

## What This App Does
A personal wardrobe catalog that recommends daily outfits based on the weather and your calendar. You upload photos of your clothes once; AI auto-tags them. Every morning, you get an outfit suggestion by email. A React web app lets you browse your catalog and manage items (including marking things as in the laundry).

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Frontend | React + Vite | Good UI, you have exposure, deploys easily |
| Backend | FastAPI (Python) | You know Python; clean API framework |
| Database + Storage | Supabase | Free tier, handles both records and photo storage |
| AI — tagging + recommendations | Claude API | Vision for one-time tagging; text for daily recommendations |
| Weather | OpenWeatherMap API | Free tier, simple |
| Calendar | iCloud → Google Calendar sync (one-time setup) | Easiest path; no code required |
| Frontend hosting | Vercel | Free, deploys on every git push |
| Backend hosting | Render | Free tier, acceptable for this use case |
| Daily job | Render Cron Jobs | Triggers 7am email, free |

---

## Repo Structure

```
wardrobe-ai/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── routers/
│   │   ├── clothes.py           # Add, edit, delete, list clothing items
│   │   ├── outfits.py           # Generate outfit recommendations
│   │   └── calendar.py          # Fetch today's calendar events
│   ├── services/
│   │   ├── claude.py            # Claude API: photo tagging + outfit recommendations
│   │   ├── weather.py           # OpenWeatherMap API
│   │   └── email.py             # Send daily outfit email
│   ├── db/
│   │   └── supabase.py          # Supabase client setup
│   ├── schemas.py               # Pydantic models (what a ClothingItem looks like, etc.)
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ClothingCard.jsx      # Single item: photo + tags + availability toggle
│   │   │   ├── AddClothingForm.jsx   # Upload photo, review/edit AI tags, save
│   │   │   ├── OutfitSuggestion.jsx  # Display today's outfit recommendation
│   │   │   └── FilterBar.jsx         # Filter catalog by type, season, etc.
│   │   ├── pages/
│   │   │   ├── Catalog.jsx           # Browse all clothes
│   │   │   ├── AddItem.jsx           # Add new clothing item
│   │   │   └── TodayOutfit.jsx       # Today's outfit suggestion + reasoning
│   │   ├── services/
│   │   │   └── api.js                # All calls to the FastAPI backend
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
│
├── jobs/
│   └── daily_outfit.py          # Standalone script: fetch weather + calendar,
│                                #   call Claude, send email. Run by Render Cron.
│
├── .env.example                 # Template for required environment variables
├── .gitignore
└── README.md
```

---

## Data Model

A single `clothing_items` table in Supabase:

| Field | Type | Notes |
|---|---|---|
| id | UUID | Auto-generated |
| name | text | e.g. "Navy wool blazer" |
| type | text | e.g. jacket, shirt, trousers, shoes |
| color | text | e.g. "navy blue" |
| formality | text | casual / smart-casual / formal |
| season | text | spring, summer, fall, winter, all-season |
| fabric | text | e.g. wool, cotton, linen |
| photo_url | text | Points to Supabase Storage |
| available | boolean | false = in laundry or unavailable |
| in_travel_bag | boolean | true = packed for current trip (default false) |
| notes | text | Optional free-text for anything AI missed |
| created_at | timestamp | Auto-generated |

---

## Build Order

Build in this sequence so you have something usable as early as possible, and never get blocked waiting on another piece.

### Phase 1 — Foundation (Weekend 1, Part 1)
*Goal: the skeleton is wired up end-to-end, nothing is functional yet but all pieces talk to each other.*

- [ ] Create repo, set up `/backend` and `/frontend` folders
- [ ] Stand up FastAPI with a single `/health` endpoint
- [ ] Create Supabase project, create `clothing_items` table
- [ ] Connect FastAPI to Supabase
- [ ] Create React app with Vite, call `/health` and display response
- [ ] Set up `.env` for API keys (Supabase, Claude, OpenWeatherMap)
- [ ] Deploy backend to Render, frontend to Vercel

### Phase 2 — Clothing Catalog (Weekend 1, Part 2 + Weekend 2, Part 1)
*Goal: you can add, view, and edit your clothes. This is the core of the app.*

- [ ] `POST /clothes` — upload photo to Supabase Storage, send photo to Claude for tag generation, return suggested tags
- [ ] `AddClothingForm` — photo upload UI, display AI-generated tags in editable form fields, save button
- [ ] `GET /clothes` — return all clothing items
- [ ] `Catalog` page — grid of `ClothingCard` components with photo + tags
- [ ] `PATCH /clothes/{id}` — edit tags or toggle availability
- [ ] Availability toggle ("in laundry") on each `ClothingCard`
- [ ] Start cataloging your actual clothes 📸

### Phase 3 — Outfit Recommendations (Weekend 2, Part 2)
*Goal: the app can suggest an outfit given weather and calendar context.*

- [ ] Wire up OpenWeatherMap API in `weather.py`
- [ ] Wire up Google Calendar API in `calendar.py` (after iCloud → Google sync setup)
- [ ] `POST /outfits/recommend` — fetches weather + calendar, pulls all available clothes from DB, calls Claude with text descriptions, returns 2-3 outfit suggestions with reasoning
- [ ] `TodayOutfit` page — displays suggestions with photos and Claude's reasoning

### Phase 4 — Daily Email Job (Weekend 3, Part 1)
*Goal: you receive an outfit suggestion every morning without opening the app.*

- [ ] Write `jobs/daily_outfit.py` — standalone script that runs the recommendation and sends an email
- [ ] Set up email sending (SendGrid free tier, or Gmail SMTP)
- [ ] Configure Render Cron Job to run the script at 7am
- [ ] Test end-to-end

### Phase 5 — Polish (Weekend 3, Part 2 and beyond)
*Nice-to-haves once the core is working.*

- [ ] Filter/search catalog by type, season, color
- [ ] "Recently worn" tracking
- [ ] Outfit history log
- [ ] Mobile UI refinements
- [ ] Multiple outfit options to swipe through
- [ ] **Travel mode** — "Pack" button on each ClothingCard to toggle `in_travel_bag`; Travel Mode toggle on Catalog/Today's Outfit page; recommendations filter to `available = true AND in_travel_bag = true` when active; "Clear all" button to unpack when you get home

---

## Key Environment Variables

```
# Backend (.env)
SUPABASE_URL=
SUPABASE_KEY=
ANTHROPIC_API_KEY=
OPENWEATHERMAP_API_KEY=
GOOGLE_CALENDAR_API_KEY=
EMAIL_SENDER=
EMAIL_RECIPIENT=

# Frontend (.env)
VITE_API_BASE_URL=https://your-render-app.onrender.com
```

---

## Cost Summary (at steady state)

| Service | Monthly Cost |
|---|---|
| Supabase | Free |
| Render (backend) | Free |
| Vercel (frontend) | Free |
| OpenWeatherMap | Free |
| Claude API (daily recommendations + ~100 one-time photo tags) | ~$1–2/month |
| **Total** | **~$1–2/month** |

---

## What's Explicitly Out of Scope for V1

- Native iOS/Android app (phone browser is fine)
- Multiple users
- Outfit history / "don't repeat outfits"
- Full-body outfit preview / virtual try-on
- Purchasing recommendations
