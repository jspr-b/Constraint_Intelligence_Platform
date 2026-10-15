"""Write JSON Schema for every model: ``uv run python -m cip_schema.export``."""

import json
from pathlib import Path

from cip_schema.registry import MODELS

OUT_DIR = Path(__file__).resolve().parents[2] / "json"


def render() -> dict[str, str]:
    """JSON Schema text per file name, deterministic."""
    return {
        f"{name}.schema.json": json.dumps(model.model_json_schema(), indent=2, sort_keys=True)
        + "\n"
        for name, model in sorted(MODELS.items())
    }


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    rendered = render()
    for stale in OUT_DIR.glob("*.schema.json"):
        if stale.name not in rendered:
            stale.unlink()
    for name, text in rendered.items():
        (OUT_DIR / name).write_text(text)
    print(f"wrote {len(rendered)} schemas to {OUT_DIR}")


if __name__ == "__main__":
    main()
