"""Robust parsing helpers for possibly-noisy LLM output."""

from __future__ import annotations

import json
from typing import Any, cast


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first valid JSON object from a possibly noisy model output.

    Raises:
        ValueError: If no valid JSON object is found.
    """

    raw = (text or "").strip()
    if raw.startswith("{") and raw.endswith("}"):
        return cast(dict[str, Any], json.loads(raw))

    def _balanced_candidates(s: str) -> list[str]:
        out: list[str] = []
        start_positions = [i for i, ch in enumerate(s) if ch == "{"]
        for start in start_positions:
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(s)):
                ch = s[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        out.append(s[start : i + 1])
                        break
        return out

    for cand in _balanced_candidates(raw):
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return cast(dict[str, Any], obj)
        except ValueError:
            continue
    raise ValueError("No valid JSON object found in model output.")


def safe_float(value: Any) -> float | None:
    """Return a float for numeric-like values; otherwise ``None``."""

    if isinstance(value, (int, float)):
        return float(value)
    return None
