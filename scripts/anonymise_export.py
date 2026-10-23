"""Anonymise a factory export before it is used: see cip_connectors.anonymise.

    uv run python scripts/anonymise_export.py <export folder> <output folder> --key-file <file>

Personal columns and columns the mapping does not read are dropped; codes and names get stable
pseudonyms; numbers and times are kept. The key file is created on the first run (keep it with
the client: the same key gives the same pseudonyms on the next export). Neither the output nor
the key may be inside this repository: real data never enters the repo.
"""

import argparse
import os
import secrets
import sys
from pathlib import Path

from cip_connectors.anonymise import AnonymiseError, anonymise_export
from cip_connectors.importer import import_export
from cip_connectors.mapping import load_mapping

REPO = Path(__file__).resolve().parents[1]
GENERIC = REPO / "packages" / "connectors" / "mappings" / "generic" / "mapping.yaml"


def _inside_repo(path: Path) -> bool:
    return path.resolve().is_relative_to(REPO)


def _key(path: Path) -> bytes:
    if path.exists():
        return bytes.fromhex(path.read_text().strip())
    key = secrets.token_bytes(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key.hex() + "\n")
    os.chmod(path, 0o600)
    print(f"New key written to {path}. Keep it with the client; do not share it.")
    return key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("export", type=Path, help="folder with the client's export files")
    parser.add_argument("out", type=Path, help="new folder for the anonymised export")
    parser.add_argument("--key-file", type=Path, required=True, help="pseudonym key (made if new)")
    parser.add_argument("--mapping", type=Path, default=GENERIC, help="mapping of this export")
    parser.add_argument(
        "--standard", type=Path, help="also import the anonymised export into this new folder"
    )
    args = parser.parse_args(argv)
    targets = [("output folder", args.out), ("key file", args.key_file)]
    if args.standard:
        targets.append(("standard folder", args.standard))
    for name, path in targets:
        if _inside_repo(path):
            print(f"Refused: the {name} {path} is inside the repository.", file=sys.stderr)
            return 2
    if not args.export.is_dir():
        print(f"No export folder at {args.export}.", file=sys.stderr)
        return 2
    for folder in (args.out, args.standard):
        if folder and folder.exists() and any(folder.iterdir()):
            print(f"Refused: {folder} is not empty; choose a new folder.", file=sys.stderr)
            return 2
    try:
        report = anonymise_export(
            args.export, load_mapping(args.mapping), args.out, _key(args.key_file)
        )
    except AnonymiseError as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1
    for name, f in report.files.items():
        print(
            f"{name}: {f.rows} rows; pseudonymised {', '.join(f.pseudonymised) or '-'}; "
            f"dropped {', '.join(f.dropped_personal + f.dropped_unused) or '-'}"
        )
    if report.not_copied:
        print(f"Not copied (the mapping does not read them): {', '.join(report.not_copied)}")
    print(f"Done: {args.out} (with mapping.yaml and anonymise_report.json).")
    if args.standard:
        anon = load_mapping(args.out / "mapping.yaml")
        plant = {
            "plant_code": "PLANT-X",
            "name": "Anonymised plant",
            "timezone_iana": anon.timezone,
        }
        imported = import_export(args.out, anon, args.standard, plant)
        print(
            f"Imported into {args.standard}: {sum(imported.rows_written.values())} rows, "
            f"{len(imported.row_errors)} rejected, missing: "
            f"{', '.join(imported.missing_sources + imported.missing_required) or 'nothing'}."
        )
        print(
            f"Next: uv run python -m constraint_engine.diagnose {args.standard} --section quality"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
