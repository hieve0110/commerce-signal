"""설정 로딩. 기본값은 config/poc.toml, 비밀값은 환경변수."""
from __future__ import annotations

import os
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "poc.toml"
KST = timezone(timedelta(hours=9))


def load_config(path: str | os.PathLike | None = None) -> dict:
    path = Path(path or os.environ.get("COMMERCE_SIGNAL_CONFIG", DEFAULT_CONFIG))
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    db_path = Path(cfg["storage"]["db_path"])
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    cfg["storage"]["db_path"] = str(db_path)
    return cfg


def today_kst() -> str:
    return datetime.now(KST).date().isoformat()


def slack_webhook_url() -> str:
    return os.environ.get("SLACK_WEBHOOK_URL", "")


def dashboard_url() -> str:
    return os.environ.get("DASHBOARD_URL", "")
