"""clip 对象：素材、裁切、主讲区。"""

from pathlib import Path

from scene_spec import check

ROOT = Path(__file__).resolve().parents[1]
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x04\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def codes(doc, **kwargs):
    return check(doc, **kwargs).codes()


def with_plate(doc, **fields):
    plate = {
        "type": "clip", "src": "hook.mp4", "kind": "video", "content_kind": "plate",
        "fit": "cover", "in": "side",
    }
    plate.update(fields)
    doc["objects"]["plate"] = plate
    hook = next(b for b in doc["beats"] if b["id"] == "Hook")
    hook["do"].insert(0, {"at": "s1", "act": "show", "target": "plate"})
    return doc


def test_hook_plate_passes(insight):
    with_plate(insight, **{"in": "stage"})
    predict = next(b for b in insight["beats"] if b["id"] == "Predict")
    predict["do"] = [{"at": 0, "act": "hide", "target": "plate"}]
    assert codes(insight) == []


def test_stage_clip_blocks_explanation(insight):
    with_plate(insight, **{"in": "stage"})
    found = [i for i in check(insight).issues if i.code == "SS474"]
    assert [i.path for i in found] == ["beats[2]", "beats[3]", "beats[4]"]
    assert "explain: allow" in found[0].message


def test_explain_allow_keeps_stage_clip(insight):
    with_plate(insight, **{"in": "stage", "explain": "allow"})
    assert "SS474" not in codes(insight)


def test_beat_plate_allow_is_per_beat(insight):
    with_plate(insight, **{"in": "stage"})
    next(b for b in insight["beats"] if b["id"] == "Rearrange")["plate"] = "allow"
    found = [i.path for i in check(insight).issues if i.code == "SS474"]
    assert found == ["beats[3]", "beats[4]"]


def test_hook_role_is_not_an_explanation(insight):
    with_plate(insight, **{"in": "stage"})
    for beat in insight["beats"]:
        if beat["id"] != "Hook":
            beat["role"] = "hook"
    assert "SS474" not in codes(insight)


def test_inset_and_side_do_not_occupy_stage(insight):
    with_plate(insight, **{"in": "stage", "size": {"max_width": 0.4, "max_height": 0.4}})
    assert "SS474" not in codes(insight)
    insight["objects"]["plate"]["size"] = {"max_width": 0.9, "max_height": 0.4}
    assert "SS474" in codes(insight)
    del insight["objects"]["plate"]["size"]
    insight["objects"]["plate"]["in"] = "footer"
    assert "SS474" not in codes(insight)


def test_full_bleed_without_region_occupies_stage(insight):
    with_plate(insight, fit="cover")
    del insight["objects"]["plate"]["in"]
    assert "SS474" in codes(insight)


def test_content_kind_rejects_text_and_unknown(insight):
    with_plate(insight, content_kind="formula")
    report = check(insight)
    assert report.codes() == ["SS471"]
    assert "text / math" in report.errors[0].message
    insight["objects"]["plate"]["content_kind"] = "caption"
    assert codes(insight) == ["SS471"]
    insight["objects"]["plate"]["content_kind"] = "bloop"
    assert codes(insight) == ["SS471"]
    insight["objects"]["plate"]["content_kind"] = "simulation"
    assert codes(insight) == []


def test_frames_need_fps(insight):
    with_plate(insight, kind="frames", src="frames")
    assert codes(insight) == ["SS470"]
    insight["objects"]["plate"]["fps"] = 12
    assert codes(insight) == []


def test_src_missing_or_wrong_type(insight, tmp_path):
    with_plate(insight, src="missing.mp4")
    assert codes(insight) == []  # 没给素材根，不查文件在不在
    assert "SS472" in codes(insight, root=tmp_path)
    video = tmp_path / "hook.mov"
    video.write_bytes(b"mov")
    insight["objects"]["plate"]["src"] = "hook.mov"
    assert "SS472" not in codes(insight, root=tmp_path)
    insight["objects"]["plate"]["src"] = "hook.mov"
    insight["objects"]["plate"]["kind"] = "frames"
    insight["objects"]["plate"]["fps"] = 24
    assert codes(insight, root=tmp_path) == ["SS472"]
    frames = tmp_path / "frames"
    frames.mkdir()
    insight["objects"]["plate"]["src"] = "frames"
    assert any(c == "SS472" for c in codes(insight, root=tmp_path))
    (frames / "000.png").write_bytes(PNG)
    (frames / "notes.txt").write_text("no")
    assert codes(insight, root=tmp_path) == []
    (frames / "000.png").unlink()
    (frames / "shot.JPEG").write_bytes(PNG)
    assert codes(insight, root=tmp_path) == []


def test_trim_order_and_duration(insight, tmp_path, monkeypatch):
    with_plate(insight, trim={"in": 1.5, "out": 1.5})
    assert codes(insight) == ["SS473"]
    insight["objects"]["plate"]["trim"] = {"in": 0.2, "out": 1.0}
    assert codes(insight) == []  # 探不到时长，只查先后

    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "a.png").write_bytes(PNG)
    (frames / "b.png").write_bytes(PNG)
    insight["objects"]["plate"].update(kind="frames", src="frames", fps=10, trim={"out": 0.5})
    assert "SS473" in codes(insight, root=tmp_path)  # 2 帧 / 10 fps = 0.2s
    insight["objects"]["plate"]["trim"] = {"in": 0.0, "out": 0.2}
    assert codes(insight, root=tmp_path) == []

    (tmp_path / "hook.mp4").write_bytes(b"mp4")
    monkeypatch.setattr("scene_spec.clips.ffprobe_duration", lambda path: 1.25)
    insight["objects"]["plate"].update(kind="video", src="hook.mp4", trim={"in": 0.5, "out": 2})
    del insight["objects"]["plate"]["fps"]
    report = check(insight, root=tmp_path)
    assert report.codes() == ["SS473"]
    assert "1.250" in report.errors[0].message
    insight["objects"]["plate"]["trim"] = {"in": 0.5, "out": 1.25}
    assert codes(insight, root=tmp_path) == []


def test_clip_schema_edges(insight):
    with_plate(insight, fit="zoom")
    assert codes(insight) == ["SS100"]
    insight["objects"]["plate"]["fit"] = "stretch"
    insight["objects"]["plate"]["end"] = "bounce"
    assert "SS100" in codes(insight)
    insight["objects"]["plate"]["end"] = "loop"
    insight["objects"]["plate"]["opacity"] = 1.2
    assert "SS100" in codes(insight)
    insight["objects"]["plate"]["opacity"] = 0
    insight["objects"]["plate"]["text"] = "烤进去的字"
    assert "SS100" in codes(insight)


def test_example_clip_scene_passes():
    from scene_spec import check_file

    report = check_file(ROOT / "examples" / "clip-hook.scene.yaml")
    assert report.issues == [], report.issues


def test_group_show_reveals_child_clip(insight):
    with_plate(insight, **{"in": "stage"})
    insight["objects"]["bundle"] = {"type": "group", "children": ["plate"], "in": "stage"}
    hook = next(b for b in insight["beats"] if b["id"] == "Hook")
    hook["do"][0] = {"at": "s1", "act": "show", "target": "bundle"}
    assert "SS474" in codes(insight)
