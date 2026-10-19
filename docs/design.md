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

- 不是编程语言。没有循环、条件、函数定义；`data` 只放字面量。表达式只有一种：引用场景参数和函数自变量的白名单算式，只能写在组件声明的属性和读数里（§7.5），用来描述"随参数连续变化"的几何，不能用来生成内容。需要批量生成的内容（例如 8 个数的差分表）由 `data` + 组件参数表达，或由外部脚本生成 spec 文件。数据是否自洽由组件负责校验，例如 `diff_table` 检查 B 是不是 A 的逐项差。
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
    speed: 1.0              # 2026-10-16 老师确认 1 倍速（1.25 倍太快）
  segmented: false          # true：小学默认分段播放（每个 beat 结束定格，播放器自动暂停）
  step_hold: 1.0            # 分段时每个子步（step）结束定格几秒，见 §7.6
  subtitles: burned         # burned 烧进画面（默认，2026-10-17 定）| soft 只封装可关的软字幕轨 | none；都导出 .vtt/.srt
  min_font: 28              # 字号下限（1080p 下的像素）：布局求解不缩到它以下，kit inspect 报低于它的字；不写时 16
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
5. 包围盒之外还有一层**字形级检查**（kit 的 `inspect`，渲染时也跑）：每批动作结束时看每个字——字号低于 `style.min_font`（没写时 16px，1080p）、一条线或一块填充的边穿过字（同一对象内部也算，例如数轴刻度穿过标签、图上的曲线穿过刻度数字）、不透明的填充盖住字、两段文字压在一起、内容伸出画面。`cross` 划掉自己的目标、`mark` 底色压到邻字边缘、镜头推近时跟镜头走的东西只露出一部分，这几种本来就是故意的，不报。
6. **几类文字另有字号下限**（2026-10-17 定，按成片 720p 计；烧录字幕时画面缩小，kit 按比例抬高）：数轴上的数字和分数标注 36px（分数用 `\dfrac`，分子分母不缩小；数轴被排版缩小时 kit 加大标注字号重建，标注不跟着变小）；`side` 侧栏里的文字和「练一练」框（`think_box`）26px。侧栏宽度相应加到 4.2 个单位。低于下限 inspect 报 `small`。

确实是故意的版式例外，在对象上写 `allow`，检查就不报：

```yaml
allow:
  cross: [card]      # 本对象的线可以穿过 card 的文字（或者 card 的线穿过本对象的字）；true = 和任何对象，含本对象内部
  overlap: [ghost_a] # 文字可以压住这些对象的文字；true = 任何对象
  small: true        # 允许小于 style.min_font 的字（例如角标式的注记）
  clip: true         # 允许伸出画面（例如从画外滑进来的长条）
```

`cross` / `overlap` 是对称的：任何一方写了对方就不报。只写在真正故意的对象上；检查报出来的大多是真问题。

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

### 6.6 剖分组件 dissect：剪一刀，挪过去

规划 §2 里最大的一类（#4 #5 #11 #12 #13 #17 #18 #20 #21 #23 #29 #37）都是"把图形剪开、刚体移动、拼成另一个图形"。`dissect` 把它做成一个通用组件：**所有会产生名字的东西（图形、切法、复制品、参考线、拼合轮廓）都在对象里声明，动作只点名字**，不写算好的坐标。检查器和 kit 用同一份几何代码（`scene_spec/dissect.py`）。

