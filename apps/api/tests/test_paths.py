from pathlib import Path

import pytest

from app.paths import repo_root, synthetic_root
from app.services.data_loader import DataLoadError, load_json


def test_repo_root_resolves_to_monorepo() -> None:
    root = repo_root()

    assert (root / "data").is_dir()
    assert (root / "apps" / "api").is_dir()


def test_synthetic_root_is_under_repo_data() -> None:
    assert synthetic_root() == repo_root() / "data" / "synthetic"


def test_load_json_reads_developer_feed() -> None:
    feed = load_json("developers/siam-riverside-feed.json")

    assert feed["developer_id"] == "siam-riverside-living"


def test_load_json_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DataLoadError) as exc_info:
        load_json("missing/file.json", base_dir=tmp_path)

    assert exc_info.value.reason == "file not found"
