#!/usr/bin/env python3
import os
import unittest
from unittest.mock import patch

TOKEN = "test-token-for-api-tests-ok"
os.environ["BT_SPEAKER_TOKEN"] = TOKEN

import server  # noqa: E402
import validate  # noqa: E402


class ApiValidationTests(unittest.TestCase):
    def setUp(self):
        os.environ["BT_SPEAKER_TOKEN"] = TOKEN
        self.app = server.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.headers = {"X-Api-Token": TOKEN, "Content-Type": "application/json"}

    def test_play_unauthorized_is_401(self):
        r = self.client.post("/api/play", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
        self.assertEqual(r.status_code, 401)
        data = r.get_json()
        self.assertFalse(data["ok"])
        self.assertTrue(data.get("auth_required"))

    def test_play_empty_is_400_hebrew(self):
        r = self.client.post("/api/play", json={}, headers=self.headers)
        self.assertEqual(r.status_code, 400)
        data = r.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], validate.ERR_MISSING_URL_OR_FILE)

    def test_play_garbage_url_is_400_not_500(self):
        with patch("server.player.play") as play:
            r = self.client.post(
                "/api/play",
                json={"url": "hello world"},
                headers=self.headers,
            )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], validate.ERR_BAD_URL)
        play.assert_not_called()

    def test_play_youtube_without_id_is_400(self):
        with patch("server.player.play") as play:
            r = self.client.post(
                "/api/play",
                json={"url": "https://www.youtube.com/watch"},
                headers=self.headers,
            )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], validate.ERR_BAD_YOUTUBE)
        play.assert_not_called()

    def test_play_bare_youtu_be_is_coerced(self):
        with (
            patch("server._ensure_speaker_ready", return_value=(None, None)),
            patch("server.player.play", return_value={"ok": True, "title": "x"}) as play,
        ):
            r = self.client.post(
                "/api/play",
                json={"url": "youtu.be/dQw4w9WgXcQ"},
                headers=self.headers,
            )
        self.assertEqual(r.status_code, 200)
        play.assert_called_once()
        self.assertEqual(play.call_args[0][0], "https://youtu.be/dQw4w9WgXcQ")

    def test_queue_empty_is_400(self):
        r = self.client.post("/api/queue", json={}, headers=self.headers)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], validate.ERR_MISSING_URL_OR_FILE)

    def test_connect_missing_address_is_400_hebrew(self):
        with patch("server.bt.connect") as connect:
            r = self.client.post("/api/bluetooth/connect", json={}, headers=self.headers)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], validate.ERR_MISSING_ADDRESS)
        connect.assert_not_called()

    def test_connect_invalid_mac_is_400(self):
        with patch("server.bt.connect") as connect:
            r = self.client.post(
                "/api/bluetooth/connect",
                json={"address": "speaker"},
                headers=self.headers,
            )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], validate.ERR_BAD_ADDRESS)
        connect.assert_not_called()

    def test_volume_non_int_is_400(self):
        with patch("server.player.set_volume") as vol:
            r = self.client.post(
                "/api/volume",
                json={"percent": "loud"},
                headers=self.headers,
            )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], validate.ERR_BAD_VOLUME)
        vol.assert_not_called()

    def test_search_empty_is_400_hebrew(self):
        r = self.client.post("/api/search", json={"q": "  "}, headers=self.headers)
        self.assertEqual(r.status_code, 400)
        data = r.get_json()
        self.assertEqual(data["error"], validate.ERR_MISSING_SEARCH)
        self.assertEqual(data["results"], [])

    def test_scan_bad_seconds_is_400(self):
        with patch("server.bt.scan_and_wait") as scan:
            r = self.client.post(
                "/api/bluetooth/scan",
                json={"seconds": "long"},
                headers=self.headers,
            )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], validate.ERR_BAD_SCAN)
        scan.assert_not_called()

    def test_no_speaker_message_is_hebrew(self):
        with patch("server._bt_speaker_connected", return_value=False):
            r = self.client.post(
                "/api/play",
                json={"url": "https://youtu.be/dQw4w9WgXcQ"},
                headers=self.headers,
            )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], validate.ERR_NO_SPEAKER)

    def test_skip_invalid_delta_is_400(self):
        r = self.client.post("/api/skip", json={"delta": "next"}, headers=self.headers)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], validate.ERR_BAD_SKIP)

    def test_normalize_sources_coerces_bare_youtube(self):
        from player import _normalize_sources

        self.assertEqual(
            _normalize_sources(["youtu.be/dQw4w9WgXcQ"]),
            ["https://youtu.be/dQw4w9WgXcQ"],
        )

    def test_save_url_rejects_javascript(self):
        with patch("server.library.save_url_async") as save:
            r = self.client.post(
                "/api/library/save-url",
                json={"url": "javascript:alert(1)"},
                headers=self.headers,
            )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], validate.ERR_BAD_URL)
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
