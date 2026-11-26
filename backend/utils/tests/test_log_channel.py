"""The log channel id stands in for the session key wherever it travels.

The session key is the HttpOnly session cookie's value, so the channel id must
never equal it, reveal it or be derivable without SECRET_KEY, while both ends
(the auth middleware and the socket server) must compute the same id.
"""

from django.test import SimpleTestCase, override_settings
from logs_helper.log_service import LogService

from utils.log_channel import log_channel_id

SESSION = "abcdefghijklmnopqrstuvwxyz012345"


class LogChannelIdTest(SimpleTestCase):
    def test_is_stable_for_a_session(self) -> None:
        self.assertEqual(log_channel_id(SESSION), log_channel_id(SESSION))

    def test_is_not_the_session_key_and_does_not_contain_it(self) -> None:
        channel = log_channel_id(SESSION)

        self.assertNotEqual(channel, SESSION)
        self.assertNotIn(SESSION, channel)

    def test_differs_between_sessions(self) -> None:
        self.assertNotEqual(log_channel_id(SESSION), log_channel_id("b" * 32))

    def test_is_a_sha256_hex_digest(self) -> None:
        channel = log_channel_id(SESSION)

        self.assertEqual(len(channel), 64)
        int(channel, 16)

    def test_depends_on_the_secret_key(self) -> None:
        # Without SECRET_KEY, a session key cannot be turned into its channel.
        with override_settings(SECRET_KEY="one-secret-key-for-this-test-only"):
            first = log_channel_id(SESSION)
        with override_settings(SECRET_KEY="another-secret-key-for-this-test"):
            second = log_channel_id(SESSION)

        self.assertNotEqual(first, second)

    def test_no_session_has_no_channel(self) -> None:
        self.assertIsNone(log_channel_id(None))
        self.assertIsNone(log_channel_id(""))


class UiLogKeysTest(SimpleTestCase):
    def test_ui_log_keys_are_named_by_the_channel_not_the_session_key(self) -> None:
        key = LogService.generate_redis_key(session_id=SESSION)

        self.assertEqual(key, f"logs:{log_channel_id(SESSION)}")
        self.assertNotIn(SESSION, key)
