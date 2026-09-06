"""Persistent, local configuration for the ``studio`` command."""

from __future__ import annotations

import getpass
import json
import os
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from . import crypto


CONFIG_DIR = Path(
    os.environ.get("UPLOADER_LEGACY_CONFIG_DIR", "~/.config/uploader-legacy")
).expanduser()
CONFIG_PATH = CONFIG_DIR / "config.json"
BUNDLED_DSN_PATH = files("uploader_legacy").joinpath("production_dsn.enc")


@dataclass
class Config:
    dsn: str = ""


def load() -> Config:
    """Load the saved DSN, preferring an explicitly supplied environment value."""
    env_dsn = os.environ.get("DSN", "").strip()
    if env_dsn:
        return Config(dsn=env_dsn)

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return Config()
    return Config(dsn=str(data.get("dsn", "")).strip())


def save(config: Config) -> None:
    """Save secrets atomically in a directory and file restricted to the owner."""
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass

    fd, temp_name = tempfile.mkstemp(prefix="config.", dir=CONFIG_DIR)
    try:
        # fchmod is unavailable on Windows; chmod still prevents accidental
        # exposure on POSIX systems and keeps the write path portable.
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"dsn": config.dsn}, handle, indent=2)
            handle.write("\n")
        os.replace(temp_name, CONFIG_PATH)
        try:
            os.chmod(CONFIG_PATH, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def prompt_and_save(validate: Callable[[str], None] | None = None) -> Config:
    """Ask for a DSN, optionally validate it, then persist it."""
    print("No database configuration found.")
    print("The DSN is saved locally with owner-only permissions where supported.")
    while True:
        try:
            dsn = getpass.getpass("Postgres DSN: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("No DSN was entered; setup cancelled.") from None
        if not dsn:
            print("A Postgres DSN is required.")
            continue
        candidate = Config(dsn=dsn)
        if validate is not None:
            try:
                validate(candidate.dsn)
            except Exception:
                print("Could not connect using that DSN. Check it and try again.")
                continue
        save(candidate)
        print(f"Configuration saved to {CONFIG_PATH}")
        return candidate


def prompt_encrypted_and_save(validate: Callable[[str], None] | None = None) -> Config:
    """Unlock the bundled DSN, validate it, and save it locally."""
    payload = crypto.load_payload(BUNDLED_DSN_PATH)
    if payload is None:
        return prompt_and_save(validate=validate)

    print("An encrypted database configuration is bundled with this tool.")
    print("The passphrase is not stored locally or sent to the database.")
    while True:
        try:
            passphrase = getpass.getpass("DSN passphrase: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("No passphrase was entered; setup cancelled.") from None
        try:
            dsn = crypto.decrypt_dsn(payload, passphrase)
        except ValueError as exc:
            print(str(exc))
            continue
        if validate is not None:
            try:
                validate(dsn)
            except Exception:
                print("The unlocked DSN could not connect. Check network access and try again.")
                continue
        candidate = Config(dsn=dsn)
        save(candidate)
        print(f"Configuration saved to {CONFIG_PATH}")
        return candidate


def ensure(validate: Callable[[str], None] | None = None) -> Config:
    config = load()
    return config if config.dsn else prompt_encrypted_and_save(validate=validate)


def redacted_dsn(dsn: str) -> str:
    """Return a display-safe DSN without credentials."""
    if not dsn:
        return "(not configured)"
    try:
        parsed = urlsplit(dsn)
        if not parsed.scheme or not parsed.hostname:
            return "(configured; credentials hidden)"
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parsed.port:
            host = f"{host}:{parsed.port}"
        user = parsed.username
        netloc = f"{user}:***@{host}" if user else host
        # Do not retain query parameters: DSNs commonly put passwords or
        # cloud-provider tokens there even when the URI has no userinfo.
        return f"{parsed.scheme}://{netloc}{parsed.path}"
    except ValueError:
        return "(configured; credentials hidden)"
