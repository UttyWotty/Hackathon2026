"""
Unit tests for the export_formats utility module.
Covers dict_to_two_column_csv and rows_to_csv with happy-path,
boundary, and error cases for CSV serialisation of dicts and row lists.
"""

import csv
import io
from typing import Any, Dict, List

from utils.export_formats import dict_to_two_column_csv, rows_to_csv

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_csv(text: str) -> List[List[str]]:
    """Parse a CSV string into a list of rows (list of strings)."""
    reader = csv.reader(io.StringIO(text))
    return list(reader)


# ---------------------------------------------------------------------------
# dict_to_two_column_csv
# ---------------------------------------------------------------------------


class TestDictToTwoColumnCsv:
    """Tests for dict_to_two_column_csv."""

    def test_happy_path_single_entry(self) -> None:
        """A single-entry dict produces a header row and one data row."""
        data: Dict[str, Any] = {"alpha": 42}
        result = dict_to_two_column_csv(data)
        rows = _parse_csv(result)
        assert rows[0] == ["key", "value"]
        assert rows[1] == ["alpha", "42"]

    def test_happy_path_multiple_entries(self) -> None:
        """Multiple entries are emitted with the correct header."""
        data: Dict[str, Any] = {"b_key": 2, "a_key": 1}
        result = dict_to_two_column_csv(data)
        rows = _parse_csv(result)
        assert rows[0] == ["key", "value"]
        assert len(rows) == 3  # header + 2 data rows

    def test_keys_are_sorted(self) -> None:
        """Output rows are sorted alphabetically by key."""
        data: Dict[str, Any] = {"cherry": 3, "apple": 1, "banana": 2}
        result = dict_to_two_column_csv(data)
        rows = _parse_csv(result)
        keys = [r[0] for r in rows[1:]]
        assert keys == ["apple", "banana", "cherry"]

    def test_empty_dict(self) -> None:
        """An empty dict produces only the header row."""
        result = dict_to_two_column_csv({})
        rows = _parse_csv(result)
        assert rows[0] == ["key", "value"]
        assert len(rows) == 1

    def test_value_types_are_stringified(self) -> None:
        """Non-string values (int, float, bool, None) are converted to strings."""
        data: Dict[str, Any] = {
            "count": 100,
            "ratio": 3.14,
            "flag": True,
            "empty": None,
        }
        result = dict_to_two_column_csv(data)
        rows = _parse_csv(result)
        value_map = {r[0]: r[1] for r in rows[1:]}
        assert value_map["count"] == "100"
        assert value_map["ratio"] == "3.14"
        assert value_map["flag"] == "True"
        assert value_map["empty"] == ""

    def test_special_characters_in_values(self) -> None:
        """Values with commas, quotes, and newlines are properly CSV-escaped."""
        data: Dict[str, Any] = {"msg": 'He said, "hello"'}
        result = dict_to_two_column_csv(data)
        rows = _parse_csv(result)
        assert rows[1][1] == 'He said, "hello"'

    def test_numeric_string_keys(self) -> None:
        """Keys that are numeric strings are sorted lexicographically."""
        data: Dict[str, Any] = {"2": "b", "10": "a", "1": "c"}
        result = dict_to_two_column_csv(data)
        rows = _parse_csv(result)
        keys = [r[0] for r in rows[1:]]
        # Lexicographic: "1", "10", "2"
        assert keys == ["1", "10", "2"]

    def test_output_ends_with_newline(self) -> None:
        """CSV output ends with a trailing newline."""
        data: Dict[str, Any] = {"x": 1}
        result = dict_to_two_column_csv(data)
        assert result.endswith("\n") or result.endswith("\r\n")


# ---------------------------------------------------------------------------
# rows_to_csv
# ---------------------------------------------------------------------------


class TestRowsToCsv:
    """Tests for rows_to_csv."""

    def test_happy_path(self) -> None:
        """Basic list of dicts is serialised with the specified fieldnames."""
        rows_data = [
            {"name": "Alice", "age": "30"},
            {"name": "Bob", "age": "25"},
        ]
        result = rows_to_csv(rows_data, fieldnames=("name", "age"))
        rows = _parse_csv(result)
        assert rows[0] == ["name", "age"]
        assert rows[1] == ["Alice", "30"]
        assert rows[2] == ["Bob", "25"]

    def test_field_order_matches_fieldnames(self) -> None:
        """Columns appear in the order specified by fieldnames, not dict order."""
        rows_data = [{"b": 2, "a": 1}]
        result = rows_to_csv(rows_data, fieldnames=("a", "b"))
        rows = _parse_csv(result)
        assert rows[0] == ["a", "b"]
        assert rows[1] == ["1", "2"]

    def test_extra_keys_are_ignored(self) -> None:
        """Dict keys not in fieldnames are silently ignored."""
        rows_data = [{"name": "X", "age": 10, "secret": "hidden"}]
        result = rows_to_csv(rows_data, fieldnames=("name", "age"))
        rows = _parse_csv(result)
        assert len(rows[0]) == 2
        assert "secret" not in rows[0]

    def test_missing_keys_produce_empty_cells(self) -> None:
        """If a row is missing a fieldname key, the cell is empty."""
        rows_data = [{"name": "Alice"}]
        result = rows_to_csv(rows_data, fieldnames=("name", "age"))
        rows = _parse_csv(result)
        assert rows[1] == ["Alice", ""]

    def test_empty_rows_list(self) -> None:
        """An empty iterable produces only the header row."""
        result = rows_to_csv([], fieldnames=("a", "b"))
        rows = _parse_csv(result)
        assert rows[0] == ["a", "b"]
        assert len(rows) == 1

    def test_single_column(self) -> None:
        """Works correctly with a single fieldname."""
        rows_data = [{"id": "1"}, {"id": "2"}]
        result = rows_to_csv(rows_data, fieldnames=("id",))
        rows = _parse_csv(result)
        assert rows[0] == ["id"]
        assert len(rows) == 3

    def test_special_characters_in_values(self) -> None:
        """Values containing commas and quotes are properly escaped."""
        rows_data = [{"desc": 'a, b, and "c"'}]
        result = rows_to_csv(rows_data, fieldnames=("desc",))
        rows = _parse_csv(result)
        assert rows[1][0] == 'a, b, and "c"'

    def test_generator_input(self) -> None:
        """An iterable (generator) works just like a list."""

        def gen():
            yield {"v": "x"}
            yield {"v": "y"}

        result = rows_to_csv(gen(), fieldnames=("v",))
        rows = _parse_csv(result)
        assert len(rows) == 3  # header + 2 rows

    def test_output_ends_with_newline(self) -> None:
        """CSV output ends with a trailing newline."""
        rows_data = [{"a": 1}]
        result = rows_to_csv(rows_data, fieldnames=("a",))
        assert result.endswith("\n") or result.endswith("\r\n")

    def test_large_number_of_rows(self) -> None:
        """Handles a larger number of rows without error."""
        rows_data = [{"i": str(n)} for n in range(500)]
        result = rows_to_csv(rows_data, fieldnames=("i",))
        parsed = _parse_csv(result)
        # header + 500 data rows
        assert len(parsed) == 501
