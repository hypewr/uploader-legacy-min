# uploader-legacy

Small command-line launcher for opening TikTok Studio for one account. It reads
the account's latest cookies and active proxy from Postgres, starts a visible
Chrome session, and waits for Enter before closing the browser.

## Install and run

Install `uv` using the official installer, then run:

```bash
uvx --from git+https://github.com/hypewr/uploader-legacy-min.git \
    studio 9b358f3iivg2p2jegu
```

The first invocation asks for the DSN passphrase with hidden input. This package
can carry an encrypted production DSN (`production_dsn.enc`) without carrying
the plaintext credential. It decrypts the DSN in memory, verifies the database
connection, and stores it at `~/.config/uploader-legacy/config.json` with
owner-only permissions. Later invocations reuse the local value without
prompting.

This is encryption, not hashing: a hash cannot be decoded. Anyone who has both
the public repository and the passphrase can use the database credential. Use a
least-privilege database role for this tool and send the passphrase through a
separate trusted channel. The passphrase itself is never committed or saved by
the tool.

If no encrypted payload is bundled, first use instead asks directly for the
Postgres DSN.

The workstation must have Google Chrome or Chromium installed. Selenium
Manager downloads the matching ChromeDriver automatically on first launch.
The GitHub repository must be public for the unauthenticated `https://github.com`
clone in the command above to work.

## Configuration commands

```bash
studio config set-dsn
studio config show
studio config path
```

`DSN` in the environment takes precedence over the saved configuration. The
saved file never prints the full DSN in command output.

## Options

```bash
studio ACCOUNT_ID --url https://www.tiktok.com/tiktokstudio/content
studio ACCOUNT_ID --no-proxy
```

The database schema must contain:

- `documents(account_id, content, created_at)`
- `proxies(account_id, proxy_address, port, username, password, status)`
