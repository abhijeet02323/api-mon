"""Small, deterministic JSON-path assertion helpers for API test cases."""

import re


def validate_json_path(value: str) -> str:
    path = value.removeprefix("$").removeprefix(".")
    if path and not re.fullmatch(r"[A-Za-z0-9_-]+(?:\[\d+\])?(?:\.[A-Za-z0-9_-]+(?:\[\d+\])?)*", path):
        raise ValueError("Use a simple JSON path such as status or items[0].id")
    return value


def json_path_value(document, path):
    normalized = path.removeprefix("$").removeprefix(".")
    if not normalized:
        return document, True
    tokens = re.findall(r"[^.\[\]]+|\[\d+\]", normalized)
    current = document
    for token in tokens:
        if token.startswith("["):
            if not isinstance(current, list):
                return None, False
            index = int(token[1:-1])
            if index >= len(current):
                return None, False
            current = current[index]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            return None, False
    return current, True


def assertion_passes(document, assertion):
    actual, exists = json_path_value(document, assertion["path"])
    operator, expected = assertion["operator"], assertion.get("value")
    if operator == "exists":
        return exists
    if operator == "not_exists":
        return not exists
    if not exists:
        return False
    try:
        if operator == "equals": return actual == expected
        if operator == "not_equals": return actual != expected
        if operator == "contains": return expected in actual
        if operator == "gt": return actual > expected
        if operator == "gte": return actual >= expected
        if operator == "lt": return actual < expected
        if operator == "lte": return actual <= expected
    except (TypeError, ValueError):
        return False
    return False
