# scene-spec

数学讲解视频的场景描述格式。一支视频一个文件，写清楚讲什么、画什么、什么时候动；不写坐标，不写颜色。

本仓库包含 0.1 版的：

- **JSON Schema**：`schema/scene-spec-0.1.schema.json`
- **检查器**：受限 YAML 读取、结构检查、语义检查（引用、时间点、组件参数、教学信息）
- **示例**：`examples/s67-p01.scene.yaml`（高阶等差数列）和 `examples/s67-p02.scene.yaml`（d-等差比数列），两支完整的例题讲解视频

格式的设计说明见 [docs/design.md](docs/design.md)。渲染不在本仓库，由 `kit`（Manim 运行时）负责。

## 用法

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

## 检查分层

| 层 | 内容 | 代码 |
|---|---|---|
| 读取 | 受限 YAML：禁用锚点、别名、合并键、自定义标签；布尔只认 `true`/`false`；`16:9`、`0o17`、日期都按字符串读；重复的键报错 | SS000–SS003 |
| 结构 | JSON Schema | SS100 |
| 语义 | 组件参数与数据自洽、片段与书签语法、选择器和时间点能解析、动作合法、不写色值与表达式、绝对坐标规则、产品线要求的教学信息 | SS201–SS381 |
| 分段 | `ghost` / `unghost` 残影、`step` 子步定格、`pin` 常驻公式：目标是整个对象、常驻后不能再 hide / move、残影和子步数量（设计稿 §7.6） | SS440–SS459 |

结构不通过时不运行语义检查。时间检查（旁白时长对动作）和布局检查属于后续版本。

## 开发

```bash
uv run pytest
```

## 作者与许可

作者：Boxi Yu（[@BoxiYu](https://github.com/BoxiYu)）

代码以 [MIT 许可](LICENSE)发布。示例文件中的旁白和讲解以 CC BY 4.0 发布；示例引用的题面按 `meta.sources` 标注来源。
