# scene-spec 设计稿 v0.1

> 状态：设计已定（第 13 节），尚未实现。
> 作者：Boxi Yu · 2026-10-16
> 归属仓库：`animind-ai/scene-spec`（MIT）

scene-spec 是一份**描述一支数学讲解视频"讲什么、画什么、什么时候动"的文件格式**。人和模型只写这份文件，由 `kit` 把它编译成 Manim 场景，由 `voice` 合成旁白，由 `qa` 在渲染前后做检查。

---

## 1. 为什么要有这一层

拿 §6.7 第 01 支（`highSchool/lessons/sec6-7/p01/`）来看，现在一支视频由三部分组成：

| 现在 | 问题 |
|---|---|
| `build.py` 里的 `BEATS`：每个场景若干句 (语气, 旁白) | 旁白和画面分在两个文件，靠"第几句"对齐，插一句话就要改两处 |
| `scenes.py` 里 544 行 Manim 代码，坐标手写（`XS = [-4.2 + 1.36 * i ...]`、`Y_A = 1.05`） | 版式靠人调，模型生成时最容易出重叠、出框；换个题就要重写 |
| 颜色直接用色卡名（`FOREST`、`SAGE`、`GOLD`） | 颜色的含义只写在注释里，换主题要改代码 |

画面跟不上旁白（`CUE LATE`）要渲染完才知道；"有没有非例""公式有没有落地"这类教学要求，也只能靠人看成片检查。

scene-spec 要做到：

1. **一个文件说清一支视频**：旁白、画面对象、动作、时间点、教学信息都在一处。
2. **不写坐标**：对象说"放在哪个区域、挨着谁"，由布局求解器算位置；放不下就在编译时报错，不用等渲染。
3. **不写颜色**：对象只说语义角色（已知、对象 A、结论、错误……），由 `palette` 主题决定颜色。
4. **渲染前就能检查**：引用是否存在、动作总时长是否超过旁白、洞察卡片字段是否齐全、非例是否真的出现过。
5. **不绑死 Manim**：规范本身不出现任何 Manim 类名。以后要换渲染器，只需要写一个新的编译后端。
6. **模型好写、人好审**：语法小而封闭，diff 好读，能用 JSON Schema 校验。

不做的事：

- 不是编程语言。没有循环、条件、函数定义，也没有表达式；`data` 只放字面量。需要批量生成的内容（例如 8 个数的差分表）由 `data` + 组件参数表达，或由外部脚本生成 spec 文件。数据是否自洽由组件负责校验，例如 `diff_table` 检查 B 是不是 A 的逐项差。
- 0.1 不支持三维对象。#14 和立体几何走 `custom`（§9），等试做后再决定三维的对象、相机和布局规则。
- 不覆盖所有画面。确实表达不了的，用 `custom` 逃生口接手写代码（见 §9），但会被标记出来。

---

## 2. 文件形态

- 作者写**受限 YAML**（可以写中文注释、多行文本），工具内部统一转成 JSON，用 JSON Schema 校验。受限指：
  - 禁用锚点、别名、合并键（`&`、`*`、`<<`）和自定义标签（`!`）；
  - 布尔值只认 `true` / `false`，`yes`、`no`、`on`、`off` 一律当字符串，避免"NO 被读成 false"这类坑；
  - 配一个格式化工具（`scene-spec fmt`）统一缩进、引号和键的顺序，提交前自动运行。
- 一支视频一个文件：`<id>.scene.yaml`。可复用的组件定义放在 `kit` 里，不放在 spec 里。
- 顶层结构：

```yaml
spec: "0.1"        # 规范版本，语义化版本号
meta: {...}        # 身份、归属、许可、来源
pedagogy: {...}    # 洞察卡片：洞察、迷思、非例、演示还是证明
style: {...}       # 主题、配音人设、语速、是否分段播放
data: {...}        # 可选：本集用到的数据（数列、坐标点、表格）
objects: {...}     # 画面上的对象，按 id 声明
beats: [...]       # 按顺序的段落：旁白 + 动作
```

