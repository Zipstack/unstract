import unittest

from unstract.core.account_services.unstract_account import UnstractAccount


class TestUnstractAccount(unittest.TestCase):
    def test_provision_blob(self):
        account = UnstractAccount("acme", "johndoe")
        account.provision_s3_storage()
        account.upload_sample_files()
        self.assertEqual(True, True)  # add assertion here


if __name__ == "__main__":
    unittest.main()