```yaml
para:
  widget: dissect
  role: A                    # 块的默认颜色角色
  in: stage
  view: [[-1, -1], [10, 4]]  # 可选：给图形留出的范围（块挪出原图时要写），默认是原图包围盒外扩一点
  shapes:                    # 一开始就有的图形；坐标是图形坐标（y 向上，单位任意，按画面自动缩放）
    P:
      polygon: [[0, 0], [6, 0], [9, 3], [3, 3]]     # 或 rect: [宽, 高]、circle: 半径、sector: {r, from, to}、
                                                      #    dots: {rows: [1, 2, 3]} / {points: [[x, y], ...]}
      edges: [{at: [[0, 0], [6, 0]], text: '底 $a$'}] # 边长标签（放在边外侧，始终正立）
      # at: [x, y] 平移整个图形；hidden: true 先藏着，show obj#P 时出现；label: 面积标签（写在重心）
  cuts:
    c1: {piece: P, line: [[3, 3], [3, 0]], into: [T, Q]}   # line 过两点的直线；path 折线；sectors: n 把圆切成 n 份
  copies: {T2: T}            # 复制品（copy 动作之后才存在）
  pieces: {T: {role: B, label: '$S_1$'}}                   # 给任意块（包括切出来的）配颜色和标签
  guides:                    # 参考线：虚线 + 标签，show / hide obj#h
    h: {from: [3, 3], to: [3, 0], label: '高 $h$', role: HL}   # side: above/below/left/right，solid: true 画实线
  merges:
    R: {pieces: [T, Q], label: '$a\times h$', role: HL}     # 拼好后画外轮廓（共用的边自动抵消）
```

- **切法**：多边形和切线一起做平面剖分，每个有界的面是一块；切线落在多边形外的部分和悬空的部分不算。一刀可以切出多块（凹多边形）。`into` 按重心**从左到右、再从下到上**对应名字；`sectors` 的 `into` 是名字前缀（`s` → `s0`…`s{n-1}`）。圆和扇形只能用 `sectors` 切，点阵只能用 `line` 分成两份。
- **坐标约定**：每块记住"出生时"的坐标（切出来的块就是被切那块的原坐标）。动作里的 `edge` / `vertex` / `to_edge` / `to_vertex` 用块的原坐标点名（作者写过的点，挪到哪都不变）；`shift` 的 `to`、`rotate` 的 `about`、`flip` 的 `axis` 是当前的图形坐标。
- **片段**：每一块、每条参考线、每个合并轮廓都是片段（`para#T`），内置的 `show` / `hide` / `focus` / `mark` / `set` 直接可用。`obj[i]` 是现在存在的块。

动作（`target` 指向整个组件）：

| 动作 | 参数 | 作用 |
|---|---|---|
| `cut` | `cut`, `spread?` | 切口用虚线闪一下，被切的块换成切出的几块；`spread` 让各块离开切口一点 |
| `shift` | `piece`, `by: [dx, dy]` 或 `to: [x, y]` | 平移（`to` 是重心的目标位置） |
| `rotate` | `piece`, `angle`, `about?` | 绕点转（逆时针为正）；`about` 是 `center`（默认）、`[x, y]` 或 `{vertex: [x, y]}` |
| `flip` | `piece`, `axis` | 关于直线翻折，画面上是"翻过去"；`axis` 是两点或 `{edge: [[x,y],[x,y]]}`（沿块自己的边翻） |
| `fold` | `cut`, `flap`, `back?` | 折纸：沿 `cut`（必须是 `line` 切法）的切线，把 `flap`（切出的块名或列表，不能是全部）翻到另一侧；没切过就先切。翻的过程在垂直于折痕的方向从 1 压到 −1、中途变暗，`back` 是翻过来露出的背面颜色角色；翻过来的块放到最上层（仍在参考线下面）。折痕跟着块当前的位姿走，同一个切法可以再 `fold` 一次翻回来 |
| `snap` | `piece`, `edge` + `to` + `to_edge`，或 `vertex` + `to` + `to_vertex` | 吸附：按两条边（或两个点）算出刚体变换，边对边时端点按书写顺序对齐；`to` 也可以是参考线或一个点 |
| `copy` | `piece`, `by?` | 复制品出现在原块当前位置，可以顺手挪开 |
| `merge` / `unmerge` | `name` | 画出 / 去掉拼合外轮廓 |
| `arrange` | `cut`, `layout: alternate`, `at?` | 把一次 `sectors` 切出的扇形交错排成一排（#13：n=8、16、64 越来越接近长 πr、宽 r 的长方形） |
| `labels` | `piece`, `show` | 显示 / 藏起这块的标签 |

