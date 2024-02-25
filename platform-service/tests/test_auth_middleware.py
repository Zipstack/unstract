import unittest

from unstract.platform_service.main import (
    get_account_from_bearer_token,
    validate_bearer_token,
)


class TestAuthMiddleware(unittest.TestCase):
    def test_auth_middleware(self) -> None:
        try:
            self.assertTrue(validate_bearer_token("test"))
            self.assertEqual(get_account_from_bearer_token("test"), "mock_org")
        except Exception as e:
            self.fail(f"Authentication Test failed: {e}")


if __name__ == "__main__":
    unittest.main()
