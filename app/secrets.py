from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
VAULT_PATH = DATA_DIR / "vault.enc"


def _fernet() -> Fernet:
    key = os.getenv("APP_SECRET", "").strip()
    if not key:
        raise RuntimeError("APP_SECRET must be configured")
    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise RuntimeError("APP_SECRET must be a valid Fernet key") from exc


def save_secrets(values: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(values, separators=(",", ":")).encode("utf-8")
    tmp = VAULT_PATH.with_suffix(".tmp")
    tmp.write_bytes(_fernet().encrypt(payload))
    os.replace(tmp, VAULT_PATH)
    try:
        os.chmod(VAULT_PATH, 0o600)
    except OSError:
        pass


def has_secrets() -> bool:
    return VAULT_PATH.exists()


def load_secrets() -> dict[str, str]:
    if not VAULT_PATH.exists():
        return {}
    data = _fernet().decrypt(VAULT_PATH.read_bytes())
    return json.loads(data.decode("utf-8"))


def factory_reset() -> None:
    # Permanently remove the encrypted credential vault. The next setup starts empty.
    if VAULT_PATH.exists():
        VAULT_PATH.unlink()
