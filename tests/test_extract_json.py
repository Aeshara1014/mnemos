"""_extract_json tolerates fences, single values, and CONCATENATED JSON.

Local models sometimes emit several objects back-to-back with no array
wrapper (``{...}{...}``); a single ``json.loads()`` silently keeps only the
first. These pin the recovery (and the pre-existing fence/single-value paths).
"""
from mnemos.encoding.llm_classifier import _extract_json


def test_single_object():
    assert _extract_json('{"a": 1}') == [{"a": 1}]


def test_single_array():
    assert _extract_json('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]


def test_concatenated_objects():
    assert _extract_json('{"id": "1"}{"id": "2"}') == [{"id": "1"}, {"id": "2"}]


def test_concatenated_objects_with_whitespace_and_newlines():
    raw = '{"id": "1"}\n{"id": "2"}  {"id": "3"}'
    assert _extract_json(raw) == [{"id": "1"}, {"id": "2"}, {"id": "3"}]


def test_concatenated_objects_comma_separated():
    # Comma-joined objects with no surrounding brackets (not a valid array).
    assert _extract_json('{"id": "1"}, {"id": "2"}') == [{"id": "1"}, {"id": "2"}]


def test_fenced_array():
    assert _extract_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]


def test_fenced_concatenated_objects():
    assert _extract_json('```\n{"a": 1}{"b": 2}\n```') == [{"a": 1}, {"b": 2}]


def test_array_then_object_concatenated():
    assert _extract_json('[{"a": 1}] {"b": 2}') == [{"a": 1}, {"b": 2}]


def test_non_dict_list_elements_filtered():
    assert _extract_json('[1, {"a": 1}, "x"]') == [{"a": 1}]


def test_empty_returns_empty():
    assert _extract_json("") == []
    assert _extract_json("   ") == []


def test_garbage_returns_empty():
    assert _extract_json("not json at all") == []


def test_partial_garbage_after_first_object_stops_gracefully():
    # The first object is recovered; trailing garbage ends the scan (logged).
    assert _extract_json('{"a": 1} garbage!!!') == [{"a": 1}]


def test_pathologically_deep_nesting_does_not_raise():
    # Python's C json scanner caps nesting (~10k) and raises RecursionError
    # (a RuntimeError, not JSONDecodeError). _extract_json must swallow it and
    # return [], never propagate — two of its callers don't guard exceptions.
    deep = "[" * 12000 + "]" * 12000
    assert _extract_json(deep) == []
