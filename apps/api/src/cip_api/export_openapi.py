"""Write the API contract: ``uv run python -m cip_api.export_openapi [path]``."""

import json
import sys
from pathlib import Path

from cip_api.main import create_app
from cip_api.settings import Settings

DEFAULT = Path(__file__).resolve().parents[2] / "openapi.json"


def render() -> str:
    return (
        json.dumps(create_app(Settings()).openapi(), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    )


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    target.write_text(render())
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
