from __future__ import annotations

import pytest

from neogeomedia import tiercache


@pytest.fixture(autouse=True)
def never_touch_the_committed_store(tmp_path, monkeypatch, request):
    if request.node.get_closest_marker("reads_real_store"):
        return
    monkeypatch.setattr(tiercache, "default_store", lambda: tmp_path / "tiers.json")
