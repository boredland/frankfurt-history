"""Shared fixtures: load the standalone pipeline scripts as importable modules."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script(name: str, relative_path: str) -> ModuleType:
    """Import a standalone script from scripts/ as a module."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def merge_mod() -> ModuleType:
    return load_script("merge_script", "scripts/merge.py")


@pytest.fixture(scope="session")
def geojson_mod() -> ModuleType:
    return load_script("geojson_script", "scripts/geojson.py")
