"""图片主题固定构图、完整按钮避让和冻结前景合同。"""

import hashlib
from pathlib import Path

import pytest

from services import post_layout_theme as themes
from services.theme_content_regions import button_ids


def test_current_subject_and_texture_assets_are_active_and_present():
    root = Path(__file__).resolve().parents[2]
    expected = {"photos": 31, "texturePhotos": 15,
                "subjectlessWidePhotos": 0, "squareExpansions": 0}
    for key, count in expected.items():
        entries = themes.registered_themes(key)
        assert isinstance(entries, list) and len(entries) == count
        for entry in entries:
            src = entry.get("src")
            assert isinstance(src, str) and src.startswith("resources/base/media/")
            assert (root / src).is_file()
    assert all(p.get("id", "").startswith("photo-ux-")
               for p in themes.registered_themes("photos"))
    photos = themes.registered_themes("photos", include_disabled=True)
    photos.extend(themes.registered_themes("texturePhotos", include_disabled=True))
    expected_paths = {root / entry.get("src") for entry in photos}
    assert set((root / "resources/base/media").glob("bg_*")) == expected_paths


@pytest.mark.parametrize("entry", [
    *themes.registered_themes("photos", include_disabled=True),
    *themes.registered_themes("texturePhotos", include_disabled=True),
], ids=lambda entry: entry.get("id"))
def test_photo_assets_match_delivery_hash_and_preserve_source_record(entry):
    src = entry.get("src")
    assert isinstance(src, str)
    payload = (Path(__file__).resolve().parents[2] / src).read_bytes()
    assert payload.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n"))
    metadata = entry.get("source", {})
    assert hashlib.sha256(payload).hexdigest() == metadata.get("assetSha256")
    assert len(payload) == metadata.get("assetBytes")
    original_hash = metadata.get("sourceSha256")
    assert isinstance(original_hash, str)
    assert len(original_hash) == 64
    assert metadata.get("originalSize")
    assert metadata.get("assetSize")


def test_capsules_and_round_buttons_both_occupy_the_whole_area():
    def node(identity, width):
        return {"id": identity, "component": "Button", "onClick": [{"call": "open"}],
                "styles": {"width": width, "height": 30, "borderRadius": 15}}

    assert button_ids([node("pill", 120), node("circle", 30)]) == ["pill", "circle"]


def test_subject_avoidance_cannot_use_legacy_capsule_exemptions():
    photo = {"size": "2x2", "business": "weather", "subjectBounds": [.6, .1, .4, .6]}
    content = {"id": "title", "rect": [.1, .1, .3, .1]}
    capsule = {"id": "pill_text", "rect": [.1, .5, .8, .2]}
    evidence = {"complete": True, "occupied": [content, capsule], "subjectAvoidance": [content]}
    assert "冲突" in themes._photo_geometry_reason(photo, evidence)
    changed = {**evidence, "subjectAvoidance": [capsule]}
    assert "冲突" in themes._photo_geometry_reason(photo, changed)
    assert themes._photo_geometry_reason(photo, {**evidence, "complete": False}) is not None
