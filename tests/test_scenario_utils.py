import os
import unittest
from unittest.mock import patch

from scenario_utils import ScenarioConfigError, resolve_scenario_text, validate_headers


class ScenarioUtilityTests(unittest.TestCase):
    def test_resolves_chained_variables_and_environment_secrets(self):
        with patch.dict(os.environ, {"SENTINEL_SECRET_TOKEN": "secret-value"}):
            self.assertEqual(resolve_scenario_text("https://api.example.org/items/{{item_id}}", {"item_id": 42}), "https://api.example.org/items/42")
            self.assertEqual(resolve_scenario_text("Bearer {{env:SENTINEL_SECRET_TOKEN}}", {}), "Bearer secret-value")
            self.assertEqual(resolve_scenario_text("env:SENTINEL_SECRET_TOKEN", {}), "secret-value")

    def test_missing_variables_and_secrets_fail_without_exposing_values(self):
        with self.assertRaises(ScenarioConfigError):
            resolve_scenario_text("Bearer {{missing}}", {})
        with self.assertRaises(ScenarioConfigError):
            resolve_scenario_text("env:SENTINEL_SECRET_NOT_SET", {})

    def test_sensitive_headers_require_secret_references(self):
        self.assertTrue(validate_headers({"Authorization": "env:SENTINEL_SECRET_BEARER"}))
        with self.assertRaises(ValueError):
            validate_headers({"Authorization": "Bearer literal-secret"})
        with self.assertRaises(ValueError):
            validate_headers({"Host": "attacker.example"})


if __name__ == "__main__":
    unittest.main()
