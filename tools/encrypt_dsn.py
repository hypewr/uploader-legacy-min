#!/usr/bin/env python3
"""Create the encrypted payload used by the standalone package.

Usage: read exactly one DSN from stdin and write the payload to the requested
path. The DSN and passphrase are never printed.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import tempfile
from pathlib import Path

from uploader_legacy.crypto import encrypt_dsn


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--passphrase-file",
        type=Path,
        help="read the passphrase from a temporary owner-only file",
    )
    args = parser.parse_args()
    dsn = sys.stdin.read().strip()
    if args.passphrase_file:
        passphrase = args.passphrase_file.read_text(encoding="utf-8").strip()
    else:
        passphrase = getpass.getpass("Encryption passphrase: ").strip()
    payload = encrypt_dsn(dsn, passphrase)
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="dsn.", dir=args.output.parent)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, args.output)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    print(f"Encrypted DSN written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
