"""Reset the synthetic demo tenant: `--empty` (no plant) or `--loaded` (plants A, B and C).

    uv run python scripts/demo_reset.py --empty
    uv run python scripts/demo_reset.py --loaded

See cip_api.demo for what it does. Dev only; touches nothing but the demo tenant.
"""

import sys

from cip_api.demo import main

if __name__ == "__main__":
    sys.exit(main())
