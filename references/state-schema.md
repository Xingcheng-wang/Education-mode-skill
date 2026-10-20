# 状态文件规范

## 目录

```
<EDU_HOME>/
├── config.json
├── plan.md                        # 人可读的 Now / Next / Later
├── learner/
│   ├── profile.md
│   ├── glossary.md                # 全局术语表
│   ├── outlines/<topic-slug>.md     # 理论大纲（教学者的地图）
│   ├── plan.json                  # 方向、计划风格
│   ├── topics.json
│   ├── misconceptions.json
│   └── schedule.json
├── sessions/
│   └── 0001-2026-10-20-topic.md
├── notes/
│   └── <source-id>.md
├── sparks/
│   ├── index.json                 # 想法索引与状态
│   └── s0001.md                   # 单个 spark note
├── backup/
│   └── <timestamp>/               # forget 前自动备份
└── corpus/
    ├── inbox/
    └── <source-id>/
        ├── meta.json
        ├── chunks.jsonl
        └── text.txt
```

## 写入权限

| 文件 | 谁写 | 规则 |
|---|---|---|
| `config.json` | 用户；模型只能提示用户手动执行 `config --set retrieval_mode` | 模型不得自行改检索模式 |
| `learner/profile.md` | 模型/用户 | 可编辑；默认不保存原话 |
| `learner/glossary.md` | 模型/用户 | 术语首现时追加；不堆词典 |
| `learner/outlines/<topic-slug>.md` | 模型/用户 | 理论大纲；不是任务清单 |
| `learner/plan.json` | `edu.py` | 方向与计划风格；模型不手改 |
| `plan.md` | `edu.py` | 由 `plan` / `map` / `replan` 生成，不手改 |
| `learner/topics.json` | `edu.py` | 模型不手改 |
| `learner/misconceptions.json` | `edu.py` | 模型不手改 |
| `learner/schedule.json` | `edu.py` | 模型不手改 |
| `sessions/*.md` | 模型/`edu.py` | 按同意级别写；默认 `outline`，`off` 不写 |
| `notes/*.md` | 模型/用户 | 可编辑，保留来源标注 |
| `sparks/index.json` | `edu.py` | 想法索引；模型不手改 |
| `sparks/*.md` | `edu.py` | 由 `spark` 命令生成，不手改 |
| `backup/**` | `edu.py` | `forget` 前自动备份 |
| `corpus/**` | `edu.py` | 模型只读 |

Profile B（无脚本）时，用 `assets/templates/` 手工维护；JSON 改用 Markdown 表格，字段保持一致。

## config.json

```json
{
  "version": 2,
  "language": "auto",
  "hint_policy": "one_level_at_a_time",
  "retrieval_mode": "ask",
  "web_cache": true,
  "context_window": 1000000,
  "multimodal": false,
  "corpus_dir": "corpus",
  "review_algorithm": "sm2"
}
```

| 字段 | 说明 |
|---|---|
| `retrieval_mode` | `local` / `web` / `ask` / `auto`。`local` 严格禁止联网检索；**只有用户可以修改** |
| `web_cache` | 网页资料是否必须缓存后再引用；默认 `true` |
| `context_window` | 目标模型上下文，默认 1000000；仅用于策略提示 |
| `multimodal` | 是否支持图像；默认 `false`，不得假装看图 |
| `session_minutes` | 可选用户偏好；旧配置可能保留，但不再是默认值 |
| `max_explanation_words` | 可选用户偏好；旧配置可能保留，但不再是默认值 |

旧版 `allow_network` 会被自动迁移：`false → local`，`true → web`。迁移后不再使用该字段。

## learner/glossary.md

```markdown
# Glossary

| term | full form | plain meaning | example | first seen |
|---|---|---|---|---|
| LLM | Large Language Model，大语言模型 | 一种用大量文本训练、能生成语言的模型 | 用 LLM 解释概念 | 2026-10-20 |
```

- 术语第一次出现时追加一行；同一术语不重复解释。
- 输出格式：`中文（English, ABBR）——一句白话。例：……`
- 不做缩写汤；能白话就不缩写。

## learner/outlines/<topic-slug>.md

`topic-slug` 是 topic-id 把 `/` 换成 `-`，例如 `calculus/limits` → `calculus-limits.md`。

理论大纲是**教学者的地图**，不是学习者的任务清单。建议包含：

