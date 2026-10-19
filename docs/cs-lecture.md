# 编程课视频：scene-spec 怎么描述（设计说明，2026-10-19）

目标：大学 CS 课的视频（AIE1001 Python 入门、CSC4801 AI 辅助软件工程）能写成 scene-spec，由 kit 在墨线上渲染，
画面不比现在手写的 Manim 场景（课程仓库里的 `kit/cs_style.py`）差，这样两门课以后可以整体换到墨线。
这里列出这些场景用到的东西，以及每样怎么落到 scene-spec 和 kit/mx 上。

## 现在的画面用了什么

读的是 `cs_style.py`、AIE1001 第 6 讲第 1 部分（递归）、CSC4801 第 3 讲（上下文工程）：

| 部件 | Manim 里的写法 | 用来做什么 |
|---|---|---|
| 页眉 | `corner()` + `heading()` | 左上角的课程 / 部分小字，下面是标题和一小段琥珀色短线 |
| 代码面板 | `code_block()`（pygments friendly 配色）、`line_mark()`、`pointer()` | 白底卡片上的高亮代码；整行宽的底色条；Python Tutor 式的「下一行」箭头；框住一行里的一段 |
| 终端 | `terminal()` | 深色面板上的程序输出，保留行首空格（缩进往往就是重点），报错行用浅红 |
| 调用栈 | `stack_frame()`、`global_frame()` | 帧从「global frame」往上压，右边是状态标签（waiting、returns 1） |
| 名字 → 对象 | `binding()`、`rebind()`（AIE1001 第 3 讲） | 环境图：名字、箭头、值框 |
| 卡片、胶囊、要点 | `card()`、`pill()`、`number_tag()`、`bullets()`、`chip()` | 浅底卡片带彩色竖条；实心标签；编号列表 |
| 流程图 | 各讲自己写的 `flow()`（CSC4801 的 agent 循环） | 格子上的方框和判断菱形，直线箭头和折线箭头 |
| 图片 | `ImageMobject`（CSC4801 的课件首页末页） | 整屏的课件页或框里的截图 |
| 公式 | `MathTex`、`TransformMatchingTex`、`Brace` | 阶乘的定义 |
| 强调 | `Indicate`、`SurroundingRectangle`、`Cross`、`CurvedArrow` | 闪一下、框起来、打叉、「跳回开头」的弯箭头 |

配色：浅纸色底，青色管结构，海绿第二，琥珀色是「看这里」，红色只给错误，石灰色给次要文字。字体：正文 Inter，代码 Source Code Pro。

## 怎么映射

大部分是新组件；有三处在格式层面。

**格式层面（Schema + 检查器）**

- `meta.line: lecture`：大学课程讲座。不要求教学字段（一讲很长、讲很多点）；`at:` 和 `worked` 一样允许，给警告。
- `style.layout: lecture`：像幻灯片一样的分区模板，字号层级也照 cs_style（display 80、title 40、body 30、caption 24）。`top` 是一条窄带（只放页眉，1.4 个单位高），`stage` 占其余部分，
  `side` 是右半边（两栏页面：左边代码，右边调用栈或终端）。默认模板不变。
- `style.fonts: {text: Inter, code: Source Code Pro}`：西文正文和代码的字体。字体是各台机器的资源、不是颜色，所以放在 `style`；
  系统里没有这个字体时 kit 退回它默认的中文字体。
- palette 里加一套 `classroom` 主题（纸色 `#F6F5F1`，A 青、B 海绿、C 和 HL 琥珀、NO 红、DIM 石灰），场景文件里照样只写角色。

**组件（在 scene-spec 登记检查，在 kit/mx/cs.py 实现）**

| 组件 | 参数 | 暴露 | 动作 |
|---|---|---|---|
| `heading` | `text`、`kicker`（上面的小字） | `#title`、`#kicker` | `retitle {text, role}`（换标题，小字不动：一讲只用一个页眉对象） |
| `code` | `src`、`numbers`、`spans: {id: {line, text}}` | `line[i]`、`#id`（一行里的一段） | `highlight {lines, role}`、`unhighlight {lines?}`、`point {line}`、`unpoint`、`jump {from, to, role}`（左边的弯箭头）、`unjump` |
| `terminal` | `lines`（字符串或 `{text, role}`）、`cols`（最少几个字符宽） | 每行一项 | 内置的 `show obj[i]` |
| `call_stack` | `depth`（几个帧位）、`base`（底帧的字，默认 global frame）、`label`（底下的说明）、`cols`（帧宽）、`note_cols`（右边状态标签留几个字宽，默认 16） | `frame[i]`、`value[i]`、`note[i]`（按压栈顺序）、`base` | `push {name, vars, role}`、`pop`、`note {text, role, frame, mono}`、`unnote {frame?}` |
| `bindings` | `names`、`objects: {id: 值}`、`bind: {名字: 对象}` | `name[i]`、`object[i]`、`arrow[i]` | `rebind {name, to}`、`update {object, value}` |
| `card` | 单张卡片：`title`、`body`、`role`、`mono`、`cols` / `rows`（最小宽高，按正文字数和行数） | `#title`、`#body` | — |
| `cards` | `items: [{title, body, role, mono, note}]`、`cols` / `rows` | 每张卡一项、`note[i]`（卡片下面的小字，一开始藏着） | 内置的 `show obj[i]`、`show obj.note[i]` |
| `pill` | `text`、`role`、`filled`、`mono` | — | — |
| `bullets` | `items`、`role` | 每条一项 | 内置的 `show obj[i]` |
| `flow` | `nodes: {id: {text, row, col, shape, role}}`、`edges: [{from, to, label, via}]` | `#节点`、`edge[i]` | 内置的 focus / mark 指向 `#节点` |
| `image` | `src`（相对场景文件） | — | — |
| `queue` | `people`、`you`、`label` | `person[i]`、`you` | `ask`（问号气泡传到队首）、`number`（答案一个个传回来） |

`flow` 的行列、`code` 的行号都是逻辑位置，不是画面坐标，「不写坐标」的规则照旧。`call_stack.depth` 和 `terminal.cols`
预先留出位置：压栈时组件的包围盒不变，布局只解一次。

检查器按动作顺序推演调用栈（空栈不能 pop，帧数不超过 `depth`），核对代码行号和片段文字在 `src` 里，做法同 `wallet`、`balance`。

墨线后端还没有 `row` / `stack` 容器（`type: group`），几个对象排成一行时第一个会被居中、其余挤到右边；所以并排的卡片做成一个 `cards` 组件。

**其余用内置动作。** 闪一下（`Indicate`）用 `focus` / `unfocus` 或 `mark`；`SurroundingRectangle` 是 `circle`；`Cross` 是 `cross`；
`TransformMatchingTex` 是 `transform` 加 `match: tex`；公式下的大括号改成片段加 `underline`。

**墨线**加一种 `ImageNode`（把位图画进一个框），`image` 不必依赖 Manim。

## 还没覆盖

- 各讲自己画的图（CSC4801 的磁盘、内存条、上下文窗口条、跷跷板）：要么各做一个组件，要么走 `custom` beat；墨线后端还没有 `custom` 的接口。
- 打字动画（终端里一个字一个字出现）、代码里光标连续移动。
- CSC4801 的品牌包装（片头 logo、角标、片尾卡）留在 animind 外面：那是私有的品牌素材。
