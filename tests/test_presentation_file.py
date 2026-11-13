"""A tool's presentation comes from its own presentation.json (TO DO FL-134,
13 November 2026), so a wording change is that tool's deploy and no longer a
shared release that restarts all ten services."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from phronon_common.registry import PRESENTATIONS, presentation_from_file  # noqa: E402


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "presentation.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _as_file(key: str) -> dict:
    p = PRESENTATIONS[key]
    return {"key": key, "tagline": p.tagline, "blurb": p.blurb, "audience": p.audience,
            "duration": p.duration, "how": list(p.how)}


@pytest.mark.parametrize("key", sorted(PRESENTATIONS))
def test_a_file_reads_back_as_the_same_presentation(tmp_path, key):
    assert presentation_from_file(_write(tmp_path, _as_file(key)), key) == PRESENTATIONS[key]


def test_a_file_for_another_tool_is_refused(tmp_path):
    with pytest.raises(ValueError, match="written for 'layoff', read for 'whiteout'"):
        presentation_from_file(_write(tmp_path, _as_file("layoff")), "whiteout")


@pytest.mark.parametrize("change", [
    {"tagline": ""}, {"how": []}, {"how": "one sentence"}, {"extra": "x"},
])
def test_a_file_with_a_missing_or_empty_field_is_refused(tmp_path, change):
    data = {**_as_file("layoff"), **change}
    with pytest.raises(ValueError):
        presentation_from_file(_write(tmp_path, data), "layoff")
    data = _as_file("layoff")
    del data["blurb"]
    with pytest.raises(ValueError, match="needs exactly the fields"):
        presentation_from_file(_write(tmp_path, data), "layoff")