注意：`move` 是内置动作（整个对象换布局位置），块的平移叫 `shift`。

移动途中块与块重叠是预期的，布局检查不管组件内部；**结束状态下**（每个 beat 末尾）看得见的标签两两不能压住，否则算一条版式问题。

检查（错误码 SS420–SS439）：

| 码 | 内容 |
|---|---|
| SS420 | 图形写错：种类不是 polygon / rect / circle / sector / dots 之一、多边形退化（面积 0）或自相交、半径不是正数 |
| SS421 | 名字不合法或重复（块、参考线、合并轮廓共用一个名字空间） |
| SS422 | 切法引用的块不存在；动作引用不存在的切法；同一个切法切两次 |
| SS423 | 切线没把图形切开（只得到一块）；点落在点阵的切线上 |
| SS424 | `into` 的个数和实际切出的块数不一样 |
| SS425 | 切法写错：line / path / sectors 不是恰好一个、圆用了直线切、多边形用了 sectors |
| SS426 | 动作引用不存在的块 |
| SS427 | 按时间顺序，块这时还不存在（切之前、复制之前）或已经被切掉 |
| SS428 | 吸附 / 翻折的目标不存在：块没有这条边或这个顶点、目标块不存在、吸附到自己 |
| SS429 | 边对边吸附的两条边不一样长（刚体移动对不上） |
| SS430 | 翻折轴退化（两点重合）或写错 |
| SS431 | `rotate` 缺角度、角度为 0、`about` 写错 |
| SS432 | `shift` 的 `by` / `to` 缺失或两个都写、坐标格式错 |
| SS433 | 合并轮廓没声明、成员块不存在、`unmerge` 在 `merge` 之前 |
| SS434 | `arrange` 的切法不是 `sectors`、`layout` 未知 |
| SS435 | 复制品没在 `copies` 里声明、被复制的块不存在、复制两次 |
| SS436 | 动作有多余参数、`labels` 缺 `show` |
| SS437 | 参考线写错（缺端点、两端重合、`side` 不对） |
| SS438 | `fold` 写错：切法不是一刀 `line`、没写 `flap`、`flap` 不是这个切法切出的块、全部块都翻、`back` 不是角色 |
| SS439 | `pieces` / 图形里的样式写错：块不存在、角色不对、边长标签指向不存在的边 |

完整的例子见 `animind/scene-spec/examples/ep11.scene.yaml`（平行四边形面积）、`ep18.scene.yaml`（平方差）和 `ep20-fold.scene.yaml`（折纸）。

### 6.7 立体组件 solid：轴测图、剖成三块、截面比大小

洞察 #14「圆锥为什么是圆柱的 1/3」要三种画面：几种立体的线框图、一个正方体剖成三个全等的四棱锥再合回去、一个截平面同时扫过两个立体并把两个截面拿出来比大小（祖暅原理）。`solid` 把它们做成一个组件：立体、剖法、截平面都在对象里声明，动作只点名字。

```yaml
zu:
  widget: solid
  in: stage
  role: A                         # 立体的默认颜色角色
  bodies:                         # 名字 → 立体；坐标 x 向右、y 向里、z 向上，单位任意（按画面自动缩放）
    C: {cube: 2, label: 正方体}                        # 或 box: [宽, 深, 高]
    P: {pyramid: {base: 2, h: 2}, role: B}            # 正四棱锥；base 也可以是 [宽, 深]，apex: [dx, dy] 让顶点偏离底面中心
    Y: {cylinder: {r: 1, h: 2}, hidden: true}         # hidden：先藏着，show zu#Y 时出现
    K: {cone: {r: 1.128, h: 2}, at: [3, 0, 0]}        # at：底面中心的位置；不写 at 的立体在画面上排成一行
  splits:                         # 正方体剖成三个全等的四棱锥
    s: {body: C, into: [P1, P2, P3], gap: 1.5, roles: [A, B, C]}
  plane: {bodies: [P, K], z: 0.5, compare: right, labels: ['$S_1$', '$S_2$']}
  view: {azimuth: 30, elevation: 20}                  # 可选：看过去的方位角、仰角（度）
```