---

## 3. meta：身份与来源

```yaml
meta:
  id: s67-p01
  title: 高阶等差数列
  line: worked              # insight 洞察短视频 | worked 例题讲解 | contest 竞赛拔高
  units: [S6]               # 学习路径单元编号
  episode: null             # 洞察系列的选题编号，例如 21
  grade: 高二
  author: Boxi Yu
  license: CC-BY-4.0
  sources:                  # 非原创内容必须列出，见 OPEN_SOURCE.md 第 4 节
    - kind: problem
      cite: "§6.7 例1(1)"
      note: 题面引用；讲解与旁白为原创
```

`line` 决定哪些字段必填（见 §8 检查规则）。

---

## 4. pedagogy：洞察卡片

把规划 v0.2 §3.1 的五个必填字段放进文件，让检查器能核对。

```yaml
pedagogy:
  insight: 只要某一层差数列是等差的，就能往下做差、在那一层补全、再逐层加回
  misconception: 只给了五项，求不出第八项
  non_example: 如果二阶差不是等差的，这张表就补不下去
  status: method            # proof 证明 | demo 演示 | motivation 动机 | method 方法
  landing: GeneralTerm      # 图落到公式的是哪个 beat
  checks: [q-why-1, q-why-2]   # 练习包里对应的"为什么"题 id（题目本身存在题库，不在这里）
```

- `status: demo` 时，检查器要求某个 beat 的旁白里有"演示""不是证明"之类的说明（可配置关键词）。
- `non_example` 必须被至少一个 beat 用 `shows: non_example` 标注引用，否则报错。

---

## 5. style：主题与配音

```yaml
style:
  theme: paper              # animind-ai/palette 的主题名
  canvas: 16:9
  voice:
    persona: teacher-hs     # voice 仓库里的人设，含声音和语气说明
    speed: 1.25
  segmented: false          # true：小学默认分段播放（每个 beat 结束定格，播放器自动暂停）
  subtitles: soft           # soft 软字幕 | none
  min_font: 28              # 布局求解时字号下限（1080p 下的像素）
```

---

## 6. objects：画面对象

### 6.1 基本写法

每个对象一个 id，必须有 `type` 或 `widget`，可以有 `role`（语义颜色）和布局约束。

```yaml
objects:
  title:
    type: text
    text: 高阶等差数列
    role: A
    in: top
```

文字和公式对象可以写 `level` 表示字号层级：`display`（大标题）、`title`（标题）、`body`（正文，默认）、`caption`（注释）。具体字号由运行时决定，场景文件里不写数字。

对象类型分三层：

| 层 | 例子 | 定义在哪 |
|---|---|---|
| 基本类型 | `text`（文字与公式混排）、`math`、`shape`（圆、多边形、线、箭头）、`axes`、`numberline`、`grid`、`group` | 规范本身 |
| 组件 `widget` | `problem_card` 题卡、`chips` 步骤胶囊、`think_box` 想一想框、`summary` 总结卡 | `kit`，每个组件带自己的参数 Schema |
| 变形原语对象 | `diff_table` 差分表、`area_model` 面积模型、`fraction_bar` 分数条 | `primitives`，同上 |

§6.7 现有的 `card_box`、`plan_chips`、`think_box`、`summary_rows` 都会变成 `kit` 里的组件，`Table` 类变成 `primitives` 里的 `diff_table`。

### 6.2 文字与公式：显示文本和读法分开

文字里可以混写公式，用 `$...$`。要单独指向、单独上色的片段，用方括号加属性标出来：

```yaml
text: "定义：对数列 $\{A_n\}$，令 [$b_n=A_{n+1}-A_n$]{#b_def .B}，则 $\{b_n\}$ 称为一阶差数列"
```

