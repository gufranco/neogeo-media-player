from __future__ import annotations

import pytest

from neogeomedia import bake, tiercache
from tests.bakehelp import lavfi_clip, small_request


@pytest.fixture(autouse=True)
def never_touch_the_committed_store(tmp_path, monkeypatch, request):
    if request.node.get_closest_marker("reads_real_store"):
        return
    monkeypatch.setattr(tiercache, "default_store", lambda: tmp_path / "tiers.json")


@pytest.fixture(scope="session")
def synthetic_clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("bake") / "source.mp4"
    return lavfi_clip(path, "testsrc=size=640x360:rate=24:duration=1")


@pytest.fixture(scope="session")
def epoch_clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("epochs") / "source.mp4"
    return lavfi_clip(path, "testsrc=size=1280x720:rate=24:duration=8")


@pytest.fixture(scope="session")
def baked(synthetic_clip, tmp_path_factory):
    request = small_request(
        synthetic_clip,
        tmp_path_factory.mktemp("out"),
        duration=0.25,
        palette_count=8,
        keyframe_interval=8,
    )
    return bake.run(request)