- **画法**：正交轴测，默认从右前方 30°、仰角 20° 看。不用严格的等轴测（45°、35.26°），因为那样正方体的前上角和后下角投到同一点，虚线的棱全叠在中间。多面体朝向观者的面涂淡色（按朝向深浅不同），看得见的棱画实线、被挡住的棱画淡虚线；圆柱、圆锥画轮廓线和底面椭圆，背面那段椭圆画虚线。
- **排成一行**：不写 `at` 的立体按声明顺序沿画面水平方向排开（底面中心在画面上同一高度，互不遮挡）。立体之间不做遮挡计算，摆得互相重叠时是半透明叠在一起。
- **剖开**：公共顶点是正方体的左后上角，三块的底面依次是正方体的下、前、右三个面，`into` 按这个顺序起名，默认 A / B / C 三色（`roles` 可改）。`apart` 时底下那块往下、前面那块往画面左边、右边那块往画面右边，各挪 `gap`（立体坐标，默认 0.75 个棱长；排版按它预留位置）。
- **截平面**：`plane.bodies` 上方的一块水平面，盖住这几个立体的底面再多出一点；`z` 是一开始的高度（默认在中间）。每个立体在这个高度的截面涂成实色。`compare: right / below` 时排版在立体的右边 / 下面预留一行，`compare` 动作把截面"拿出来"平铺过去：俯视的真实形状，和立体同一个比例，大小可以直接比；`labels` 写在平铺的截面下面。
- **片段和部件**：每个立体、每个剖出来的块都是片段（`zu#K`、`zu#P2`）；`zu.plane[0]`、`zu.section[i]`、`zu.flat[i]` 是截平面、第 i 个截面、第 i 个平铺的截面（i 按 `plane.bodies` 的顺序）。内置的 `show` / `hide` / `mark` / `focus` 都能用；`set {role, opacity}` 由组件自己接管：面换填充色、棱换描边色（立体的样式在面和棱各自的节点上）。`zu[i]` 是现在看得见的立体（剖开以后是三块）。

动作（`target` 指向整个组件；颜色、透明度、位置都在动画播放时才改）：

| 动作 | 参数 | 作用 |
|---|---|---|
| `split` | `split` | 正方体淡出，三块在原处出现 |
| `apart` / `join` | `split` | 三块挪开 / 拼回去 |
| `unsplit` | `split` | 换回整个正方体（要先 `join`） |
| `sweep` | `z` | 截平面移到高度 `z`，截面跟着变；第一次 `sweep` 时截平面在 `z` 处出现。`compare` 之后平铺的截面也跟着变 |
| `compare` | — | 截面从立体里平铺到旁边 |

检查（错误码 SS460–SS469）：

| 码 | 内容 |
|---|---|
| SS460 | 立体写错：种类不是 cube / box / pyramid / cylinder / cone 中恰好一个、尺寸不是正数、`at` 不是三个数、`role` 不对、多余字段 |
| SS461 | 名字不合法或重复（立体和剖出来的块共用一个名字空间） |
| SS462 | 剖法写错：`body` 不存在或不是正方体、同一个正方体剖两次、`into` 不是三个名字、`gap` 不是正数或超过两个棱长、`roles` 不是三个角色 |
| SS463 | 截平面写错：`bodies` 引用不存在的立体（剖出来的块不能放进去）、`z` 碰不到立体、`compare` 不是 right / below、`labels` 个数不对或没写 `compare` |
| SS464 | `view` 写错：方位角的绝对值不在 10°–80°（有的面看成一条线）、仰角不在 10°–50° |
| SS465 | `split` / `apart` / `join` / `unsplit` 没写 `split` 或写了不存在的剖法 |
| SS466 | 按时间顺序做不了：没 `split` 就 `apart`、分开着就 `unsplit`、剖开两次 |
| SS467 | 没写 `plane` 就 `sweep`、`sweep` 缺 `z` 或 `z` 碰不到立体 |
| SS468 | `compare`：`plane` 里没写 `compare`、截平面还没出现（先 `sweep`）、平铺两次 |

