#!/usr/bin/env python3
"""Generate (or verify) data/demo_scenario.json.

All profiles are SIMULATED: synthetic, not measurements, not validated forecasts.

Usage (from the repository root):
    python scripts/generate_demo_data.py            # write data/demo_scenario.json
    python scripts/generate_demo_data.py --check    # exit 1 if the file is out of date
    python scripts/generate_demo_data.py --out path/to/file.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.scenario_generator import generate_demo_file  # noqa: E402
from app.schemas import ScenarioRequest  # noqa: E402


def render() -> str:
    data = generate_demo_file()
    for weather, scenario in data["scenarios"].items():  # fail loudly if the contract is violated
        ScenarioRequest.model_validate(scenario)
    return json.dumps(data, indent=1) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "demo_scenario.json")
    parser.add_argument("--check", action="store_true", help="verify the file instead of writing it")
    args = parser.parse_args()

    text = render()
    if args.check:
        if not args.out.is_file() or args.out.read_text(encoding="utf-8") != text:
            print(f"{args.out} is missing or out of date; run without --check to regenerate.")
            return 1
        print(f"{args.out} is up to date.")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"Wrote {args.out} ({len(text):,} bytes): scenarios 'clear' and 'cloudy' (SIMULATED data).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
