# Wardrobe AI

Personal wardrobe catalog with AI-tagged photos and a daily outfit-by-email job.
See [wardrobe-ai-project-outline.md](wardrobe-ai-project-outline.md) for the full spec.

## Local development

### Backend
```bash
cd backend
uv sync
cp ../.env.example .env   # fill in values
uv run uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev
```

Open http://localhost:5173 and enter your `APP_PASSWORD` to unlock the UI.

## Deployment

- **Backend:** Render (config in [render.yaml](render.yaml)).
- **Frontend:** Vercel (config in [vercel.json](vercel.json), root = `frontend/`).
- **Daily email cron:** Render Cron Job, also defined in `render.yaml`.

See [docs/deploy.md](docs/deploy.md) for the env-var checklist.

## Repo layout

```
backend/    FastAPI app + services
frontend/   React + Vite UI
jobs/       Standalone scripts (daily email)
docs/       Setup notes
```