SS469 预留。动作的多余参数报 SS281。完整的例子见 `animind/scene-spec/examples/solids.scene.yaml`。

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
- `en`（可选）：这句的英文。中文版里是双语字幕的第二行（每条两行，中文在上），不念、不影响配音和音频缓存；英文版里就是要念的旁白（§7.7）。

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
| `camera` | 放大、平移（导数放大、局部特写），参数见下 |
| `hold` | 停住 N 秒（"aha"处留白） |
| `step` / `ghost` / `unghost` / `pin` | 子步定格、残影、常驻公式，见 §7.6 |
| `tween` | 把场景参数在动作时长内补间到目标值，依赖参数的图形和读数跟着连续变化（§7.5） |
| 原语动作 | 由 `primitives` 提供，例如 `derive`、`extend`（差分表）、`cut`、`slide`（面积模型）、`flip`（数轴） |

**镜头 `camera`**：整幅画面一起放大、平移，对象本身不动（布局、引用的坐标都不变）。

```yaml
    - at: s2@z
      act: camera
      target: graph.point     # 对准谁
      args: {zoom: 60}        # 放大到原样的 60 倍（绝对倍数，不累乘）
      dur: 3
    - at: s3
      act: camera
      target: table
      args: {fit: true, margin: 0.3}   # 让 table 刚好填满画面，四周留 0.3
    - at: s4
      act: camera
      args: {reset: true}     # 回到原样
```

| 参数 | 含义 |
|---|---|
| `zoom: 3` | 放大倍数，> 0；1 是原样。有 `target` 时对准它的中心，没有时绕当前中心缩放 |
| `fit: true` | 自动算倍数，让 `target` 填满画面；需要 `target`，不能和 `zoom` 同时写 |
| `margin: 0.3` | 只和 `fit: true` 一起用，四周留白（画面单位，默认 0.5） |
| `reset: true` | 复位到原样；不再写 `target`、`zoom`、`fit`、`margin` |

三者（`zoom`、`fit: true`、`reset: true`）必须有一个。放大倍数按对数插值，从 1 倍推到 100 倍看起来是匀速的；默认时长 1.5 秒。钉住的对象（`pin`）和 `top` / `footer` 区的对象不跟镜头走，题卡和底部胶囊在放大时原地不动；对准它们会得到警告。参数错误报 `SS334`。

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

### 7.5 参数：连续变化的量

很多洞察的核心是"一个量连续变化，图形和读数跟着变"：斜率 k 从 0.5 调到 2，直线变陡、斜率三角形的竖边变长（#22）；
直角三角形等比放大，比值读数不变、面积读数在变（#25）；追踪曲线上一点（#26）。这类画面用**场景参数**表达：

```yaml
params:
  k: {value: 0.5, min: -3, max: 3}   # 初值 + 可选范围
  t: 0                                # 只写初值的简写

objects:
  g:
    widget: graph
    x: [-3, 4]
    y: [-3, 5]
    plots: [{f: "kx+b", label: "y=kx+b"}]   # 曲线可以引用参数
    points: [{x: "t"}]                       # 点的横坐标由参数决定
    triangles: [{point: 0, run: 1}]          # 斜率三角形：横走 run，竖走到曲线上
  kval:
    type: readout                            # 读数：label + 随参数变化的值
    label: "斜率 $k$ ="
    value: k
    digits: 1                                # 小数位（默认 2）；或 format: fraction
    in: side

beats:
  - id: Steep
    do:
      - {at: s1@go, act: tween, args: {k: 2}, dur: fit, ease: in_out}
      - {at: s2@neg, act: tween, args: {k: -1, t: 1}, dur: 2.5}   # 一次补间几个参数
```

