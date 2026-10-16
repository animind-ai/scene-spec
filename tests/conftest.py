import copy
from pathlib import Path

import pytest

from scene_spec.loader import load_file

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "s67-p01.scene.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def example() -> dict:
    """完整示例的一份可随意修改的副本。"""
    return copy.deepcopy(load_file(EXAMPLE))


def minimal_insight() -> dict:
    """一支能通过检查的最小洞察短视频。"""
    return {
        "spec": "0.1",
        "meta": {
            "id": "ep21", "title": "勾股定理", "line": "insight", "episode": 21,
            "author": "Boxi Yu", "license": "CC-BY-4.0",
        },
        "pedagogy": {
            "insight": "四个三角形换个摆法，空白处从 c² 变成 a²+b²",
            "misconception": "a+b=c",
            "non_example": "钝角时拼不上",
            "status": "proof",
            "landing": "Landing",
        },
        "objects": {
            "wrong": {"type": "math", "tex": "a+b=c", "role": "NO", "in": "side"},
            "law": {"type": "math", "tex": "a^2+b^2=c^2", "role": "HL", "in": "side"},
            "big": {"widget": "area_model", "kind": "square", "side": "a+b", "in": "stage"},
        },
        "beats": [
            {"id": "Hook", "shows": "misconception",
             "say": [{"id": "s1", "pace": "ask", "text": "斜边等于{@w} a 加 b 吗？"}],
             "do": [{"at": "s1@w", "act": "show", "target": "wrong"},
                    {"after": "prev", "act": "cross", "target": "wrong"}]},
            {"id": "Predict", "pause": {"type": "predict", "prompt": "空白处会变成什么？", "hold": 3}},
            {"id": "Rearrange", "say": [{"pace": "normal", "text": "挪一挪。"}],
             "do": [{"at": 0, "act": "slide", "target": "big", "args": {"layout": "two_rectangles"}}]},
            {"id": "NonExample", "shows": "non_example", "say": [{"pace": "normal", "text": "换成钝角试试。"}]},
            {"id": "Landing", "shows": "landing", "say": [{"pace": "slow", "text": "所以 a 方加 b 方等于 c 方。"}],
             "do": [{"at": 0, "act": "transform", "from": "big", "to": "law", "match": "shape"}]},
        ],
    }


@pytest.fixture
def insight() -> dict:
    return minimal_insight()
