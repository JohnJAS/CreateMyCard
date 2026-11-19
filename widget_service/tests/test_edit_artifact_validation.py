"""编辑引用授权共用产物规则，服务不再追加旧路径子串检查。"""

import json

import pytest

from services.card_validation import validate_card

OLD_ROOT = "/data/weather"
OLD_REFERENCE = "{{ ${/data/weather/current/condition} }}"
PATH_CODE = "EFFECTIVE_DATA_PATH_NOT_ALLOWED"


def _standard_dsl(content: str, kind: str = "text") -> str:
    text = {
        "id": "value",
        "component": "Text",
        "content": content,
        "styles": {"fontSize": 18, "fontColor": "#FF000000"},
    }
    root = {
        "id": "root",
        "component": "Column",
        "children": ["value"],
        "styles": {
            "width": "matchParent",
            "height": "matchParent",
            "padding": 12,
            "backgroundColor": "#FFFFFFFF",
        },
    }
    if kind == "template":
        root["children"] = {"componentId": "value", "path": OLD_ROOT + "/items"}
    if kind == "event":
        text["content"] = "天气"
        text["onClick"] = [{"call": "test", "args": {"value": content}}]
    if kind == "style":
        text["styles"] = {"fontSize": 18, "fontColor": content}
        text["content"] = "天气"
    # 未移除的首帧值不能让已取消授权的动态路径通过。
    weather = {"current": {"condition": "晴"}, "items": [{"condition": "晴"}]}
    rows = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "card",
                "catalogId": "ohos.a2ui.extended.catalog.form",
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "card",
                "root": "root",
                "components": [root, text],
            },
        },
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "card",
                "path": "/",
                "value": {
                    "data": {
                        "weather": {**weather, "today": weather},
                        "weatherBackup": weather,
                    },
                },
            },
        },
    ]
    dsl = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if kind == "escaped":
        dsl = dsl.replace("/", r"\/")
    return dsl


def _binding(root: str) -> dict:
    return {
        "capabilityId": "ViewWeather",
        "arguments": {"prefectureName": "上海市", "forecastDays": 1},
        "writeResultTo": root,
        "candidateOutputFields": ["/current/condition"],
    }


@pytest.mark.parametrize(
    ("content", "root", "kind", "location"),
    [
        pytest.param(OLD_REFERENCE, None, "text", "value/content", id="removed-with-old-data"),
        pytest.param(OLD_ROOT, None, "text", None, id="literal-path"),
        pytest.param(
            "{{ ${/data/weatherBackup/current/condition} }}",
            "/data/weatherBackup",
            "text",
            None,
            id="authorized-sibling",
        ),
        pytest.param(
            "{{ ${/data/weather/today/current/condition} }}",
            "/data/weather/today",
            "text",
            None,
            id="authorized-child",
        ),
        pytest.param(OLD_REFERENCE, None, "escaped", "value/content", id="escaped-slashes"),
        pytest.param("静态卡片", None, "text", None, id="unused-old-data"),
        pytest.param(
            "{{ ${condition} }}",
            None,
            "template",
            "root/children/path",
            id="relative-template",
        ),
        pytest.param(
            OLD_REFERENCE,
            None,
            "event",
            "value/onClick/0/args/value",
            id="event-argument",
        ),
        pytest.param(
            OLD_REFERENCE,
            None,
            "style",
            "value/styles/fontColor",
            id="style-expression",
        ),
        pytest.param(OLD_REFERENCE, OLD_ROOT, "text", None, id="inherited-binding"),
    ],
)
def test_current_binding_authorizes_parsed_references(content, root, kind, location):
    bindings = [] if root is None else [_binding(root)]
    artifact = {
        "genui": _standard_dsl(content, kind),
        "cardSpec": {
            "title": "天气",
            "description": "当前天气",
            "suggestSize": "2x2",
            "dataBindings": bindings,
        },
        "effectiveCapabilities": {
            "data": [] if root is None else ["ViewWeather"],
            "event": [],
            "asset": [],
        },
    }
    reporter = validate_card(artifact=artifact)
    errors = [item for item in reporter.diagnostics if item.code == PATH_CODE]
    if location is None:
        assert not errors
    else:
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert errors[0].file_kind == "genui"
        assert errors[0].line == 2
        assert errors[0].json_pointer == "/updateComponents/componentsById/" + location
