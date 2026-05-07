import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth import require_password
from db.supabase import client as supabase

load_dotenv()

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
