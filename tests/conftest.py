"""Pytest fixtures and skip helpers.

Many integration tests need real Marathon binary files. We don't bundle Bungie
IP in the repo, so tests that require sample data check environment variables
(or default local paths) and skip if absent. Each Marathon version has its
own fixture so tests can target whichever they need.

Set any of these env vars (each pointing to the corresponding game's data
directory) to enable that version's integration tests:

    MARATHON_SAMPLE_DATA      -- M1 (Marathon-20250829)
    MARATHON2_SAMPLE_DATA     -- M2 (Marathon2-20250829)
    MARATHON_INFINITY_SAMPLE_DATA  -- Infinity (MarathonInfinity-20250829)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


def _resolve(env_var: str, defaults: list[Path], required_filename: str) -> Path | None:
    env = os.environ.get(env_var)
    if env:
        p = Path(env).expanduser().resolve()
        return p if p.is_dir() else None
    for candidate in defaults:
        if candidate.is_dir() and (candidate / required_filename).is_file():
            return candidate
    return None


def _m1_root() -> Path | None:
    return _resolve(
        "MARATHON_SAMPLE_DATA",
        [
            Path.home() / "Desktop" / "m1ue5" / "M1SOURCE" / "Marathon-20250829",
            Path("C:/Users/Dustin Kost/Desktop/m1ue5/M1SOURCE/Marathon-20250829"),
        ],
        "Map.scen",
    )


def _m2_root() -> Path | None:
    return _resolve(
        "MARATHON2_SAMPLE_DATA",
        [
            Path.home() / "Desktop" / "m1ue5" / "M2SOURCE" / "Marathon2-20250829",
            Path("C:/Users/Dustin Kost/Desktop/m1ue5/M2SOURCE/Marathon2-20250829"),
        ],
        "Map.sceA",
    )


def _mi_root() -> Path | None:
    return _resolve(
        "MARATHON_INFINITY_SAMPLE_DATA",
        [
            Path.home() / "Desktop" / "m1ue5" / "MISOURCE" / "MarathonInfinity-20250829",
            Path("C:/Users/Dustin Kost/Desktop/m1ue5/MISOURCE/MarathonInfinity-20250829"),
        ],
        "Map.sceA",
    )


@pytest.fixture(scope="session")
def sample_dir() -> Path:
    """Backward-compatible fixture pointing at the M1 sample dir."""
    root = _m1_root()
    if root is None:
        pytest.skip("set MARATHON_SAMPLE_DATA to a Marathon-20250829 dir to enable")
    return root


@pytest.fixture(scope="session")
def m2_dir() -> Path:
    root = _m2_root()
    if root is None:
        pytest.skip("set MARATHON2_SAMPLE_DATA to a Marathon2-20250829 dir to enable")
    return root


@pytest.fixture(scope="session")
def mi_dir() -> Path:
    root = _mi_root()
    if root is None:
        pytest.skip("set MARATHON_INFINITY_SAMPLE_DATA to a MarathonInfinity-20250829 dir to enable")
    return root


@pytest.fixture(scope="session")
def map_scen(sample_dir: Path) -> Path:
    p = sample_dir / "Map.scen"
    if not p.is_file():
        pytest.skip(f"Map.scen not found in {sample_dir}")
    return p


@pytest.fixture(scope="session")
def shapes_shps(sample_dir: Path) -> Path:
    p = sample_dir / "Shapes.shps"
    if not p.is_file():
        pytest.skip(f"Shapes.shps not found in {sample_dir}")
    return p


@pytest.fixture(scope="session")
def sounds_sndz(sample_dir: Path) -> Path:
    p = sample_dir / "Sounds.sndz"
    if not p.is_file():
        pytest.skip(f"Sounds.sndz not found in {sample_dir}")
    return p


@pytest.fixture(scope="session")
def m2_map(m2_dir: Path) -> Path:
    return m2_dir / "Map.sceA"


@pytest.fixture(scope="session")
def m2_shapes(m2_dir: Path) -> Path:
    return m2_dir / "Shapes.shpA"


@pytest.fixture(scope="session")
def m2_sounds(m2_dir: Path) -> Path:
    return m2_dir / "Sounds.sndA"


@pytest.fixture(scope="session")
def mi_map(mi_dir: Path) -> Path:
    return mi_dir / "Map.sceA"


@pytest.fixture(scope="session")
def mi_shapes(mi_dir: Path) -> Path:
    return mi_dir / "Shapes.shpA"


@pytest.fixture(scope="session")
def mi_sounds(mi_dir: Path) -> Path:
    return mi_dir / "Sounds.sndA"
