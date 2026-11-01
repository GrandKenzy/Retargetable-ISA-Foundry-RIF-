"""Canonical command-line entrypoint for every RIF tool."""

from __future__ import annotations

import sys

from rif_tools.cli import main as _main


def main(argv: list[str] | None = None) -> int:
    """Dispatch pack, library, PCP-I, storage, inspection, and MIR tools."""

    return _main(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
