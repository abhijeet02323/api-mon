import unittest

from assertions import assertion_passes, json_path_value, validate_json_path


class JsonAssertionTests(unittest.TestCase):
    def setUp(self):
        self.document = {"status": "ok", "count": 3, "items": [{"id": "a1"}, {"id": "b2"}], "tags": ["blue", "green"]}

    def test_reads_dot_paths_and_array_indexes(self):
        self.assertEqual(json_path_value(self.document, "status"), ("ok", True))
        self.assertEqual(json_path_value(self.document, "$.items[1].id"), ("b2", True))
        self.assertEqual(json_path_value(self.document, "items[9].id"), (None, False))

    def test_supports_equality_presence_contains_and_numeric_operators(self):
        checks = [
            ({"path": "status", "operator": "equals", "value": "ok"}, True),
            ({"path": "status", "operator": "not_equals", "value": "down"}, True),
            ({"path": "status", "operator": "equals", "value": "degraded"}, False),
            ({"path": "count", "operator": "exists"}, True),
            ({"path": "missing", "operator": "not_exists"}, True),
            ({"path": "tags", "operator": "contains", "value": "green"}, True),
            ({"path": "count", "operator": "gt", "value": 2}, True),
            ({"path": "count", "operator": "gte", "value": 3}, True),
            ({"path": "count", "operator": "lt", "value": 4}, True),
            ({"path": "count", "operator": "lte", "value": 3}, True),
            ({"path": "count", "operator": "gt", "value": "3"}, False),
        ]
        for assertion, expected in checks:
            with self.subTest(assertion=assertion):
                self.assertEqual(assertion_passes(self.document, assertion), expected)

    def test_rejects_unsupported_path_syntax(self):
        with self.assertRaises(ValueError):
            validate_json_path("items[*].id")
        self.assertEqual(validate_json_path("$.items[0].id"), "$.items[0].id")


if __name__ == "__main__":
    unittest.main()
