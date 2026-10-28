#!/usr/bin/env python3
"""Static UI contracts for the everyday PWA (no browser / Bluetooth)."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


class TransportButtonsTests(unittest.TestCase):
    def test_prev_is_left_of_next_in_ltr_transport(self):
        start = HTML.index('class="transport"')
        chunk = HTML[start : start + 1800]
        self.assertLess(chunk.index('id="prevBtn"'), chunk.index('id="nextBtn"'))
        self.assertIn('aria-label="הקודם"', chunk[chunk.index("prevBtn") :])
        self.assertIn('aria-label="הבא"', chunk[chunk.index("nextBtn") :])


class ClientValidationTests(unittest.TestCase):
    def test_play_from_here_string_exists(self):
        self.assertIn("playFromHere:", JS)

    def test_transport_armed_is_declared(self):
        self.assertIn("let transportArmedAt", JS)

    def test_url_input_allows_bare_youtu_be(self):
        self.assertIn('id="ytUrl"', HTML)
        self.assertIn('type="text"', HTML)
        self.assertIn("coercePlayUrl", JS)
        self.assertIn("playUrlError", JS)

    def test_offline_banner_wired(self):
        self.assertIn('id="offlineBanner"', HTML)
        self.assertIn("offlineBanner", JS)
        self.assertIn(".offline-banner", CSS)

    def test_speaker_check_uses_is_audio(self):
        self.assertIn("function isSpeakerDevice", JS)
        self.assertIn("d.is_audio", JS)


class ServiceWorkerTests(unittest.TestCase):
    def test_network_first_not_cache_first(self):
        self.assertIn("Network-first", SW)
        self.assertIn("fetch(req)", SW)
        self.assertIn("caches.match(req)", SW)
        fetch_at = SW.index("fetch(req)")
        cache_at = SW.index("caches.match(req)")
        self.assertLess(fetch_at, cache_at)

    def test_api_never_cached(self):
        self.assertIn('url.pathname.startsWith("/api/")', SW)


class TouchTargetTests(unittest.TestCase):
    def test_inline_actions_meet_44px(self):
        self.assertIn("min-height: 44px", CSS)
        self.assertIn(".icon-mini", CSS)


if __name__ == "__main__":
    unittest.main()
