"""Excel (.xlsx) reader: header detection, merged cells, empty rows, real and serial dates."""

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from cip_connectors.convert import Cell
from cip_connectors.readers import DropRule, SourceTable


def _unmerge(ws: Worksheet) -> None:
    """Give every cell of a merged range the top-left value, as a person reading it would."""
    for merged in list(ws.merged_cells.ranges):
        value = ws.cell(merged.min_row, merged.min_col).value
        ws.unmerge_cells(str(merged))
        for row in range(merged.min_row, merged.max_row + 1):
            for col in range(merged.min_col, merged.max_col + 1):
                ws.cell(row, col).value = value


def _is_header(values: tuple[object, ...]) -> bool:
    texts = [v for v in values if isinstance(v, str) and v.strip()]
    return len(texts) >= 2 and len(texts) == len([v for v in values if v not in (None, "")])


def read_xlsx(path: Path, drop: DropRule, sheet: str | None = None) -> SourceTable:
    wb = load_workbook(path, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    _unmerge(ws)
    rows = list(ws.iter_rows(values_only=True))
    start = next((i for i, r in enumerate(rows) if _is_header(r)), None)
    if start is None:
        return SourceTable(path.stem, path, [], [])
    header = [str(v).strip() if v is not None else "" for v in rows[start]]
    keep = [i for i, name in enumerate(header) if name and not drop(name)]
    dropped = [name for i, name in enumerate(header) if name and i not in keep]
    data: list[tuple[int, dict[str, Cell]]] = []
    for offset, values in enumerate(rows[start + 1 :], start=start + 2):
        if all(v in (None, "") for v in values):
            continue
        record: dict[str, Cell] = {}
        for i in keep:
            v = values[i] if i < len(values) else None
            record[header[i]] = v if isinstance(v, str | int | float) or v is None else _as_cell(v)
        data.append((offset, record))
    return SourceTable(path.stem, path, [header[i] for i in keep], data, dropped, "xlsx", None)


def _as_cell(value: object) -> Cell:
    from datetime import date, datetime

    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return str(value)
