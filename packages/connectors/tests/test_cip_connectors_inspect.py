"""Reading files as plants send them, and saying why a file cannot be read."""

from pathlib import Path

import pytest

from cip_connectors.privacy import personal_column_rule
from cip_connectors.readers import choose_delimiter, inspect_file, read_csv

DROP = personal_column_rule(("Medewerker",))
ROOT = Path(__file__).resolve().parents[3]
EXPORT = ROOT / "data" / "synthetic" / "plant_a" / "erp_export" / "clean"


def write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_windows_1252_is_read_and_reported(tmp_path: Path) -> None:
    path = write(
        tmp_path, "artikelen.csv", "Artikel;Omschrijving\nF-200;Café frame\n".encode("cp1252")
    )
    table = read_csv(path, ";", DROP)
    assert table.encoding == "cp1252" and table.rows[0][1]["Omschrijving"] == "Café frame"


def test_utf8_with_bom(tmp_path: Path) -> None:
    path = write(tmp_path, "a.csv", "﻿Artikel;Omschrijving\nF-200;Ré\n".encode())
    table = read_csv(path, ";", DROP)
    assert table.header == ["Artikel", "Omschrijving"] and table.encoding == "utf-8"


def test_other_separator_is_detected(tmp_path: Path) -> None:
    path = write(tmp_path, "a.csv", b"Artikel,Omschrijving\nF-200,Frame\n")
    table = read_csv(path, ";", DROP)
    assert table.delimiter == "," and table.rows[0][1]["Omschrijving"] == "Frame"
    assert choose_delimiter("a;b", ";") == ";" and choose_delimiter("a\tb", ";") == "\t"


@pytest.mark.parametrize(
    ("name", "data", "problem"),
    [
        ("a.csv", b"", "empty"),
        ("a.csv", b"\n\nF-200;1\n", "no_header"),
        ("a.csv", b"\x00\x01\x02binary", "not_text"),
        ("a.csv", b"Artikel\nF-200\n", "single_column"),
        ("a.xlsx", b"not an excel file", "unreadable_excel"),
    ],
)
def test_unreadable_files_say_why(tmp_path: Path, name: str, data: bytes, problem: str) -> None:
    result = inspect_file(write(tmp_path, name, data), ";", DROP)
    assert (result.readable, result.problem) == (False, problem)


def test_inspection_of_a_real_export_never_shows_personal_values() -> None:
    result = inspect_file(EXPORT / "csv" / "mes_events.csv", ";", DROP)
    assert result.readable and result.rows > 1000 and result.delimiter == ";"
    assert "Medewerker" in result.header and result.personal_columns == ["Medewerker"]
    assert len(result.preview) == 5 and all("Medewerker" not in row for row in result.preview)


def test_inspection_of_excel() -> None:
    result = inspect_file(EXPORT / "xlsx" / "mes_events.xlsx", ";", DROP)
    assert (
        result.readable and result.encoding == "xlsx" and result.personal_columns == ["Medewerker"]
    )
    assert all("Medewerker" not in row for row in result.preview)
