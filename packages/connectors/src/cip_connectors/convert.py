"""Value conversion for mapped fields. Every failure raises ConversionError with a reason."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from cip_connectors.mapping import FieldRule, MappingSet

Cell = str | int | float | datetime | None


class ConversionError(ValueError):
    pass


def _text(value: Cell) -> str:
    return "" if value is None else str(value).strip()


def _decimal(value: Cell, mapping: MappingSet) -> Decimal:
    if isinstance(value, int | float):
        return Decimal(str(value))
    raw = _text(value)
    if mapping.decimal == ",":
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ConversionError(f"not a number: {raw!r}") from exc


EXCEL_EPOCH = datetime(1899, 12, 30)


def _datetime(value: Cell, mapping: MappingSet) -> str:
    if isinstance(value, datetime):
        local = value
    elif isinstance(value, int | float):
        # Excel serial date: days since 1899-12-30, fraction = time of day (to the second).
        local = EXCEL_EPOCH + timedelta(seconds=round(float(value) * 86400))
    else:
        try:
            local = datetime.strptime(_text(value), mapping.datetime_format)
        except ValueError as exc:
            raise ConversionError(
                f"not a date/time in format {mapping.datetime_format}: {_text(value)!r}"
            ) from exc
    if local.tzinfo is None:
        local = local.replace(tzinfo=ZoneInfo(mapping.timezone))
    return local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _code(raw: str, rule: FieldRule, mapping: MappingSet, column: str) -> str:
    table = (
        rule.values
        if rule.values is not None
        else mapping.code_tables.get(rule.code_table or "", {})
    )
    if rule.code_table and rule.code_table not in mapping.code_tables:
        raise ConversionError(f"code table {rule.code_table!r} is not defined")
    if raw not in table:
        raise ConversionError(f"unknown code {raw!r} in column {column!r}")
    return table[raw]


def convert(value: Cell, rule: FieldRule, mapping: MappingSet, column: str) -> str | None:
    """Standard-layout text for one field, or None when empty and optional."""
    if _text(value) == "":
        if rule.optional:
            return None
        raise ConversionError(f"column {column!r} is empty")
    if rule.type == "decimal":
        return str(_decimal(value, mapping).normalize())
    if rule.type == "int":
        number = _decimal(value, mapping)
        if number != number.to_integral_value():
            raise ConversionError(f"not a whole number: {_text(value)!r}")
        return str(int(number))
    if rule.type == "eur_cents":
        cents = _decimal(value, mapping) * 100
        if cents != cents.to_integral_value():
            raise ConversionError(f"more than two decimals for euros: {_text(value)!r}")
        return str(int(cents))
    if rule.type == "datetime":
        return _datetime(value, mapping)
    if rule.type == "bool":
        raw = _text(value).lower()
        if raw in mapping.true_values:
            return "true"
        if raw in mapping.false_values:
            return "false"
        raise ConversionError(f"not yes/no: {_text(value)!r}")
    raw = _text(value)
    if rule.type == "list":
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        if rule.values is not None or rule.code_table:
            parts = [_code(p, rule, mapping, column) for p in parts]
        return ";".join(rule.prefix + p for p in parts)
    if rule.values is not None or rule.code_table:
        raw = _code(raw, rule, mapping, column)
    return rule.prefix + raw
