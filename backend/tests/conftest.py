"""Shared pytest setup for the backend suite.

Owns the two things every former test script repeated: making `services`,
`db`, `schemas` importable, and loading the single repo-root .env (see
AGENTS.md — never a backend/.env). Only the RUN_E2E=1 tests actually need
the env values; loading them is harmless offline.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

load_dotenv(BACKEND.parent / ".env")
