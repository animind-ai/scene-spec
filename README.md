# scene-spec

[中文](#中文) | [English](#english)

## 中文

数学讲解视频的场景描述格式。一支视频一个文件，写清楚讲什么、画什么、什么时候动；不写坐标，不写颜色。

本仓库包含 0.1 版的：

- **JSON Schema**：`schema/scene-spec-0.1.schema.json`
- **检查器**：受限 YAML 读取、结构检查、语义检查（引用、时间点、组件参数、教学信息）
- **示例**：`examples/s67-p01.scene.yaml`（高阶等差数列）和 `examples/s67-p02.scene.yaml`（d-等差比数列），两支完整的例题讲解视频

格式的设计说明见 [docs/design.md](docs/design.md)。渲染不在本仓库，由 [kit](https://github.com/animind-ai/kit) 负责：渲染引擎默认是 [墨线 moxian](https://github.com/animind-ai/moxian)，也可以用 `--backend manim` 切换到 Manim。

### 用法

```bash
uv sync
uv run scene-spec check examples/s67-p01.scene.yaml
```

输出示例：

```
examples/s67-p01.scene.yaml: 通过（0 个错误，0 个警告）
  统计：beats=9，sentences=37，actions=58，custom_beats=0，absolute_coords=0，unregistered_widgets=0
```

- 退出码：`0` 通过（可以有警告），`1` 有错误，`2` 用法错误。
- `--json` 以 JSON 输出，`--strict` 把警告也算作失败。

在 Python 里：

```python
from scene_spec import check_file

report = check_file("examples/s67-p01.scene.yaml")
for issue in report.issues:
    print(issue.level, issue.code, issue.path, issue.message)
```

### 检查分层

| 层 | 内容 | 代码 |
|---|---|---|
| 读取 | 受限 YAML：禁用锚点、别名、合并键、自定义标签；布尔只认 `true`/`false`；`16:9`、`0o17`、日期都按字符串读；重复的键报错 | SS000–SS003 |
| 结构 | JSON Schema | SS100 |
| 语义 | 组件参数与数据自洽、片段与书签语法、选择器和时间点能解析、动作合法、不写色值与表达式、绝对坐标规则、产品线要求的教学信息 | SS201–SS381 |
| 参数 | 场景参数 `params`、`tween` 动作、`readout` 读数、参数表达式（白名单语法、只引用声明过的参数）；按参数会经过的关键取值代入，检查几何不出界、表达式有定义（设计稿 §7.5） | SS400–SS411 |
| 分段 | `ghost` / `unghost` 残影、`step` 子步定格、`pin` 常驻公式：目标是整个对象、常驻后不能再 hide / move、残影和子步数量（设计稿 §7.6） | SS440–SS459 |

结构不通过时不运行语义检查。时间检查（旁白时长对动作）和布局检查属于后续版本。

### 开发

```bash
uv run pytest
```

### 作者与许可

作者：Boxi Yu（[@BoxiYu](https://github.com/BoxiYu)）

代码以 [MIT 许可](LICENSE)发布。示例文件中的旁白和讲解以 CC BY 4.0 发布；示例引用的题面按 `meta.sources` 标注来源。

## English

A scene description format for math explainer videos. One file per video, stating what is explained, what is drawn, and when things move; no coordinates, no colors.

This repository contains version 0.1 of:

- **JSON Schema**: `schema/scene-spec-0.1.schema.json`
- **Checker**: restricted YAML reading, structural checks, semantic checks (references, time points, widget parameters, teaching information)
- **Examples**: `examples/s67-p01.scene.yaml` (higher-order arithmetic sequences) and `examples/s67-p02.scene.yaml` (d-arithmetic-ratio sequences), two complete worked-problem videos

For the design rationale of the format, see [docs/design.md](docs/design.md). Rendering is not in this repository; it is handled by [kit](https://github.com/animind-ai/kit), whose rendering engine defaults to [moxian 墨线](https://github.com/animind-ai/moxian), with Manim available via `--backend manim`.

### Usage

```bash
uv sync
uv run scene-spec check examples/s67-p01.scene.yaml
```

Example output (the tool prints in Chinese; "通过（0 个错误，0 个警告）" = "passed (0 errors, 0 warnings)", "统计" = "stats"):

```
examples/s67-p01.scene.yaml: 通过（0 个错误，0 个警告）
  统计：beats=9，sentences=37，actions=58，custom_beats=0，absolute_coords=0，unregistered_widgets=0
```

- Exit codes: `0` passed (warnings allowed), `1` errors, `2` usage error.
- `--json` outputs JSON; `--strict` also treats warnings as failures.

In Python:

```python
from scene_spec import check_file

report = check_file("examples/s67-p01.scene.yaml")
for issue in report.issues:
    print(issue.level, issue.code, issue.path, issue.message)
```

### Check layers

| Layer | Contents | Codes |
|---|---|---|
| Reading | Restricted YAML: anchors, aliases, merge keys, and custom tags are disallowed; booleans are only `true`/`false`; `16:9`, `0o17`, and dates are all read as strings; duplicate keys are errors | SS000–SS003 |
| Structure | JSON Schema | SS100 |
| Semantics | Widget parameters and data are self-consistent, fragment and bookmark syntax, selectors and time points resolve, actions are valid, no color values or expressions, absolute-coordinate rules, teaching information required by the product line | SS201–SS381 |
| Parameters | Scene parameters `params`, `tween` actions, `readout` displays, parameter expressions (whitelisted syntax, only declared parameters referenced); substitutes the key values a parameter will pass through to check that geometry stays in bounds and expressions are defined (design doc §7.5) | SS400–SS411 |
| Segmentation | `ghost` / `unghost` afterimages, `step` sub-step freezes, `pin` persistent formulas: targets are whole objects, pinned objects can't be hidden / moved afterwards, number of afterimages and sub-steps (design doc §7.6) | SS440–SS459 |

Semantic checks don't run if the structure check fails. Timing checks (narration length vs. actions) and layout checks belong to later versions.

### Development

```bash
uv run pytest
```

### Author and license

Author: Boxi Yu ([@BoxiYu](https://github.com/BoxiYu))

The code is released under the [MIT License](LICENSE). Narration and explanations in the example files are released under CC BY 4.0; problem statements cited by the examples are attributed in `meta.sources`.