- `{#b_def}` 给片段一个 id，动作里用 `card#b_def` 指向它。
- `{.B}` 给片段一个语义角色。
- 解析规则：`$...$` 内部的方括号一律当作数学内容，不参与片段标注（区间 `$[2,4)$` 不会被误认）；`$...$` 外面需要字面方括号时写 `\[`、`\]`。

读法不写在对象里，写在旁白里（§7.1）。旁白中的公式默认交给 `zh-math-reading` 按规则转成读法（`$A_8$` 读作"A 八"），规则不对时可以就地覆盖。

### 6.3 语义角色（颜色）

角色名直接取 `palette` 的角色：

| 角色 | 含义 | 规划 v0.2 中的对应 |
|---|---|---|
| `FG` | 正文 | — |
| `A` / `B` / `C` | 第一、二、三个对象 | 蓝：已知量 / 原对象 |
| `HL` | 结论、答案 | 绿：结果 / 答案 |
| `NO` | 错误、排除、被驳斥的迷思 | 红：易错点 / 迷思 |
| `DIM` | 次要元素、网格、辅助线 | — |

"正在变化 / 当前焦点"不再占一个颜色，改用**强调状态**表达：`focus`（加粗描边 + 其他元素调暗）、`mark`（底下垫一层淡色，§6.7 里给新算出的数垫淡金就是这个）。这样学生要记的颜色更少，也和 palette 的六套主题都兼容。

规范里**不允许出现色值**。需要主题里没有的颜色，先去 palette 加角色。

### 6.4 布局：只写关系，不写坐标

画面先按主题模板分成几个**区域**：

| 区域 | 用途 |
|---|---|
| `top` | 标题，或钉在顶上的题卡 |
| `stage` | 主讲区，变形发生的地方 |
| `footer` | 步骤胶囊、字幕安全区以上的提示 |
| `side` | 可选的右侧栏（公式常驻、答案写在题卡右侧留白） |

对象用以下约束定位：

```yaml
in: stage                       # 放进某个区域
below: table                    # 相对另一个对象：above / below / left_of / right_of
gap: md                         # 间距档位：xs / sm / md / lg / xl，由主题定义具体数值
align: {x: table}               # 与某对象某条边或中心对齐
size: {max_width: 0.8}          # 相对所在区域的比例
pin: top                        # 钉住：之后每一帧都在（题卡）
```

需要多个对象排在一起时，用容器类型：`row`、`stack`、`grid`，或者组件自带的布局（`diff_table` 自己知道三层数怎么错开排）。

**布局求解器的规则**：

1. 所有对象必须落在安全边距以内。
2. 同一时刻可见的对象两两不重叠（`mark` 底色、`focus` 描边这类装饰除外；需要叠放的用 `over: X` 显式声明）。
3. 放不下时，先按优先级缩小（但不低于 `style.min_font`），再不行就**编译失败**，报出是哪个 beat、哪几个对象冲突。
4. 求解结果写进编译产物，`qa` 用同一份结果做包围盒检查。

逃生口：`at: [x, y]` 可以写绝对坐标，规则按产品线区分：
- `line: insight`（洞察短视频）：**禁止**，检查器报错。确实需要的画面走 `custom`（§9）。
- `line: worked` / `contest`：允许，但给出警告，并统计每集的绝对坐标数量，用来跟踪 §6.7 迁移进度。

### 6.5 引用语法

动作里用选择器指向对象或对象的一部分：

| 写法 | 指向 |
|---|---|
| `table` | 整个对象 |
| `card#b_def` | 对象里带 id 的片段 |
| `table.B[0]` | 组件暴露的子元素（`diff_table` 暴露 `A`、`B`、`C` 三行，按下标取） |
| `plan[1]` | 列表型组件的第几项 |
| `table.B[0:4]` | 切片 |

每个组件在自己的 Schema 里声明暴露哪些子元素，检查器据此校验引用。

---