```markdown
# Theory Outline: <topic>

- 核心问题：
- 核心概念与关系：
- 先修：
- 常见误解：
- 经典例子/实验：
- 可能的入口/钩子：
- 评估证据：
- 路径与主干/枝叶：
```

- 系统学习、精读、技能训练开始前准备。
- 学习者可以看简化版，也可以不看；不要把它倒成待办清单。
- 大纲可以改；模型负责提醒先修/连贯性。

## learner/plan.json

```json
{
  "version": 1,
  "direction": "理解微积分如何描述变化与累积",
  "style": "inquiry",
  "updated": "2026-10-20"
}
```

- `direction`：可修改的大方向；空值合法。
- `style`：`inquiry`（探究型）或 `project`（项目型）。
- `plan.md` 由 `plan` / `map` / `replan` 生成；不要手改 JSON。

## corpus/meta.json

```json
{
  "id": "paper-x",
  "title": "Paper Title",
  "source_path": "C:/Users/root/.edu/corpus/inbox/paper-x.pdf",
  "format": "pdf",
  "source_kind": "local",
  "url": "",
  "retrieved_at": "",
  "created": "2026-10-20",
  "chars": 48210,
  "chunks": 63
}
```

- `source_kind`: `local` | `web`
- 网页来源必须有 `url` 与 `retrieved_at`
- `chunks.jsonl` 每行包含 `id`、`source`、`locator`、`text`、`url`（本地来源为空字符串）

## topics.json

```json
{
  "version": 1,
  "items": [
    {
      "id": "calculus/limits",
      "title": "极限",
      "prereqs": [],
      "status": "learning",
      "understanding": 2,
      "confidence": "medium",
      "understanding_range": [1, 2],
      "evidence": [
        {"date": "2026-10-20", "type": "predict", "result": "partial", "confidence": 2}
      ],
      "last_calibrated": "2026-10-20",
      "next_check": "2026-10-24",
      "why": "想理解连续与逼近",
      "horizon": "now",
      "next_action": "用数列例子说清极限",
      "sessions": 1,
      "last_seen": "2026-10-20",
      "next_review": null
    }
  ]
}
```

- `status`: `new` | `learning` | `review` | `mastered`（仅内部使用，不向用户展示等级）
- `understanding`: 0–3，描述性状态：0 刚接触 / 1 能复述 / 2 能解释或应用 / 3 能迁移或创造
- `confidence`: `low` | `medium` | `high`，表示模型对这个判断有多确定。
- `understanding_range`: `[low, high]`，表示可能区间；不是分数。
- `evidence`: 少量探针记录，字段为 `date` / `type` / `result` / `confidence`。
- `last_calibrated` / `next_check`: 上次校准与下次建议复校日期；`next_check` 只是提醒。
- `why`: 节点与大方向的关系。
- `horizon`: `now` | `next` | `later`。
- `next_action`: 这个节点当前最小的下一步。
- **默认 `outline` 会话记录不写入理解状态**；该字段只用于内部接续。
- `id`: 稳定的 `领域/主题`，小写，空格用 `-`
- 旧字段 `mastery` 会自动迁移为 `understanding`；不要手改 JSON

## misconceptions.json

```json
{
  "version": 1,
  "items": [
    {
      "id": "M0001",
      "topic_id": "calculus/chain-rule",
      "wrong_model": "把内层函数当成常数",
      "evidence": "",
      "correction": "先对外层求导，再乘内层导数",
      "status": "open",
      "created": "2026-10-20"
    }
  ]
}
```

- `evidence` 默认空；只有用户选择 `verbatim` 时才保存原话。
- `status`: `open` | `resolved` | `recurring`

## schedule.json

```json
{
  "version": 1,
  "items": [
    {
      "id": "r0001",
      "topic_id": "calculus/chain-rule",
      "question": "为什么链式法则要乘内层导数？",
      "answer": "因为外层变化率要按内层的变化率缩放。",
      "ease": 2.5,
      "interval": 1,
      "reps": 0,
      "lapses": 0,
      "due": "2026-10-21",
      "active": true,
      "last_grade": null,
      "created": "2026-10-20"
    }
  ]
}
```

- `due` 是**建议日期**，不是到期债务。
- `active: false` 表示学习者暂停了这条；`reviews` 默认不列出。
- `grade` / `lapses` / `ease` 只作为内部建议参数，不向用户展示。
- 复习由学习者发起；不显示"到期数量""逾期"。

## sparks/index.json

