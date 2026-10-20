#!/usr/bin/env python3
"""Prepare an unsigned local Firefox companion from the shared runtime build.

Run the extension build first. The output directory must not exist; this utility
never replaces an installed extension or signs, uploads, or publishes anything.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from companion_install import prepare  # noqa: E402

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/firefox-companion")
    args = parser.parse_args()
    result = prepare(ROOT / "chrome_extensions/incremento_companion", args.output.absolute())
    print(f"Local Firefox companion: {result}")
    print("Load its manifest.json from Firefox about:debugging → This Firefox → Load Temporary Add-on.")


if __name__ == "__main__":
    main()