## 7. beats：旁白与动作

一个 beat 对应现在的一个场景（`Opening`、`Down`、`Up`……），由**旁白句子**和**动作**组成。

### 7.1 旁白

```yaml
- id: Down
  say:
    - id: s1
      pace: normal
      text: "先往下做差。按定义，后一项减前一项：{@d0}五减二，得三。"
    - id: s2
      pace: brisk
      text: "同样，{@d1}十一减五得六，{@d2}二十一减十一得十，{@d3}三十六减二十一得十五。"
```

- `pace` 沿用 §6.7 的四种：`normal`、`brisk`、`slow`、`ask`。
- `{@d0}` 是**词级书签**。`voice` 合成后用 Whisper 时间戳算出它的时刻，动作可以挂在书签上，比"第几句"更精确。
- 旁白文本就是读法。需要显示和读法不同时，在 `say` 里写读法，在对象里写显示：例如对象显示 `$A_8$`，旁白写"A 八"。也可以在旁白里写 `$A_8$`，交给读法规则自动转换。
- 句子可以不写 `id`，此时按下标引用；建议给会被动作引用的句子写 `id`，插句子时不会错位。

### 7.2 动作

```yaml
  do:
    - at: s1                 # 在句子 s1 开始时
      act: focus
      target: plan[0]
    - at: s1@d0              # 在书签 d0 处
      act: derive            # diff_table 原语提供的动作
      target: table
      args: {row: B, index: 0}
    - at: s2@d1
      act: derive
      target: table
      args: {row: B, index: 1}
      dur: fit               # 时长撑满到下一个时间点
```

**时间点**：

| 写法 | 含义 |
|---|---|
| `at: s1` | 句子开始 |
| `at: s1@d0` | 书签处 |
| `at: s1+0.5` | 句子开始后 0.5 秒 |
| `after: prev` | 上一个动作结束后 |
| `with: prev` | 与上一个动作同时 |

**时长**：`dur: 0.8`（秒）、`dur: fit`（撑满到下一个时间点）、或使用动作的默认值。

**动作词表**（规范内置，保持小而封闭）：

| 动作 | 作用 |
|---|---|
| `show` / `hide` | 出现、消失；`style:` 淡入、书写、从边缘长出等，由后端映射 |
| `transform` | 一个对象变成另一个；`match: tex` 按公式片段对应（TransformMatchingTex），`match: shape` 按形状 |
| `move` | 移到新的布局约束（不写坐标，写新的 `in` / `below` 等） |
| `focus` / `unfocus` | 强调状态：加粗描边，其余调暗 |
| `mark` / `unmark` | 底下垫淡色 |
| `underline` / `circle` / `cross` | 划线、圈出、打叉（打叉用于排除、错误） |
| `clear` | 去掉目标对象上的划线、圈、叉和 mark |
| `set` | 改角色、透明度等属性 |
| `camera` | 放大、平移（导数放大、局部特写） |
| `hold` | 停住 N 秒（"aha"处留白） |
| 原语动作 | 由 `primitives` 提供，例如 `derive`、`extend`（差分表）、`cut`、`slide`（面积模型）、`flip`（数轴） |

### 7.3 停顿、分段和互动点

```yaml
- id: Predict
  pause:
    type: predict            # predict 预测暂停 | think 想一想 | segment 分段点
    prompt: "拼起来会是什么形状？先想三秒。"
    hold: 3
    app_item: q-predict-1    # 可选：App 里对应的题目 id
```

- 播放器根据 `pause` 生成章节点；`style.segmented: true` 时每个 beat 末尾自动成为分段点。
- `pause` 本身也是 beat，可以有旁白。

### 7.4 教学标注

beat 可以带标注，供检查器和后续数据分析使用：

```yaml
- id: NonExample
  shows: non_example         # 对应 pedagogy.non_example
- id: Wrong
  shows: misconception       # 先按错误想法演示出矛盾
- id: GeneralTerm
  shows: landing             # 图落到公式
```