```json
{
  "version": 1,
  "items": [
    {
      "id": "s0001",
      "title": "统一 LLM 记忆格式",
      "claim": "用一套格式/协议统一记忆的组织、存储与迁移",
      "why_now": "agent 记忆碎片化",
      "why_me": "我在做学习记录",
      "type": "design",
      "status": "seed",
      "next_move": "read",
      "riskiest_assumption": "厂商没有采用动机",
      "smallest_test": "两个系统导出导入再导出，测语义损失",
      "prior_art": [
        {"source": "W3C AI Agent Memory Interop CG", "relation": "adjacent", "note": "标准化讨论"}
      ],
      "created": "2026-10-20",
      "updated": "2026-10-20"
    }
  ]
}
```

- `type`: `question` | `hypothesis` | `design` | `project`
- `status`: `seed` | `exploring` | `parked` | `project`
- `next_move`: `park` | `read` | `test` | `project` | `curiosity` | `systematic` | `skill-drill` | `deep-read`
- `prior_art[].relation`: `solved` | `adjacent` | `open` | `different`
- `sparks/s0001.md` 是同一内容的人可读版本；`park` 是合法结果，没有提醒或排名。

## 滚动计划

| 命令 | 作用 |
|---|---|
| `plan` | 从 `plan.json` + `topics.json` 生成 `plan.md`，显示 Now / Next / Later |
| `map --action add/update/drop` | 学习者增删改节点；模型只建议 |
| `replan` | 复盘方向与视野；可更新 `direction` / `style` |
| `calibrate --topic-id` | 查看当前假设、置信度、证据，并给出 2–3 个探针的建议 |
| `spark add/list/show/update/prior-art/route` | 捕获想法、查先行工作、更新状态、路由到其他模式 |

`plan.md` 不显示完成率、覆盖率或理解等级；它只显示方向、节点、why 和 next action。

Spark 路由：

| `--to` | 结果 |
|---|---|
| `curiosity` | 先弄懂一个子问题 |
| `deep-read` | 精读先行工作 |
| `systematic` | 加进问题地图 |
| `skill-drill` | 做最小原型 |
| `project` | 转项目型滚动计划 |

## 会话记录

命名：`NNNN-YYYY-MM-DD-<slug>.md`，四位递增，不重复使用编号。
会话开始时问一次记录偏好：`off` / `outline` / `verbatim`。

### outline（默认）

```markdown
# Session 0001 — 2026-10-20 — curiosity

- Topic: calculus/chain-rule
- Mode: curiosity
- Retrieval: local
- 记录同意: outline

## 本轮概要（只记大纲，不含原话）

<用户确认过的简短概要>

## 误解

- none

## 下一步

- <一个具体动作>

## 可选复习

- suggested: 2026-10-23
```

### verbatim（明确同意）

```markdown
# Session 0001 — 2026-10-20 — curiosity

- Topic: calculus/chain-rule
- Mode: curiosity
- Retrieval: local
- 记录同意: verbatim

## 用户表达

<用户原话或作品>

## 观察

- 理解状态: 能解释或应用
- 支持程度: H2

## 用户原话（已同意）

- <短引>

## 误解

- <wrong model>（证据：……）

## 下一步

- <一个具体动作>
```

### off

不创建会话文件，不更新 topic/misconception/schedule。

## 记录控制

| 命令 | 作用 |
|---|---|
| `records` | 列出已存会话的元数据：日期、主题、模式、同意级别、是否含原话 |
| `session --id` | 显示单条记录；outline 记录会标注"不含原话" |
| `export --to <zip或目录>` | 导出 config/learner/sessions/notes/sparks；`--include-corpus` 可含资料索引 |
| `forget --session/--topic/--spark/--all` | 默认 dry-run；`--apply` 才删除，删除前自动备份到 `backup/<timestamp>/`；`--topic` 也会删除对应理论大纲 |

## 记录规则

1. 只记录实际发生的内容；没有回答写 `unassessed`。
2. 默认只记大纲；原话只在 `verbatim` 同意下保存。
3. 修正判断用新记录 + `supersedes: <旧记录>`，不覆盖旧记录。
4. 不写"用户已掌握"；只写"现在能解释/应用/迁移"以及证据。
5. 默认追加；学习者可以用 `forget` 删除或遗忘。
6. 记录是给学习者下次接上的，不是成绩单；不写排名、分数、等级、连续天数。