- **参数**：顶层 `params`，名字是字母、可带下标（`k`、`theta`、`x_0`），不能和 `x`、`pi`、`e`、函数名重名。参数跨 beat 保留：下一个 beat 从上一个 beat 结束时的值出发。
- **`tween` 动作**：在动作时长内把 `args` 里的参数补间到目标值（必须是数，在声明的 `[min, max]` 里）；不写 `target`，画面上依赖这些参数的对象自己跟着变。`ease` 可选 `linear`、`smooth`（默认）、`in`、`out`、`in_out`；`dur` 默认 1.5 秒，可以写 `fit`。
- **表达式**：只能写在组件声明为"可用参数"的属性里，以及 `readout` 的 `value`。语法沿用 `graph` 的白名单（四则、乘方、括号、`sin cos tan exp ln log sqrt abs`、`pi e`），多了声明过的参数名；参数名紧挨着写算乘法（`kx` = k·x，`2kx` = 2·k·x）。从不 `eval`。只有曲线的 `f` 能用 `x`。
- **读数 `readout`**：`label` 是值前面的文字（可混排公式），`value` 是表达式；`digits` 定小数位，`format: fraction` 时能写成分母不超过 12 的分数就写成分数（例如 1/2），否则按 2 位小数。值变宽时左端不动、往右长。
- **graph 里能用参数的属性**：`plots[].f`、`points[].x`、`lines[].x / slope / through`、`triangles[].run`。割线、切线跟着它们的点走。

时间语义：参数在 beat 内时刻 t 的值只由 t 决定（同一参数的后一个补间从前一个补间当时的值接管），逐帧渲染、跳着预览、往回拖都得到同一画面。

检查（错误码 SS400–SS419）：

| 代码 | 内容 |
|---|---|
| SS400 | 参数声明不合法：保留名、`min > max`、初值不在范围里 |
| SS401 | 表达式语法错 |
| SS402 | 表达式引用了没声明的参数 |
| SS403 | 这里不能用 `x`（只有曲线的 `f` 能用） |
| SS404 | `tween` 写法不对：没有 `args`，或者写了 `target` / `from` / `to` |
| SS405 | `tween` 补间了没声明的参数 |
| SS406 | `tween` 的目标不是数 |
| SS407 | `tween` 的目标超出参数的 `[min, max]` |
| SS408 | `ease` 只用于 `tween` |
| SS409 | （警告）声明了参数但没有表达式用到它 |
| SS410 | `readout` 写法不对（缺 `value`；`format: fraction` 和 `digits` 同时写；别的类型写了 `value` 等字段） |
| SS411 | 参数取到某个关键值时表达式没有定义，或点、三角形出了坐标范围 |

SS411 按文件顺序推演参数：初值、每个 `tween` 的中点和终点逐个代入，只看对象**在画面上**的那些时刻（例如 k 补间到 0 时截距读数 −b/k 没有定义，但那时读数还没出现，就不报）。渲染时 kit 的版式检查也在每个补间的起点、中点、终点采样包围盒，不只看 beat 结束那一帧。

### 7.6 分段播放、残影和常驻公式

小学集默认分段（规划 §3.2、《K12 数学学习路径科学分析》单集模板）：核心变形拆成 3–5 个子步，每步结束**定格**；上一步留下**淡色残影**；关键公式落地后**常驻**。四个内置动作：

```yaml
style: {segmented: true, step_hold: 1.0}
...
    do:
      - {at: s2, act: step}                       # 子步结束：分段时在这里定格 step_hold 秒
      - {at: s1, act: ghost, target: line, args: {place: above, gap: xl, scale: 0.75}}
      - {with: prev, act: erase, target: line}    # 残影留在上方，原对象接着变
      - {at: s1, act: unghost, target: line}      # 收掉 line 的残影
      - {after: prev, act: pin, target: law}      # 规则公式从此常驻
```