---

## 8. 检查规则（渲染前）

检查分四层，前三层都不需要渲染，几秒内出结果：

| 层 | 检查内容 | 失败时 |
|---|---|---|
| 1. 结构 | JSON Schema：字段、类型、枚举值 | 报错 |
| 2. 语义 | 引用的对象、片段、句子、书签都存在；没有色值；`line` 要求的字段齐全；`pedagogy.non_example` / `misconception` / `landing` 都被某个 beat 标注引用；`status: demo` 时旁白里有说明 | 报错 |
| 3. 时间 | 按 `voice` 缓存的真实时长（没有缓存时按字数估算），挂在同一句上的动作总时长不超过这一句；预测出来的"画面跟不上旁白"直接报出，对应现在渲染日志里的 `CUE LATE` | 报错或警告 |
| 4. 布局 | 求解器跑一遍：出框、重叠、字号低于下限 | 报错 |

不同产品线的必填项：

| 字段 | insight | worked | contest |
|---|---|---|---|
| `pedagogy.insight` | 必填 | 必填 | 选填 |
| `pedagogy.misconception` | 必填 | 选填 | 选填 |
| `pedagogy.non_example` | 必填 | 选填 | 选填 |
| `pedagogy.status` | 必填 | 必填 | 必填 |
| `pedagogy.landing` | 必填 | 选填 | 选填 |
| 至少一个 `predict` 停顿 | 必填 | 选填 | 选填 |
| `meta.sources` | 有非原创内容时必填 | 同左 | 同左 |

渲染后的检查（抽帧、Whisper 回识别比对、模型预筛）属于 `qa` 仓库，不在规范里定义，但它们读取同一份编译产物。

---

## 9. 逃生口：custom

总会有规范一时表达不了的画面。允许在 beat 里接手写代码：

```yaml
- id: Galton
  custom:
    backend: manim
    ref: scenes_custom:GaltonBoard   # 模块:类
    args: {balls: 300, rows: 10}
  say: [...]
```

规则：

- `custom` beat 仍然参与旁白合成、时间检查和教学标注检查，只是画面部分由手写代码负责。
- 检查器统计每集 `custom` beat 的数量和占比。某种 `custom` 用多了，说明该把它做成原语。
- `custom` 代码要遵守同一套主题和布局区域（通过 `kit` 提供的接口取颜色和区域），不能写色值。

---

## 10. 编译与缓存

```
<id>.scene.yaml
   │  解析 + Schema 校验
   ▼
 语义检查 ── 时间检查（读 voice 缓存）
   │
   ▼
 布局求解 ──► layout.json（每个对象每个时刻的包围盒）
   │
   ├──► voice：按句合成 → 书签时间戳 → timing.json
   │
   ▼
 后端编译（manim）──► 每个 beat 一个场景 ──► 渲染 ──► 拼接成片
                                              │
                                              ▼
                                       qa：抽帧、回识别、预筛
```

- 每个 beat 按内容算哈希，只重新渲染改过的 beat；旁白按（文本、语气、人设、语速）缓存，沿用 §6.7 现在的做法。
- 编译产物（`layout.json`、`timing.json`、生成的场景代码）放在构建目录，不手改。

---

## 11. 完整例子

### 11.1 §6.7 第 01 支的"往下做差"一段

对照现在 `p01/build.py` 的 `Down` 和 `p01/scenes.py` 的 `Table`：

