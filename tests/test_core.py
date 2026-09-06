import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from uploader_legacy import config
from uploader_legacy.crypto import decrypt_dsn, encrypt_dsn
from uploader_legacy.browser import parse_cookies


class CookieTests(unittest.TestCase):
    def test_netscape_secure_and_http_only_cookies(self):
        content = "\n".join(
            [
                "# Netscape HTTP Cookie File",
                "#HttpOnly_.tiktok.com\tTRUE\t/\tTRUE\t1893456000\tsessionid\tsecret",
            ]
        )
        cookies = parse_cookies(content)
        self.assertEqual(cookies[0]["name"], "sessionid")
        self.assertTrue(cookies[0]["secure"])
        self.assertTrue(cookies[0]["httpOnly"])
        self.assertEqual(cookies[0]["expiry"], 1893456000)

    def test_json_cookie_data_is_reduced_to_selenium_fields(self):
        cookies = parse_cookies(
            json.dumps(
                [
                    {
                        "name": "sessionid",
                        "value": "secret",
                        "domain": ".tiktok.com",
                        "expirationDate": 1893456000,
                        "sameSite": "no_restriction",
                        "hostOnly": False,
                        "storeId": "0",
                    }
                ]
            )
        )
        self.assertEqual(cookies[0]["expiry"], 1893456000)
        self.assertNotIn("hostOnly", cookies[0])
        self.assertNotIn("storeId", cookies[0])
        self.assertEqual(cookies[0]["sameSite"], "None")


class ConfigTests(unittest.TestCase):
    def test_redaction_never_returns_password_or_query(self):
        dsn = "postgresql://alice:super-secret@db.example/fonya?sslmode=require&token=secret"
        safe = config.redacted_dsn(dsn)
        self.assertNotIn("super-secret", safe)
        self.assertNotIn("secret", safe)
        self.assertIn("alice:***@db.example/fonya", safe)

    def test_keyword_dsn_is_not_echoed(self):
        safe = config.redacted_dsn("host=db.example user=alice password=super-secret dbname=fonya")
        self.assertNotIn("super-secret", safe)
        self.assertEqual(safe, "(configured; credentials hidden)")

    def test_saved_config_is_owner_only(self):
        with tempfile.TemporaryDirectory() as directory:
            config_dir = Path(directory) / "config"
            with patch.object(config, "CONFIG_DIR", config_dir), patch.object(
                config, "CONFIG_PATH", config_dir / "config.json"
            ):
                config.save(config.Config("postgresql://db/fonya"))
                mode = stat.S_IMODE(os.stat(config.CONFIG_PATH).st_mode)
                self.assertEqual(mode, 0o600)
                self.assertEqual(config.load().dsn, "postgresql://db/fonya")


class CryptoTests(unittest.TestCase):
    def test_encrypted_dsn_round_trip_and_wrong_passphrase(self):
        payload = encrypt_dsn("postgresql://alice:password@db/fonya", "correct horse")
        self.assertEqual(
            decrypt_dsn(payload, "correct horse"),
            "postgresql://alice:password@db/fonya",
        )
        with self.assertRaises(ValueError):
            decrypt_dsn(payload, "wrong horse")

    def test_ciphertext_does_not_contain_plaintext(self):
        dsn = "postgresql://alice:unique-production-password@db/fonya"
        payload = encrypt_dsn(dsn, "passphrase")
        self.assertNotIn("unique-production-password", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
