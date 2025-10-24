from __future__ import annotations

from datetime import timezone
from unittest.mock import patch

from django.test import TestCase

from reviews.services.parsers import (
    parse_categories,
    parse_optional_int,
    parse_superset_bool,
    parse_superset_list,
    parse_superset_timestamp,
    prepare_superset_metadata,
)


class ParsersTests(TestCase):
    def test_parse_categories(self):
        wikitext = "Some text [[Category:Foo]] more text [[Category:Bar]]"
        result = parse_categories(wikitext)
        self.assertEqual(result, ["Bar", "Foo"])

    def test_parse_superset_timestamp_iso_format(self):
        result = parse_superset_timestamp("2024-01-01T12:00:00+00:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)

    def test_parse_superset_timestamp_with_z(self):
        result = parse_superset_timestamp("2024-01-01T12:00:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_parse_superset_timestamp_with_space(self):
        result = parse_superset_timestamp("2024-01-01 12:00:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)

    def test_parse_superset_timestamp_14_digit_format(self):
        result = parse_superset_timestamp("20240101120000")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 1)
        self.assertEqual(result.hour, 12)

    @patch("reviews.services.parsers.logger")
    def test_parse_superset_timestamp_invalid_14_digit(self, mock_logger):
        result = parse_superset_timestamp("99999999999999")
        self.assertIsNone(result)

    @patch("reviews.services.parsers.logger")
    def test_parse_superset_timestamp_invalid_format(self, mock_logger):
        result = parse_superset_timestamp("invalid-timestamp")
        self.assertIsNone(result)

    def test_parse_superset_timestamp_none(self):
        result = parse_superset_timestamp(None)
        self.assertIsNone(result)

    def test_parse_superset_list(self):
        result = parse_superset_list("foo, bar, baz")
        self.assertEqual(result, ["foo", "bar", "baz"])

    def test_parse_superset_list_empty(self):
        result = parse_superset_list(None)
        self.assertEqual(result, [])

    def test_parse_optional_int_valid(self):
        result = parse_optional_int("123")
        self.assertEqual(result, 123)

    def test_parse_optional_int_none(self):
        result = parse_optional_int(None)
        self.assertIsNone(result)

    def test_parse_optional_int_invalid(self):
        result = parse_optional_int("not-a-number")
        self.assertIsNone(result)

    def test_parse_superset_bool_true_values(self):
        for value in ["1", "true", "t", "yes", "y", "True", "YES"]:
            result = parse_superset_bool(value)
            self.assertTrue(result, f"Failed for value: {value}")

    def test_parse_superset_bool_false_values(self):
        for value in ["0", "false", "f", "no", "n", "False", "NO"]:
            result = parse_superset_bool(value)
            self.assertFalse(result, f"Failed for value: {value}")

    def test_parse_superset_bool_none_values(self):
        result = parse_superset_bool(None)
        self.assertIsNone(result)
        result = parse_superset_bool("")
        self.assertIsNone(result)
        result = parse_superset_bool("null")
        self.assertIsNone(result)

    def test_parse_superset_bool_numeric(self):
        self.assertTrue(parse_superset_bool(1))
        self.assertFalse(parse_superset_bool(0))
        self.assertTrue(parse_superset_bool(2.5))

    def test_parse_superset_bool_bool(self):
        self.assertTrue(parse_superset_bool(True))
        self.assertFalse(parse_superset_bool(False))

    def test_parse_superset_bool_other(self):
        result = parse_superset_bool("random-string")
        self.assertTrue(result)

    def test_prepare_superset_metadata_converts_lists(self):
        entry = {
            "change_tags": "tag1,tag2",
            "user_groups": "group1,group2",
            "user_former_groups": "old1,old2",
            "page_categories": "cat1,cat2",
        }
        result = prepare_superset_metadata(entry)
        self.assertEqual(result["change_tags"], ["tag1", "tag2"])
        self.assertEqual(result["user_groups"], ["group1", "group2"])
        self.assertEqual(result["user_former_groups"], ["old1", "old2"])
        self.assertEqual(result["page_categories"], ["cat1", "cat2"])

    def test_prepare_superset_metadata_converts_actor_user(self):
        entry = {"actor_user": "123"}
        result = prepare_superset_metadata(entry)
        self.assertEqual(result["actor_user"], 123)

    def test_prepare_superset_metadata_converts_booleans(self):
        entry = {"rc_bot": "1", "rc_patrolled": "0"}
        result = prepare_superset_metadata(entry)
        self.assertTrue(result["rc_bot"])
        self.assertFalse(result["rc_patrolled"])