```yaml
spec: "0.1"
meta:
  id: s67-p01
  title: 高阶等差数列
  line: worked
  units: [S6]
  author: Boxi Yu
  license: CC-BY-4.0
  sources:
    - {kind: problem, cite: "§6.7 例1(1)", note: 题面引用；讲解与旁白为原创}

pedagogy:
  insight: 某一层差数列是等差的，就能往下做差、在那一层补全、再逐层加回
  misconception: 只给了五项，求不出第八项
  status: method
  landing: GeneralTerm

style:
  theme: paper
  voice: {persona: teacher-hs, speed: 1.25}

data:
  A: [2, 5, 11, 21, 36, 57, 85, 121]
  B: [3, 6, 10, 15, 21, 28, 36]
  C: [3, 4, 5, 6, 7, 8]

objects:
  card:
    widget: problem_card
    pin: top
    lines:
      - '[例1(1)]{.bold} 定义：对数列 $\{A_n\}$，令 [$b_n=A_{n+1}-A_n$]{#b_def .B}，则 $\{b_n\}$ 称为 $\{A_n\}$ 的一阶差数列；'
      - '再令 [$c_n=b_{n+1}-b_n$]{#c_def .C}，则 $\{c_n\}$ 称为 $\{A_n\}$ 的二阶差数列．'
      - '已知 $\{A_n\}$ 为 [$2,5,11,21,36,\cdots$]{#terms .A}，且[它的二阶差数列是等差数列]{#key .HL}，则 [$A_8=$]{#ask .HL}[____]{#blank}．'
  table:
    widget: diff_table
    in: stage
    rows:
      - {data: A, role: A, label: '$A_n$', name: 原数列}
      - {data: B, role: B, label: '$b_n$', name: 一阶差数列}
      - {data: C, role: C, label: '$c_n$', name: 二阶差数列}
    known: [5, 0, 0]
  plan:
    widget: chips
    in: footer
    items: ["↓ 往下做差", "→ 在等差层补全", "↑ 逐层加回"]

beats:
  - id: Down
    say:
      - {id: s1, pace: normal, text: "先往下做差。按定义，后一项减前一项：{@d0}五减二，得三。"}
      - {id: s2, pace: brisk,  text: "同样，{@d1}十一减五得六，{@d2}二十一减十一得十，{@d3}三十六减二十一得十五。"}
      - {id: s3, pace: brisk,  text: "一阶差数列再相邻相减：{@e}三、四、五。"}
      - {id: s4, pace: slow,   text: "看，三、四、五，正好是公差为一的等差数列，{@k}和题目给的条件对上了。"}
    do:
      - {at: s1, act: focus, target: "plan[0]"}
      - {at: s1@d0, act: derive, target: table, args: {row: B, index: 0}}
      - {at: s2@d1, act: derive, target: table, args: {row: B, index: 1}}
      - {at: s2@d2, act: derive, target: table, args: {row: B, index: 2}}
      - {at: s2@d3, act: derive, target: table, args: {row: B, index: 3}}
      - {at: s3@e, act: derive, target: table, args: {row: C, index: "0:3"}, dur: fit}
      - {at: s4, act: focus, target: "table.C[0:3]"}
      - {at: s4@k, act: underline, target: "card#key"}
```

和现在相比：没有坐标，没有色卡名；旁白和动作在同一处；"五减二"那个时刻由书签决定，不靠手算等待时间。

> 写法注意（实现检查器时发现）：含 LaTeX 反斜杠的字符串要用**单引号**，双引号里 `\{` 会被 YAML 当成转义而报错；流式映射 `{...}` 里的选择器如 `"plan[0]"` 要加引号。完整的一支见 `examples/s67-p01.scene.yaml`。

### 11.2 洞察系列 #21 勾股定理的骨架

展示洞察短视频特有的部分：迷思、预测暂停、非例、公式落地。

