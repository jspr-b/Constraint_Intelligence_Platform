"""Generate a synthetic plant: ``uv run python -m constraint_engine.synthetic CONFIG OUT_DIR``."""

import argparse
import sys

from constraint_engine.synthetic.config import load_config
from constraint_engine.synthetic.model import simulate
from constraint_engine.synthetic.writer import write_plant


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="constraint_engine.synthetic")
    parser.add_argument("config", help="plant YAML config")
    parser.add_argument("out_dir", help="directory to write the standard layout into")
    args = parser.parse_args(argv)
    root = write_plant(simulate(load_config(args.config)), args.out_dir)
    print(f"wrote {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
