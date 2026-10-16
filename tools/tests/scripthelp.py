from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "scripts"
CORE_SUFFIX = ".dylib" if sys.platform == "darwin" else ".so"


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        msg = f"cannot load the script {name}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_core(source: str, out_dir: Path) -> Path:
    if shutil.which("cc") is None:
        reason = "cc not on the path, and this test builds a libretro core"
        if os.environ.get("NEOGEOMEDIA_CC_REQUIRED") == "1":
            pytest.fail(reason)
        pytest.skip(reason)
    built = out_dir / f"{Path(source).stem}{CORE_SUFFIX}"
    command = ["cc", "-shared", "-fPIC", "-O1", "-o", str(built), str(TESTS / source)]
    subprocess.run(command, check=True)
    return built
