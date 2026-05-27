"""Unified CLI for marathon-utils.

Usage:
    marathon-utils extract maps    <Map.scen>    <out-dir>
    marathon-utils extract sounds  <Sounds.sndz> <out-dir>
    marathon-utils extract shapes  <Shapes.shps> <out-dir>
    marathon-utils extract physics <Physics.phys> <out-dir>
    marathon-utils visualize       <Map.scen>    <out-dir>

Run `marathon-utils <subcommand> --help` for details.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cmd_extract(args: argparse.Namespace) -> int:
    kind = args.kind
    src = Path(args.source)
    dst = Path(args.dest)
    if not src.exists():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 2

    if kind == "maps":
        from . import maps as mod
    elif kind == "sounds":
        from . import sounds as mod
    elif kind == "physics":
        from . import physics as mod
    elif kind == "strings":
        from . import strings as mod
    elif kind == "patches":
        try:
            from . import patches as mod
        except ImportError as e:  # pragma: no cover
            print(f"ERROR: patches reader needs Pillow: {e}", file=sys.stderr)
            return 3
    elif kind == "shapes":
        try:
            from . import shapes as mod
        except ImportError as e:  # pragma: no cover - friendly hint
            print(f"ERROR: shapes extraction needs Pillow installed: {e}", file=sys.stderr)
            print("  pip install py-marathon-utils[images]", file=sys.stderr)
            return 3
    else:  # argparse should prevent this
        print(f"ERROR: unknown extract kind {kind!r}", file=sys.stderr)
        return 2

    result = mod.extract(src, dst)
    print(json.dumps(result, indent=2, default=str)[:2000])
    if isinstance(result, dict) and len(json.dumps(result, default=str)) > 2000:
        print("... (truncated; see manifest.json in output dir)")
    return 0


def _cmd_visualize(args: argparse.Namespace) -> int:
    src = Path(args.source)
    dst = Path(args.dest)
    if not src.exists():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 2
    try:
        from . import visualize as mod
    except ImportError as e:  # pragma: no cover
        print(f"ERROR: visualize needs Pillow installed: {e}", file=sys.stderr)
        print("  pip install py-marathon-utils[images]", file=sys.stderr)
        return 3
    result = mod.render_all_levels(src, dst, scale=args.scale)
    print(f"Rendered {result['count']} level PNGs to {dst}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="marathon-utils",
        description="Read Bungie Marathon / Aleph One data files (M1 focus).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("extract", help="extract one of the Marathon data files")
    ex.add_argument("kind", choices=["maps", "sounds", "shapes", "physics", "strings", "patches"],
                    help="which file type to extract")
    ex.add_argument("source", help="path to the input file (e.g. Map.scen)")
    ex.add_argument("dest", help="output directory")
    ex.set_defaults(func=_cmd_extract)

    vz = sub.add_parser("visualize", help="render top-down map PNGs from Map.scen")
    vz.add_argument("source", help="path to Map.scen")
    vz.add_argument("dest", help="output directory")
    vz.add_argument("--scale", type=float, default=0.05,
                    help="pixels per world unit (default 0.05)")
    vz.set_defaults(func=_cmd_visualize)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
