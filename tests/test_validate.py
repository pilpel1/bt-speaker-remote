#!/usr/bin/env python3
import unittest

import validate


class CoercePlayUrlTests(unittest.TestCase):
    def test_empty(self):
        self.assertIsNone(validate.coerce_play_url(""))
        self.assertIsNone(validate.coerce_play_url("   "))

    def test_https_passthrough(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.assertEqual(validate.coerce_play_url(url), url)

    def test_bare_youtu_be(self):
        self.assertEqual(
            validate.coerce_play_url("youtu.be/dQw4w9WgXcQ"),
            "https://youtu.be/dQw4w9WgXcQ",
        )

    def test_www_youtube_without_scheme(self):
        self.assertEqual(
            validate.coerce_play_url("www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

    def test_protocol_relative(self):
        self.assertEqual(
            validate.coerce_play_url("//youtu.be/dQw4w9WgXcQ"),
            "https://youtu.be/dQw4w9WgXcQ",
        )

    def test_rejects_javascript(self):
        self.assertIsNone(validate.coerce_play_url("javascript:alert(1)"))

    def test_rejects_plain_text(self):
        self.assertIsNone(validate.coerce_play_url("hello world"))


class PlayUrlErrorTests(unittest.TestCase):
    def test_empty_hebrew(self):
        self.assertEqual(validate.play_url_error(""), validate.ERR_MISSING_URL)

    def test_garbage(self):
        self.assertEqual(validate.play_url_error("not a link"), validate.ERR_BAD_URL)

    def test_youtube_missing_id(self):
        self.assertEqual(
            validate.play_url_error("https://www.youtube.com/watch"),
            validate.ERR_BAD_YOUTUBE,
        )

    def test_youtube_short_id(self):
        self.assertEqual(
            validate.play_url_error("https://youtu.be/short"),
            validate.ERR_BAD_YOUTUBE,
        )

    def test_valid_watch(self):
        self.assertIsNone(validate.play_url_error("https://youtu.be/dQw4w9WgXcQ"))

    def test_valid_playlist(self):
        self.assertIsNone(
            validate.play_url_error(
                "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
            )
        )

    def test_bare_youtube_ok_after_coerce(self):
        self.assertIsNone(validate.play_url_error("youtu.be/dQw4w9WgXcQ"))


class BluetoothAddressTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate.is_bt_address("AA:BB:CC:DD:EE:FF"))
        self.assertTrue(validate.is_bt_address("00:11:22:33:44:55"))

    def test_invalid(self):
        self.assertFalse(validate.is_bt_address(""))
        self.assertFalse(validate.is_bt_address("speaker"))
        self.assertFalse(validate.is_bt_address("AA:BB:CC"))
        self.assertFalse(validate.is_bt_address("AA-BB-CC-DD-EE-FF"))


class FriendlyErrorTests(unittest.TestCase):
    def test_maps_english_player_errors(self):
        self.assertEqual(validate.friendly("Missing sources"), validate.ERR_BAD_URL)
        self.assertEqual(validate.friendly("No Bluetooth speaker connected"), validate.ERR_NO_SPEAKER)
        self.assertIn("אחרון", validate.friendly("playlist-next failed (end of playlist?)"))

    def test_passthrough_unknown(self):
        self.assertEqual(validate.friendly("some unique boom"), "some unique boom")


if __name__ == "__main__":
    unittest.main()
