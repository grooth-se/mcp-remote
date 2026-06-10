"""Validation and normalization of user-entered curve property data.

Curve properties are stored as {"temperature": [...], "value": [...]} with
numeric lists. User input arrives as JSON text (serialized by the table
editor in the UI) and may contain quoted numbers, decimal commas or other
junk — this module coerces and validates it before storage.
"""

import json
import math


def _to_float(raw):
    """Coerce a single cell to float. Returns None when not possible.

    Accepts int/float directly and strings with surrounding whitespace.
    A single decimal comma is accepted when no period is present
    (e.g. "45,5" -> 45.5).
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if "," in text and "." not in text and text.count(",") == 1:
            text = text.replace(",", ".")
        try:
            value = float(text)
        except ValueError:
            return None
    else:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def parse_curve_data(raw) -> tuple[dict | None, list[str]]:
    """Parse and validate curve data from user input.

    Parameters
    ----------
    raw : str | dict
        JSON string or already-parsed dict shaped
        {"temperature": [...], "value": [...]}.

    Returns
    -------
    (data, errors)
        data is the canonical {"temperature": [float...], "value": [float...]}
        sorted by temperature, or None when validation failed.
        errors is a list of human-readable messages (empty on success).
    """
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None, ["Curve data is empty. Enter at least 2 temperature/value points."]
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None, ["Curve data is not valid JSON."]
    elif isinstance(raw, dict):
        parsed = raw
    else:
        return None, ["Curve data must be a JSON object."]

    if not isinstance(parsed, dict):
        return None, ["Curve data must be a JSON object with 'temperature' and 'value' lists."]

    temps_raw = parsed.get("temperature")
    values_raw = parsed.get("value")
    if not isinstance(temps_raw, list) or not isinstance(values_raw, list):
        return None, ["Curve data must contain 'temperature' and 'value' lists."]

    errors = []
    if len(temps_raw) != len(values_raw):
        errors.append(
            f"Temperature and value lists have different lengths "
            f"({len(temps_raw)} vs {len(values_raw)})."
        )
        return None, errors

    points = []
    for i, (t_raw, v_raw) in enumerate(zip(temps_raw, values_raw, strict=False), start=1):
        t = _to_float(t_raw)
        v = _to_float(v_raw)
        if t is None:
            errors.append(f"Row {i}: temperature '{t_raw}' is not a number.")
        if v is None:
            errors.append(f"Row {i}: value '{v_raw}' is not a number.")
        if t is not None and v is not None:
            points.append((t, v))

    if errors:
        return None, errors

    if len(points) < 2:
        return None, ["Enter at least 2 temperature/value points."]

    points.sort(key=lambda p: p[0])
    temps = [p[0] for p in points]
    if len(set(temps)) != len(temps):
        dupes = sorted({t for t in temps if temps.count(t) > 1})
        return None, [f"Duplicate temperatures not allowed: {', '.join(str(d) for d in dupes)}."]

    return {"temperature": temps, "value": [p[1] for p in points]}, []
