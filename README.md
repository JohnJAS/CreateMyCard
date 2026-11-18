# CreateMyCard

本项目为小艺 App 提供 AI 桌面卡片生成与编辑能力。云侧将用户需求转换为 HarmonyOS A2UI Form
卡片，配套工具用于接口调试、批量评估、浏览器预览和真机渲染验证。

## 目录说明

| 目录 | 用途 |
| --- | --- |
| [.github/](.github/) | GitHub Actions 配置，当前包含微服务 PR 自动测试。 |
| [widget_service/](widget_service/) | 云侧 Python 微服务，负责生成与编辑编排、模型调用、协议转换、校验和产物保存。 |
| [debug_tools/](debug_tools/) | 开发调试工作台，包含接口调试、端到端调试、批跑、评分后处理、设备调试和测试。 |
| [render/](render/) | 卡片渲染 SDK、独立浏览器渲染平台，以及渲染开发所需的脚本、共享代码和参考资料。 |
| [resources/](resources/) | 共用素材资源，图片和图标位于 `base/media/`，供卡片及渲染工具使用。 |
| [skills/](skills/) | 主 Agent 使用的在线编排 Skill，以及独立离线生成和调试用的离线 Skill。 |
| [docs/](docs/) | 云侧方案、能力版本管理、校验器专项设计及排障资料。 |

### 云侧服务

- `widget_service/cloud/` 包含服务入口、业务实现、能力注册表、协议配置与模型提示词。
- `widget_service/tests/` 存放微服务回归测试。
- `widget_service/tools/`、`sql/` 和 `docs/` 分别存放服务辅助工具、数据库脚本和服务文档。
- 依赖与运行方式见 [微服务 README](widget_service/README.md)。

### 调试与渲染

- `debug_tools/platform/` 是统一调试平台前端，`end_to_end_debug/` 提供端到端调试后端与会话界面。
- `debug_tools/batch_testing/`、`Datasets/` 和 `postprocess_plugins/` 分别承载批跑、数据集和后处理插件。
- `debug_tools/interface_debug/`、`card_renderer/` 提供接口调试与卡片渲染功能。
- `debug_tools/device_debug/` 负责设备操作，`a2ui_render/` 是配套 HarmonyOS 真机渲染工程。
- `debug_tools/tests/` 集中存放调试工具测试，`scripts/` 存放素材同步等开发脚本。
- `render/genui-sdk/` 提供渲染运行时，`render/platform/` 提供独立卡片预览页面。

调试工具的 Python 项目配置、锁文件与虚拟环境分别位于 `debug_tools/pyproject.toml`、
`debug_tools/uv.lock` 和 `debug_tools/.venv/`。从仓库根目录执行以下命令安装并启动。

```shell
uv sync --project debug_tools
uv run --project debug_tools debug_tools
```

详细环境与使用说明见 [调试工具 README](debug_tools/README.md)、
[调试平台技术方案](debug_tools/调试平台技术方案.md)、
[调试平台运行规范](debug_tools/调试平台运行规范.md)和
[独立渲染器 README](render/platform/README.md)。

### Skill

- `skills/harmony-card-generation-online/` 负责在线云侧工具编排。
- `skills/harmony-card-generation-offline/` 用于独立离线生成、修复和评审，相关资料仅作为离线与历史参考。

## 项目文档

- [云侧方案设计](docs/云侧方案设计.md)是项目方案与接口约定的权威来源。
- [校验、重试与兜底机制入门指南](docs/校验、重试与兜底机制入门指南.md)介绍全链路校验、失败处理、重试与排障。
- [AGENTS.md](AGENTS.md)维护项目协作要求、职责边界及代码验证规范。
