"""Staff PIN. Stored as a salted PBKDF2 hash, never in plain text.

This is a basic gate for a prototype. It is not a full user system, and it does
not limit repeated guesses beyond what the app itself enforces.
"""
import hashlib
import hmac
import os

import config as cfg
from services.base import execute, fetch_one
from services.errors import ValidationError

ITERATIONS = 200_000


def _digest(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, ITERATIONS)


def pin_is_set(conn):
    return fetch_one(conn, "SELECT value FROM app_settings WHERE key = 'staff_pin'") is not None


def set_staff_pin(conn, pin):
    pin = str(pin or "")
    if len(pin) < cfg.MIN_STAFF_PIN_LENGTH:
        raise ValidationError(f"The staff PIN must be at least {cfg.MIN_STAFF_PIN_LENGTH} characters.")
    salt = os.urandom(16)
    stored = salt.hex() + ":" + _digest(pin, salt).hex()
    execute(conn,
            "INSERT INTO app_settings (key, value) VALUES ('staff_pin', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (stored,))


def verify_staff_pin(conn, pin):
    row = fetch_one(conn, "SELECT value FROM app_settings WHERE key = 'staff_pin'")
    if row is None:
        return False
    salt_hex, digest_hex = row["value"].split(":")
    candidate = _digest(str(pin or ""), bytes.fromhex(salt_hex)).hex()
    return hmac.compare_digest(candidate, digest_hex)
