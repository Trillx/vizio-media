"""Local owner sessions, profile PINs, and authenticated credential encryption."""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000)
    return f"pbkdf2-sha256$600000${salt}${digest.hex()}"


def check_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        _, iterations, salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Vault:
    def __init__(self, directory: Path, *, require_existing: bool = False):
        directory.mkdir(parents=True, exist_ok=True)
        key_path = directory / "vault.key"
        if require_existing and not key_path.is_file():
            raise RuntimeError("Credential key is missing. Restore the matching data/vault.key backup before starting.")
        try:
            descriptor = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as target:
                target.write(Fernet.generate_key())
        self.cipher = Fernet(key_path.read_bytes())

    def seal(self, payload: dict) -> str:
        return self.cipher.encrypt(json.dumps(payload).encode()).decode()

    def open(self, sealed: str | None) -> dict:
        if not sealed:
            return {}
        try:
            return json.loads(self.cipher.decrypt(sealed.encode()))
        except (InvalidToken, ValueError):
            raise RuntimeError("Stored credentials cannot be decrypted. Restore the matching vault.key backup.") from None


class LoginLimiter:
    """Bounded attempt counts; no tokens, PINs, or passwords are retained."""
    def __init__(self):
        self.entries: dict[str, tuple[float, int]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        with self.lock:
            now = time.time()
            self.entries = {k: v for k,v in self.entries.items() if now-v[0]<60}
            start, count = self.entries.get(key, (now,0))
            if count >= 5:
                return False
            self.entries[key] = (start,count+1)
            return True

    def clear(self, key: str):
        with self.lock:
            self.entries.pop(key, None)
