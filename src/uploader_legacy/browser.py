"""Visible Chrome setup and cookie authentication."""

from __future__ import annotations

import json
import os
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options

from .proxy import ProxyRelay


HOME_URL = "https://www.tiktok.com/"


def parse_cookies(content: str) -> list[dict[str, Any]]:
    """Parse the Netscape cookie text stored by the legacy uploader."""
    stripped = content.strip()
    if stripped.startswith("["):
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError("stored cookie JSON is malformed") from exc
        if not isinstance(raw, list):
            raise ValueError("stored cookie JSON must be a list")
        cookies = []
        for item in raw:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            cookie = {
                key: item[key]
                for key in (
                    "name", "value", "domain", "path", "secure", "httpOnly", "expiry", "sameSite"
                )
                if key in item
            }
            if "expirationDate" in item and "expiry" not in cookie:
                try:
                    cookie["expiry"] = int(item["expirationDate"])
                except (TypeError, ValueError):
                    pass
            if "sameSite" in cookie:
                same_site = str(cookie["sameSite"]).lower()
                same_site = {
                    "lax": "Lax",
                    "strict": "Strict",
                    "no_restriction": "None",
                    "none": "None",
                }.get(same_site)
                if same_site is None:
                    cookie.pop("sameSite", None)
                else:
                    cookie["sameSite"] = same_site
            cookies.append(cookie)
        return cookies

    cookies: list[dict[str, Any]] = []
    for line in content.splitlines():
        http_only = line.startswith("#HttpOnly_")
        if http_only:
            line = line[len("#HttpOnly_"):]
        elif not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        cookie: dict[str, Any] = {
            "domain": fields[0].strip(),
            "path": fields[2].strip() or "/",
            "name": fields[5].strip(),
            "value": fields[6].strip(),
            "secure": fields[3].strip().upper() == "TRUE",
        }
        if http_only:
            cookie["httpOnly"] = True
        try:
            expiry = int(fields[4])
        except ValueError:
            expiry = 0
        if expiry > 0:
            cookie["expiry"] = expiry
        cookies.append(cookie)
    return cookies


def _chrome_options(proxy: dict[str, Any] | None) -> tuple[Options, ProxyRelay | None]:
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--mute-audio")
    options.add_argument("--lang=en")
    if os.environ.get("CHROME_BINARY"):
        options.binary_location = os.environ["CHROME_BINARY"]

    relay = None
    if proxy:
        if proxy.get("user") is not None and proxy.get("pass") is not None:
            relay = ProxyRelay(proxy["host"], proxy["port"], proxy["user"], proxy["pass"])
            relay.start()
            options.add_argument(f"--proxy-server=http://127.0.0.1:{relay.port}")
        else:
            options.add_argument(f"--proxy-server={proxy['host']}:{proxy['port']}")
    return options, relay


def open_authenticated(cookies_text: str, proxy: dict[str, Any] | None, url: str) -> None:
    relay = None
    driver = None
    try:
        options, relay = _chrome_options(proxy)
        try:
            driver = webdriver.Chrome(options=options)
        except WebDriverException as exc:
            raise RuntimeError(
                "Could not start Chrome. Install Google Chrome or Chromium and try again. "
                f"Selenium Manager reported: {exc}"
            ) from exc

        driver.set_page_load_timeout(120)
        try:
            driver.get(HOME_URL)
        except WebDriverException as exc:
            raise RuntimeError(f"Could not load TikTok: {exc}") from exc
        try:
            cookies = parse_cookies(cookies_text)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        if not cookies:
            raise RuntimeError("The database returned no usable cookies.")
        failed = 0
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except WebDriverException:
                failed += 1
        if failed == len(cookies):
            raise RuntimeError("None of the stored cookies could be added to TikTok.")

        if driver.get_cookie("sessionid") is None:
            raise RuntimeError("The stored cookies do not contain a usable TikTok session.")
        try:
            driver.get(url)
        except WebDriverException as exc:
            raise RuntimeError(f"Could not load TikTok Studio: {exc}") from exc
        if "login" in (driver.current_url or "").lower():
            raise RuntimeError(
                "TikTok redirected to its login page; the stored session cookie may be expired."
            )
        print("\n" + "=" * 64)
        print("TikTok Studio is open with the stored session.")
        print("Make your changes in the browser, then press ENTER here to close it.")
        print("=" * 64)
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass
        if relay is not None:
            relay.stop()
