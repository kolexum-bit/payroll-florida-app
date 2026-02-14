from __future__ import annotations

from decimal import Decimal, InvalidOperation


def parse_rate_to_decimal(rate_str_or_number: str | int | float | Decimal) -> float:
    """Parse user-entered percentage/decimal rates into canonical decimal form.

    Examples:
    - "2.7" / "2.7%" -> 0.027
    - "0.027" -> 0.027
    """
    if isinstance(rate_str_or_number, Decimal):
        raw = rate_str_or_number
        text = str(rate_str_or_number)
    elif isinstance(rate_str_or_number, (int, float)):
        raw = Decimal(str(rate_str_or_number))
        text = str(rate_str_or_number)
    else:
        text = str(rate_str_or_number).strip()
        if not text:
            raise ValueError("Rate is required")
        pct_suffix = text.endswith("%")
        text = text[:-1].strip() if pct_suffix else text
        try:
            raw = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("Rate must be a valid number") from exc
        if pct_suffix:
            return float(raw / Decimal("100"))

    if raw < 0:
        raise ValueError("Rate cannot be negative")

    if raw <= 1:
        return float(raw)
    return float(raw / Decimal("100"))


def format_rate_percent(rate_decimal: float) -> str:
    return f"{(rate_decimal * 100):.4f}".rstrip("0").rstrip(".") + "%"
