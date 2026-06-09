"""
Application configuration.

All tunables are read from environment variables with sensible defaults.
Seed data (users, assets) is loaded once at import time from data/seed.json.
"""
import json
import os
from pathlib import Path

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
DB_PATH = os.environ.get("DB_PATH", "jobs.db")
PORT = int(os.environ.get("PORT", "8000"))
SEED_PATH = os.environ.get(
    "SEED_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "seed.json"),
)

_seed = json.loads(Path(SEED_PATH).read_text())

USERS_BY_TOKEN: dict[str, dict] = {u["token"]: u for u in _seed["users"]}
VALID_ASSETS: set[str] = {a["asset_id"] for a in _seed["assets"]}
