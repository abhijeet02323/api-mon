"""Small stdlib-only checks for the URL and password primitives."""
import unittest


class SecurityHelperTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verifiable(self):
        from app import hash_password, verify_password
        one = hash_password("correct horse battery")
        two = hash_password("correct horse battery")
        self.assertNotEqual(one, two)
        self.assertTrue(verify_password("correct horse battery", one))
        self.assertFalse(verify_password("wrong password", one))

    def test_url_policy_blocks_local_addresses_and_credentials(self):
        from app import safe_url
        for url in ("http://127.0.0.1/", "http://169.254.169.254/latest/", "http://user:pass@example.com/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                safe_url(url)


if __name__ == "__main__":
    unittest.main()
