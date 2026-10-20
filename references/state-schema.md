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
| `config.json` | 用户/初始化 | 模型只读 |
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
  "version": 1,
  "language": "auto",
  "session_minutes": 20,
  "max_explanation_words": 180,
  "mastery_threshold": 2,
  "hint_policy": "one_level_at_a_time",
  "allow_network": false,
  "corpus_dir": "corpus",
  "review_algorithm": "sm2"
}
```

`allow_network` 必须为 `false`；`validate` 会对此告警。

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
      "mastery": 2,
      "sessions": 1,
      "last_seen": "2026-10-20",
      "next_review": "2026-10-23"
    }
  ]
}
```

- `status`: `new` | `learning` | `review` | `mastered`
- `mastery`: 0–3，取四维中的最低分
- `id`: 稳定的 `领域/主题`，小写，空格用 `-`

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

## 用户产出
<用户的原话或作品，保留原样>

## 评估
- 准确性: 2
- 因果链: 1
- 边界: 1
- 迁移: 未测
- 最高提示: H2

## 误解
- <wrong model>（证据：……）

## 下一步
- <一个具体动作>

## 复习
- r0001 due 2026-10-23
```

## 证据规则

1. 只记录实际发生的内容；没有回答写 `unassessed`。
2. 证据优先用用户原话，其次用可观察行为。
3. 修正评估用新记录 + `supersedes: <旧记录>`，不覆盖旧记录。
4. 不写"用户已掌握"而没有分数和证据。
5. 会话记录只追加；文件损坏时新建文件，不删除旧文件。
