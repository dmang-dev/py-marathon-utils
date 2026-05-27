"""Pytest fixtures and skip helpers.

Many integration tests need real Marathon binary files. We don't bundle Bungie
IP in the repo, so tests that require sample data check the
`MARATHON_SAMPLE_DATA` env var (or a default local path) and skip if absent.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


def _sample_root() -> Path | None:
    """Resolve the directory holding Map.scen / Shapes.shps / Sounds.sndz."""
    env = os.environ.get("MARATHON_SAMPLE_DATA")
    if env:
        p = Path(env).expanduser().resolve()
        return p if p.is_dir() else None

    # Default convenience locations
    for candidate in (
        Path.home() / "Desktop" / "m1ue5" / "M1SOURCE" / "Marathon-20250829",
        Path("C:/Users/Dustin Kost/Desktop/m1ue5/M1SOURCE/Marathon-20250829"),
    ):
        if candidate.is_dir() and (candidate / "Map.scen").is_file():
            return candidate
    return None


@pytest.fixture(scope="session")
def sample_dir() -> Path:
    root = _sample_root()
    if root is None:
        pytest.skip("set MARATHON_SAMPLE_DATA to a Marathon-20250829 dir to enable")
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