| 动作 | 作用 | 参数 |
|---|---|---|
| `step` | 子步结束。`style.segmented: true` 时画面在这一刻定住 `hold` 秒，旁白在同一时刻插入等长静音，之后的动作、句子、书签全部顺延；不分段时不定格，只把位置写进 `chapters.json`（hold 为 0） | `hold`：0–10 秒，默认取 `style.step_hold`（默认 1.0）。不写 `target`、`dur` |
| `ghost` | 给目标**此刻**的样子留一个淡色副本：全部改成 `DIM` 色、整体不透明度 0.3，画在所有对象后面；之后原对象怎么变，残影不动 | `place`：`stay`（原地，默认）/ `above` / `below` / `left_of` / `right_of`；`gap`：间距档位；`scale`：0.3–1；`opacity`：0.1–0.6 |
| `unghost` | 收掉目标留下的所有残影。目标被 `hide` 时残影也一起收掉 | 无 |
| `pin` | 目标从此常驻：之后不能 `hide` / `move`（包括它的片段）；`clear` 只清它 pin 之后加的装饰，pin 时已有的下划线、圈跟着常驻；布局求解器把它当固定占位，后出现的对象让开它 | 无 |

- **和强调状态分开**：`focus` 是描边框 + 其余元素调到 0.45 不透明度（颜色不变），`mark` 是淡金底色；残影是**灰色**（DIM 角色）、更淡、在最底层，学生不会把它当成"现在要看的东西"。mark 的底色不进残影。
- **定格放在句子开头**（`at: s2`）：句子之间本来就有停顿，插入静音不切断句子；写在书签或偏移上会警告。
- **残影只留上一步**：同时超过 2 个残影警告；旧的先 `unghost`。
- `ghost` 不自动定格、`step` 不自动留残影，两者正交；常见写法是同一时刻各写一个。
- 对象属性 `pin: top` 是"一开始就钉在顶上"（题卡）；动作 `pin` 是"从这一刻起留在原地"。
- 播放器：`chapters.json` 的 `stops` 列出所有子步定格（`time`..`resume`，连续播放时可以跳过这段定格）、预测 / 想一想暂停（带 `prompt` 和 `app_item`）和分段点（beat 末尾）。首看按分段点暂停，复看连续播放。
- 字幕默认开（2026-10-17 定）：`subtitles: burned`（默认）时 kit 把字幕烧进成片画面（画面整体缩到 88%，底部让出字幕带，不压住 footer），另出一份画面干净、带 mov_text 软字幕轨的 `<名>.clean.mp4` 给自己显示字幕的播放器；`soft` 只封装可关的软字幕轨；`none` 不出字幕。三种都导出 `.vtt` / `.srt`。文字是 `say` 的原文（去掉书签，公式转 Unicode），句子写了 `en` 时第二行是英文；时刻跟着定格顺延。

| 代码 | 问题 |
|---|---|
| SS440 | `ghost` / `unghost` 的 target 不是整个对象 |
| SS441 | （警告）`place: stay` 时写了 `gap` / `scale` |
| SS442 | （警告）`ghost` 的对象这时可能还没显示 |
| SS443 | `unghost` 的对象没有残影 |
| SS444 | `step` 写了 `target` 或 `dur` |
| SS445 | （警告）用了 `step` 但 `style.segmented` 不是 true |
| SS446 | （警告）分段时 `step` 写在书签或句中偏移上，会把一句话切开 |
| SS447 | `pin` 的 target 不是整个对象 |
| SS448 | 常驻的对象（`pin` 过，或 `pin: top`）又被 `hide` / `move` |
| SS449 | （警告）对象已经常驻，又 `pin` 一次 |
| SS450 | `pin` 时对象还没显示 |
| SS451 | （警告）写了 `style.step_hold` 但没有分段 |
| SS452 | （警告）同时在画面上的残影超过 2 个 |
| SS453 | （警告）一个 beat 里子步超过 5 个 |

