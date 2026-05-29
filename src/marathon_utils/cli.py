"""Unified CLI for marathon-utils.

Usage:
    marathon-utils extract maps      <Map.scen>     <out-dir>
    marathon-utils extract sounds    <Sounds.sndz>  <out-dir>
    marathon-utils extract shapes    <Shapes.shps>  <out-dir>
    marathon-utils extract physics   <Physics.phys> <out-dir>
    marathon-utils extract strings   <Marathon.appl><out-dir>
    marathon-utils extract patches   <pack.patch>   <out-dir>
    marathon-utils extract terminals <Map.sceA|Marathon.appl> <out-dir>
    marathon-utils extract images    <Images.imgA>  <out-dir>
    marathon-utils visualize         <Map.scen>     <out-dir>
    marathon-utils marines           <Shapes.shpA>  <out-dir>

Run `marathon-utils <subcommand> --help` for details.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

# Extract kinds that need Pillow — surface a friendly hint if it's missing.
_NEEDS_PILLOW = {"images", "patches", "terminals", "shapes"}


def _cmd_extract(args: argparse.Namespace) -> int:
    kind = args.kind
    src = Path(args.source)
    dst = Path(args.dest)
    if not src.exists():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 2

    try:
        mod = importlib.import_module(f".{kind}", package=__package__)
    except ImportError as e:
        if kind in _NEEDS_PILLOW:
            print(f"ERROR: '{kind}' needs Pillow installed: {e}", file=sys.stderr)
            print("  pip install py-marathon-utils[images]", file=sys.stderr)
            return 3
        raise

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


def _cmd_marines(args: argparse.Namespace) -> int:
    src = Path(args.source)
    dst = Path(args.dest)
    if not src.exists():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 2
    try:
        from . import samsara as mod
    except ImportError as e:  # pragma: no cover
        print(f"ERROR: marine composer needs Pillow installed: {e}", file=sys.stderr)
        print("  pip install py-marathon-utils[images]", file=sys.stderr)
        return 3
    result = mod.compose_marines(src, dst, full_animation=args.full_animation)
    print(f"Composited {result['count']} marine sprites "
          f"({result['colors']} colors) to {dst}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="marathon-utils",
        description="Read Bungie Marathon / Aleph One data files (M1 focus).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("extract", help="extract one of the Marathon data files")
    ex.add_argument("kind", choices=["maps", "sounds", "shapes", "physics",
                                      "strings", "patches", "terminals", "images"],
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

    mr = sub.add_parser("marines",
                        help="composite Marathon marine player sprites (Samsara helper)")
    mr.add_argument("source", help="path to a Shapes file (uses collection 6)")
    mr.add_argument("dest", help="output directory")
    mr.add_argument("--full-animation", action="store_true",
                    help="emit every animation frame (~23k PNGs) instead of one per view")
    mr.set_defaults(func=_cmd_marines)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