```yaml
spec: "0.1"
meta: {id: ep21, title: "勾股定理：拼一拼就看见", line: insight, units: [J11], episode: 21, grade: 八年级,
       author: Boxi Yu, license: CC-BY-4.0}

pedagogy:
  insight: 同一个大正方形里，四个直角三角形换个摆法，空白处从 c² 变成 a²+b²
  misconception: a+b=c
  non_example: 把直角改成钝角，空白处对不上
  status: proof
  landing: Landing

style: {theme: paper, voice: {persona: peer-ms}, segmented: false}

objects:
  big:   {widget: area_model, kind: square, side: "a+b", in: stage, role: DIM}
  tris:  {widget: area_model, kind: right_triangles, count: 4, legs: [a, b], within: big, role: A}
  hole:  {type: shape, shape: square, side: c, within: big, role: B}
  wrong: {type: math, tex: "a+b=c", role: NO, in: side}
  law:   {type: math, tex: "a^2+b^2=c^2", role: HL, in: side}

beats:
  - id: Hook
    shows: misconception
    say:
      - {id: s1, pace: ask, text: "直角三角形两条直角边是 a 和 b，斜边 c 等于多少？{@w}a 加 b 吗？"}
    do:
      - {at: s1@w, act: show, target: wrong}
      - {after: prev, act: cross, target: wrong}

  - id: Setup
    say: [...]
    do:
      - {at: 0, act: show, target: big}
      - {with: prev, act: show, target: tris}

  - id: Predict
    pause: {type: predict, prompt: "把四个三角形挪一挪，空白处会变成什么？先想三秒。", hold: 3}

  - id: Rearrange
    say: [...]
    do:
      - {at: 0, act: slide, target: tris, args: {layout: two_rectangles}, dur: fit}   # area_model 原语
      - {after: prev, act: hold, dur: 1.5}

  - id: NonExample
    shows: non_example
    say: [...]
    do:
      - {at: 0, act: set, target: tris, args: {angle: 110}}
      - {after: prev, act: slide, target: tris, args: {layout: two_rectangles}}

  - id: Landing
    shows: landing
    say: [...]
    do:
      - {at: 0, act: transform, from: hole, to: law, match: shape}
```

---

## 12. 版本与演进

- `spec` 字段使用语义化版本号。0.x 阶段允许不兼容改动，每次改动附迁移说明；1.0 之后，次版本号只加字段，不删不改。
- 工具读到比自己新的主版本号时直接拒绝，不猜。
- 组件和原语各自有版本，spec 里可以写 `widget: diff_table@1`；不写版本时取 `kit` 锁定的版本。

---

## 13. 已定的设计决定（2026-10-16，Boxi Yu 拍板）

| # | 问题 | 决定 | 落在哪 |
|---|---|---|---|
| 1 | 作者格式 | 受限 YAML，内部转 JSON 校验，配格式化工具 | §2 |
| 2 | 片段标注语法 | 行内 `[文本]{#id .角色}`；`$...$` 内的方括号不参与标注，字面方括号用 `\[` 转义 | §6.2 |
| 3 | 绝对坐标 | 洞察系列禁止（走 `custom`），例题讲解和竞赛线允许但警告并计数 | §6.4 |
| 4 | "正在变化"的表达 | 用 `focus` / `mark` 强调状态，不占颜色；规划 v0.2 §3.2 的颜色表已同步修改 | §6.3 |
| 5 | 三维 | 0.1 不支持，走 `custom`，阶段 C 试做后再定 | §1 |
| 6 | 数据计算 | `data` 只放字面量，批量内容由外部脚本生成，自洽性由组件校验 | §1 |

## 14. 落地顺序（定稿后）

1. 写 JSON Schema 和检查器（结构、语义两层），用本稿 §11.1 做第一个测试用例。
2. 把 §6.7 的 `kit/style.py` 拆成 `kit` 组件（`problem_card`、`chips`、`think_box`、`summary`），`Table` 拆成 `primitives` 的 `diff_table`。
3. 把 `narrate.py` 改成读 spec 的 `say`，补上书签时间戳。
4. 写 Manim 后端，用 spec 重做 §6.7 第 01 支，和现有成片逐帧对比。
5. 加时间检查和布局求解。布局求解是工作量最大的一块，可以先只做"检查"不做"求解"，即先报冲突，再逐步改成自动排布。
