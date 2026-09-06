"""The two database reads required by the Studio launcher."""

from __future__ import annotations

from typing import Any

import psycopg


def _connect(dsn: str):
    return psycopg.connect(
        dsn,
        autocommit=True,
        connect_timeout=15,
        options="-c statement_timeout=30000",
    )


def check_connection(dsn: str) -> None:
    """Verify a DSN before saving it during first-run setup."""
    with _connect(dsn) as connection:
        connection.execute("SELECT 1")


def fetch_cookies(dsn: str, account_id: str) -> str | None:
    with _connect(dsn) as connection:
        row = connection.execute(
            "SELECT content FROM documents "
            "WHERE account_id = %s ORDER BY created_at DESC LIMIT 1",
            (account_id,),
        ).fetchone()
    return str(row[0]) if row and row[0] else None


def fetch_proxy(dsn: str, account_id: str) -> dict[str, Any] | None:
    with _connect(dsn) as connection:
        row = connection.execute(
            "SELECT proxy_address, port, username, password FROM proxies "
            "WHERE account_id = %s AND status = 'active' LIMIT 1",
            (account_id,),
        ).fetchone()
    if not row or row[0] is None or row[1] is None:
        return None
    proxy = {"host": str(row[0]), "port": str(row[1])}
    if row[2] is not None and row[3] is not None:
        proxy.update({"user": str(row[2]), "pass": str(row[3])})
    return proxy
