"""Validation and substitution helpers for saved API test scenarios."""

import json
import os
import re

from assertions import validate_json_path


class ScenarioConfigError(ValueError):
    """The saved scenario cannot be safely rendered or executed."""


def validate_headers(headers):
    if len(headers) > 30:
        raise ValueError("A request can have at most 30 custom headers")
    forbidden = {"host", "content-length", "transfer-encoding", "connection", "proxy-authorization", "proxy-connection", "upgrade", "te", "trailer"}
    for name, value in headers.items():
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or name.lower() in forbidden or name.lower().startswith("proxy-"):
            raise ValueError(f"Header name is not allowed: {name}")
        if len(value) > 4096 or "\r" in value or "\n" in value:
            raise ValueError(f"Header value for {name} is invalid or too long")
        looks_secret = any(term in name.lower() for term in ("authorization", "cookie", "token", "secret", "password", "api-key", "api_key"))
        uses_safe_reference = value.startswith("env:SENTINEL_SECRET_") or ("{{" in value and "}}" in value)
        if looks_secret and not uses_safe_reference:
            raise ValueError(f"Use env:SENTINEL_SECRET_NAME or a chained variable for sensitive header {name}; literal secrets are not stored")
    return headers


def validate_extractions(extractions):
    for variable, path in extractions.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", variable):
            raise ValueError("Extracted variable names must start with a letter and contain only letters, digits, or underscores")
        validate_json_path(path)
    return extractions


def resolve_scenario_text(template, variables):
    if template is None:
        return None
    if template.startswith("env:"):
        name = template[4:]
        if not name.startswith("SENTINEL_SECRET_"):
            raise ScenarioConfigError("Secret references must use the SENTINEL_SECRET_ environment prefix")
        value = os.getenv(name)
        if value is None:
            raise ScenarioConfigError(f"Required secret environment variable is not configured: {name}")
        return value

    def replace(match):
        name = match.group(1)
        if name.startswith("env:"):
            env_name = name[4:]
            if not env_name.startswith("SENTINEL_SECRET_"):
                raise ScenarioConfigError("Secret references must use the SENTINEL_SECRET_ environment prefix")
            value = os.getenv(env_name)
            if value is None:
                raise ScenarioConfigError(f"Required secret environment variable is not configured: {env_name}")
            return value
        if name not in variables:
            raise ScenarioConfigError(f"Scenario variable is not available: {name}")
        value = variables[name]
        return value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))

    return re.sub(r"\{\{([A-Za-z][A-Za-z0-9_]*|env:[A-Za-z][A-Za-z0-9_]*)\}\}", replace, template)
