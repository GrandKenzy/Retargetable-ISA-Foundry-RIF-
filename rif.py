"""Compatibility wrapper; use ``main.py`` as the canonical RIF entrypoint."""

from __future__ import annotations

import sys

from rif_tools.cli import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