参数类型（`place` 枚举、`scale` / `opacity` / `hold` 范围、`pin` / `unghost` 不带参数）由 JSON Schema 检查（SS100）。

---

### 7.7 其他语言版本（i18n）

同一个场景出英文配音版：画面、时间线、动作都不变，只换旁白和画面上的字。2026-10-18 起洞察 39 集都有英文版。

- 旁白：每句的 `en` 就是英文版要念的话，**书签要和 `text` 一样**——每个 `{@名}` 放在动作要落上的那个英文词前面（`check` 报 SS503：书签不一致；SS504：顺序不同）。中文版里 `en` 仍是双语字幕的第二行，书签不显示。
- 画面上的字写在顶层 `i18n.en`，键和文档本身一样，按 id 深合并（映射逐键合并，列表整个替换）：

```yaml
i18n:
  en:
    meta: {title: "The Pythagorean Theorem: Rearrange and See"}
    objects:
      wrong: {text: '[$a+b=c$]{#w}?'}          # 片段 id、公式原样保留，只译字
      practice: {lines: ["[Try it]{.HL}", "Short sides $3$ and $4$", "Long side $=$ ?"]}
    beats:
      Hook: {pause: {prompt: "How is the ladder c related to a and b?"}}
      Level: {do: {3: {args: {label: 'mean $4$'}}}}   # 动作参数里的字：按 do 的下标，只能改 args
```

- `say` 不能在 `i18n` 里覆盖。组件自带的中文默认字要在对象里写明：graph 割线读数 `readout_text`、复平面 `axis_labels`、coin_flips 的 `heads_text`。
- `scene_spec.localize(doc, "en")` 得到一份普通的英文场景（`say[].text` = 英文句、`style.lang: en`、没有 `i18n`）；`check` 会把它也完整查一遍（问题标 `[en]`），本地化后画面上还剩中文报 SS507。
- 直接用英文写的场景（English-first）：写 `style: {lang: en}`，句子只写 `text`，不需要 `en` 和 `i18n.en`；`localize(doc, "en")` 原样返回，`scene_spec.source_lang(doc)` 给出文件的源语言（`style.lang`，默认 `zh`）。
- 工具：`animind-voice synth|align|pitch --lang en`（英文合成指令、en-US、英文听写，数字拼成单词再对齐），`animind-kit render|inspect --lang en`（字幕只有英文一行，按小句切条）。英文版用单独的音频目录。

## 8. 检查规则（渲染前）

检查分四层，前三层都不需要渲染，几秒内出结果：

| 层 | 检查内容 | 失败时 |
|---|---|---|
| 1. 结构 | JSON Schema：字段、类型、枚举值 | 报错 |
| 2. 语义 | 引用的对象、片段、句子、书签都存在；没有色值；`line` 要求的字段齐全；`pedagogy.non_example` / `misconception` / `landing` 都被某个 beat 标注引用；`status: demo` 时旁白里有说明 | 报错 |
| 3. 时间 | 按 `voice` 缓存的真实时长（没有缓存时按字数估算），挂在同一句上的动作总时长不超过这一句；预测出来的"画面跟不上旁白"直接报出，对应现在渲染日志里的 `CUE LATE` | 报错或警告 |
| 4. 布局 | 求解器跑一遍：出框、重叠、字号低于下限；字形级检查（线穿字、字压字、小字、出画面，见 §6.4）需要排版结果，由 kit 的 `inspect` 在不编码视频的情况下几秒内给出 | 报错 |

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
  voice: {persona: teacher-hs, speed: 1.0}

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

> 写法注意（实现检查器时发现）：含 LaTeX 反斜杠的字符串要用**单引号**，双引号里 `\{` 会被 YAML 当成转义而报错；流式映射 `{...}` 里的选择器如 `"plan[0]"` 要加引号。完整的一支见 `animind/scene-spec/examples/s67-p01.scene.yaml`。

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
