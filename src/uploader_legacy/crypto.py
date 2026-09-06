"""Password-based authenticated encryption for the optional bundled DSN."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


FORMAT_VERSION = 1
ASSOCIATED_DATA = b"uploader-legacy-production-dsn-v1"
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64_decode(value: Any) -> bytes:
    if not isinstance(value, str):
        raise ValueError("encrypted DSN payload is malformed")
    try:
        return base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("encrypted DSN payload is malformed") from exc


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if not passphrase:
        raise ValueError("a passphrase is required")
    return Scrypt(
        salt=salt,
        length=KEY_BYTES,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    ).derive(passphrase.encode("utf-8"))


def encrypt_dsn(dsn: str, passphrase: str) -> dict[str, Any]:
    """Encrypt a DSN using scrypt-derived AES-256-GCM."""
    if not dsn.strip():
        raise ValueError("a DSN is required")
    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    key = _derive_key(passphrase, salt)
    ciphertext = AESGCM(key).encrypt(nonce, dsn.encode("utf-8"), ASSOCIATED_DATA)
    return {
        "version": FORMAT_VERSION,
        "kdf": "scrypt",
        "salt": _b64_encode(salt),
        "nonce": _b64_encode(nonce),
        "ciphertext": _b64_encode(ciphertext),
    }


def decrypt_dsn(payload: dict[str, Any], passphrase: str) -> str:
    """Decrypt and authenticate a bundled DSN, without exposing it in errors."""
    if payload.get("version") != FORMAT_VERSION or payload.get("kdf") != "scrypt":
        raise ValueError("encrypted DSN payload uses an unsupported format")
    salt = _b64_decode(payload.get("salt"))
    nonce = _b64_decode(payload.get("nonce"))
    ciphertext = _b64_decode(payload.get("ciphertext"))
    if len(salt) != SALT_BYTES or len(nonce) != NONCE_BYTES or len(ciphertext) < 16:
        raise ValueError("encrypted DSN payload is malformed")
    try:
        key = _derive_key(passphrase, salt)
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, ASSOCIATED_DATA)
    except (InvalidTag, ValueError) as exc:
        raise ValueError("could not unlock the encrypted DSN; check the passphrase") from exc
    try:
        dsn = plaintext.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("encrypted DSN payload is invalid") from exc
    if not dsn:
        raise ValueError("encrypted DSN payload is empty")
    return dsn


def load_payload(path) -> dict[str, Any] | None:
    """Read a payload from disk; missing payloads mean direct DSN setup."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
