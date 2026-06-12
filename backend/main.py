import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth import require_password
from db.supabase import client as supabase
from routers import clothes, feedback, geo, outfits, profile, trips

# Load the single repo-root .env regardless of cwd. See ENV setup in README.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# The app's diagnostic logs (candidate pool, #63 rejection reasons) are INFO;
# without a root handler at INFO, Python's last-resort handler shows only
# WARNING+. Uvicorn's own loggers keep their handlers (propagate=False).
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Wardrobe AI")

allowed_origins = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(clothes.router)
app.include_router(outfits.router)
app.include_router(trips.router)
app.include_router(geo.router)
app.include_router(profile.router)
app.include_router(feedback.router)  # token-authed, not password-gated


@app.get("/health")
def health():
    """Public health check — pings Supabase to confirm wiring."""
    supabase_ok: bool
    detail: str | None = None
    try:
        supabase().table("clothing_items").select("id").limit(1).execute()
        supabase_ok = True
    except Exception as e:
        supabase_ok = False
        detail = str(e)
    return {"ok": True, "supabase": supabase_ok, "detail": detail}


@app.get("/health/auth", dependencies=[Depends(require_password)])
def health_auth():
    """Confirms the password header is wired up correctly."""
    return {"ok": True, "authenticated": True}
