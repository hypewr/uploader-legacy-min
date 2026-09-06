"""Command-line entry point for ``studio``."""

from __future__ import annotations

import argparse
import sys

from . import config
from .browser import HOME_URL, open_authenticated
from .db import check_connection, fetch_cookies, fetch_proxy


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio",
        description="Open TikTok Studio for one account using its stored session.",
    )
    parser.add_argument("account_id", nargs="?", help="account ID to open")
    parser.add_argument("--url", default="https://www.tiktok.com/tiktokstudio", help="page to open")
    parser.add_argument("--no-proxy", action="store_true", help="connect using this workstation's IP")
    return parser


def _config_command(arguments: list[str]) -> int:
    if not arguments or arguments[0] == "show":
        saved = config.load()
        print(f"Configuration path: {config.CONFIG_PATH}")
        print(f"DSN: {config.redacted_dsn(saved.dsn)}")
        return 0
    if arguments[0] == "path":
        print(config.CONFIG_PATH)
        return 0
    if arguments[0] == "set-dsn":
        config.prompt_and_save(validate=check_connection)
        return 0
    if arguments[0] == "clear":
        try:
            config.CONFIG_PATH.unlink()
        except FileNotFoundError:
            pass
        print("Configuration removed.")
        return 0
    print("Usage: studio config [show|set-dsn|path|clear]", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if arguments[:1] == ["config"]:
        return _config_command(arguments[1:])

    parser = _parser()
    args = parser.parse_args(arguments)
    if not args.account_id:
        parser.print_help()
        return 2

    settings = config.ensure(validate=check_connection)
    try:
        cookies = fetch_cookies(settings.dsn, args.account_id)
    except Exception as exc:
        raise SystemExit(
            "Could not read account data from Postgres "
            f"({type(exc).__name__}). Check the DSN with 'studio config set-dsn'."
        ) from exc
    if not cookies:
        raise SystemExit(
            f"No cookies found for account {args.account_id} in the documents table."
        )

    proxy = None
    if not args.no_proxy:
        try:
            proxy = fetch_proxy(settings.dsn, args.account_id)
        except Exception as exc:
            raise SystemExit(
                "Could not read the account proxy from Postgres "
                f"({type(exc).__name__}). Check the database schema and DSN."
            ) from exc

    if args.no_proxy:
        print(f"Opening {args.account_id} through this workstation's IP (--no-proxy).")
    elif proxy:
        print(f"Using the active proxy for {args.account_id}.")
    else:
        print("No active proxy found; opening through this workstation's IP.")

    try:
        open_authenticated(cookies, proxy, args.url or HOME_URL)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    except Exception as exc:
        raise SystemExit(f"Could not open TikTok Studio ({type(exc).__name__}).") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
