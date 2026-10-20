# 状态文件规范

## 目录

```
<EDU_HOME>/
├── config.json
├── learner/
│   ├── profile.md
│   ├── topics.json
│   ├── misconceptions.json
│   └── schedule.json
├── sessions/
│   └── 0001-2026-10-20-topic.md
├── notes/
│   └── <source-id>.md
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
| `config.json` | 用户/初始化；模型通过 `edu.py config` 修改 | 模型不直接手改 |
| `learner/profile.md` | 模型 | 可编辑；保留用户原话 |
| `learner/topics.json` | `edu.py` | 模型不手改 |
| `learner/misconceptions.json` | `edu.py` | 模型不手改 |
| `learner/schedule.json` | `edu.py` | 模型不手改 |
| `sessions/*.md` | 模型/`edu.py` | 只追加，不覆盖 |
| `notes/*.md` | 模型 | 可编辑，保留来源标注 |
| `corpus/**` | `edu.py` | 模型只读 |

Profile B（无脚本）时，用 `assets/templates/` 手工维护；JSON 改用 Markdown 表格，字段保持一致。

## config.json

```json
{
  "version": 2,
  "language": "auto",
  "session_minutes": 20,
  "max_explanation_words": 250,
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
| `retrieval_mode` | `local` / `web` / `ask` / `auto`。`local` 严格禁止联网检索 |
| `web_cache` | 网页资料是否必须缓存后再引用；默认 `true` |
| `context_window` | 目标模型上下文，默认 1000000；仅用于策略提示 |
| `multimodal` | 是否支持图像；默认 `false`，不得假装看图 |

旧版 `allow_network` 会被自动迁移：`false → local`，`true → web`。迁移后不再使用该字段。

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
      "id": "calculus/chain-rule",
      "title": "链式法则",
      "prereqs": ["calculus/derivative"],
      "status": "learning",
      "understanding": 2,
      "sessions": 1,
      "last_seen": "2026-10-20",
      "next_review": "2026-10-23"
    }
  ]
}
```

- `status`: `new` | `learning` | `review` | `mastered`（仅内部使用，不向用户展示等级）
- `understanding`: 0–3，描述性状态：0 刚接触 / 1 能复述 / 2 能解释或应用 / 3 能迁移或创造
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
      "evidence": "用户说：外层求导后就不再管里面了",
      "correction": "先对外层求导，再乘内层导数",
      "status": "open",
      "created": "2026-10-20"
    }
  ]
}
```

`status`: `open` | `resolved` | `recurring`

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
      "last_grade": null,
      "created": "2026-10-20"
    }
  ]
}
```

## 会话记录

命名：`NNNN-YYYY-MM-DD-<slug>.md`，四位递增，不重复使用编号。

```markdown
# Session 0001 — 2026-10-20 — curiosity

- Topic: calculus/chain-rule
- Goal: 能解释链式法则为什么成立
- Time box: 10 min
- Mode: curiosity

## 用户表达
<用户的原话或作品，保留原样>

## 观察
- 理解状态: 能解释或应用
- 支持程度: H2
- 证据:
  - <用户原话或可观察行为>

## 误解
- <wrong model>（证据：……）

## 下一步
- <一个具体动作>

## 复习
- r0001 due 2026-10-23
```

## 证据规则

1. 只记录实际发生的内容；没有回答写 `unassessed`。
2. 证据优先用用户原话，其次用可观察行为或作品片段。
3. 修正判断用新记录 + `supersedes: <旧记录>`，不覆盖旧记录。
4. 不写"用户已掌握"；只写"现在能解释/应用/迁移"以及证据。
5. 会话记录只追加；文件损坏时新建文件，不删除旧文件。
6. 记录是给学习者下次接上的，不是成绩单；不写排名、分数、等级、连续天数。
