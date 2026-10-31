"""Maritime message envelopes and inner JSON responses."""

import json


def parse(message: str) -> dict:
    if not isinstance(message, str):
        raise ValueError("message must be a string")
    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return {"type": "ask", "text": message}
    if not isinstance(payload, dict):
        raise ValueError("envelope must be a JSON object")
    if "v" in payload and (type(payload["v"]) is not int or payload["v"] != 1):
        raise ValueError("unsupported envelope version")
    if not isinstance(payload.get("type"), str) or not payload["type"]:
        raise ValueError("envelope requires a type")
    return payload


def success(payload: dict) -> dict:
    return {**payload, "ok": True}


def error(message: str) -> dict:
    return {"ok": False, "error": str(message)}
