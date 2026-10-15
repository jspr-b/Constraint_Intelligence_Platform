"""Station PINs: stored only as a salted scrypt hash (stdlib, no extra dependency)."""

import hashlib
import hmac
import re
import secrets

N, R, P = 2**14, 8, 1
PIN = re.compile(r"^\d{4,8}$")


def valid_pin(pin: str) -> bool:
    return bool(PIN.fullmatch(pin))


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=N, r=R, p=P)
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(candidate.hex(), digest)
