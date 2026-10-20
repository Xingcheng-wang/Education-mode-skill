# Education Mode（离线教育模式）

一个可以装进本地大模型 Agent 的对话式学习 skill：**不联网、不依赖云端、把状态与排程交给本地脚本，把教学留给模型**。

适用于离线生产机器、内网环境、数据不能出机器的场景，也适用于任何希望在本地模型上获得稳定教学体验的场合。

- 版本：0.1.0
- 形态：Agent Skill（`SKILL.md` + 按需加载的 references + 纯标准库脚本）
- 许可：MIT

---

## 一、设计初衷

### 1. 学习不发生在模型的输出里

大多数 AI 学习产品在优化"生成内容"：更长的总结、更完整的课程、更漂亮的笔记、更快的答案。但学习发生在学习者身上：

- 先有预测，再有反馈；
- 先有提取，再有巩固；
- 先犯错，再修正；
- 先能解释，才算理解。

一个只会输出的系统，很容易制造"我看懂了"的错觉。所以这个 skill 的第一条产品规则不是"讲得更好"，而是**学习者必须产出**：每次会话至少有一次由用户完成的解释、应用或解题。没有产出的会话，不算教学。

### 2. 目标环境是离线生产机器

这个 skill 从第一天就是按下面的约束设计的：

- **没有网络**：不能搜索、不能调用云端 API、不能用云端向量库；
- **本地模型**：上下文可能只有 8k–32k，指令遵循和工具调用不稳定；
- **数据不能出机器**：资料、对话、学习记录必须留在本机；
- **需要可审计**：为什么判用户"掌握"、为什么安排这次复习，必须有证据可查。

现成的教育类开源项目——tutor-mcp、DeepTutor、OpenMAIC、noema——大多是完整应用或研究系统，带数据库、Web UI、服务进程，不能直接塞进一个 agent skill。现有教育类 skill 则多为教师备课或单一用途，缺少一个覆盖"好奇心、系统学习、技能训练、文本精读"的统一离线循环。

### 3. 因此做出的核心取舍

| 维度 | 常见做法 | 本 skill |
|---|---|---|
| 教学内容 | 一次生成完整课程 | 一次一个微单元，学习者产出后再继续 |
| 学习状态 | 依赖模型上下文记忆 | 落盘到本地 Markdown/JSON，脚本维护 |
| 资料检索 | 云端向量库 / embedding RAG | 本地 BM25，纯 Python 标准库 |
| 复习安排 | 模型自行提醒 | SM-2 脚本计算到期日 |
| 掌握判定 | 模型自评"已掌握" | 四维 rubric + 用户原话证据 |
| 论文/书籍 | 全文摘要 | triage → structure → deep read → synthesis |
| 能力不足时 | 报错中断 | 三档降级，纯对话也能继续教 |

一句话概括：**生成式教学，确定性状态**（Generative teaching, deterministic state）。

---

## 二、设计立场

1. **教，不是替用户读。**
   AI 不做摘要替代品。精读时先 triage，再让用户预测、复述、评价；读完要能重建论证。

2. **生成与判断分离。**
   模型负责讲解、提问、评估；状态、检索、排程、校验交给脚本。模型不擅长长时间记住学习历史，也不应该自己发明复习计划。

3. **证据优先。**
   "听懂了""讲过了""复习了三次"都不等于掌握。掌握必须由四维评分（准确性、因果链、边界、迁移）和一次成功迁移来支持，并附用户原话或可观察行为。

4. **少而稳的机制。**
   只使用证据较强的学习机制：检索练习、间隔重复、交错练习、合意难度、示例消退、自我解释、生产性失败。明确不使用学习风格 / VAK 理论。

5. **可降级。**
   有 shell 用脚本；只有文件读写用模板；纯对话用 STATE BLOCK。任何一档都不需要联网，也不会因为缺少工具而中断教学。

---

## 三、四种模式

| 模式 | 用户信号 | 时间盒 | 核心产出 |
|---|---|---|---|
| `curiosity` 好奇心 | "为什么/是什么/解释一下" | 5–10 分钟 | 一个正确的心理模型 + 一个继续探索的钩子 |
| `systematic` 系统学习 | "从零学/给个计划/系统学" | 多次，每次 15–25 分钟 | 5–12 个节点的主题图 + 掌握证据 |
| `skill-drill` 技能训练 | "练习/提升/给我反馈" | 多次，短回合 | 一个可观察的短板 + 一次成功迁移 |
| `deep-read` 精读 | "读论文/这本书/这一章" | 20–45 分钟 | 能重建论证的笔记 + 评价 |

所有模式共用同一个七步循环：

```
诊断 → 微教学 → 学习者产出 → 评估 → 提示 → 迁移 → 记录
```

### 提示阶梯

| 级别 | 动作 |
|---|---|
| H0 | 复述问题，确认目标 |
| H1 | 指出缺口位置，不给内容 |
| H2 | 给概念性提示（类比、对比、关键词） |
| H3 | 给程序性提示（下一步做什么） |
| H4 | 给完整示例，再做相似题 |
| H5 | 直接给答案，之后必须复述或重做 |

默认从 H1 开始，一次只升一级；记录本次最高提示级别，作为评估证据。

### 一个最小示例

```
用户：sin(2x) 的导数是 cos(2x) 吧？
模型：先不看 2x。外层是 sin(u)，它对 u 的导数是什么？
用户：cos(u)。
模型：对。那 u = 2x 自己对 x 的变化率是多少？
用户：……2？
模型：对。两层变化率要怎么合起来？
用户：相乘，所以是 2cos(2x)。
模型：正确。下次遇到 e^(x^2)，先找哪两层？
```

---

## 四、架构

```
.
├── SKILL.md                     # 入口：硬规则、模式路由、通用循环
├── README.md
├── LICENSE
├── config.example.json
├── references/
│   ├── minimal-core.md          # <8k 上下文的极简内核
│   ├── modes/
│   │   ├── curiosity.md
│   │   ├── systematic.md
│   │   ├── skill-drill.md
│   │   └── deep-read.md
│   ├── pedagogy/
│   │   ├── assessment.md        # 四维评分、误解分类、反馈措辞
│   │   └── memory.md            # 检索、间隔、交错、SM-2
│   ├── state-schema.md          # 状态字段与写入规则
│   ├── local-models.md          # 小模型适配指南
│   └── offline-sources.md       # 本地资料接入与引用规范
├── assets/templates/            # 无脚本时的手工状态模板
├── scripts/edu.py               # 纯标准库：索引 / BM25 / SM-2 / 记录 / 校验
└── evals/rubric.md              # 8 个离线验收用例
```

### 三层加载

`SKILL.md` 是路由和硬规则，具体模式按需加载，避免小上下文模型被无关内容挤爆：

| 上下文 | 加载 |
|---|---|
| < 8k | 只加载 `references/minimal-core.md` |
| 8–16k | 只加载 `SKILL.md` |
| 16–32k | `SKILL.md` + 一个模式文件 |
| > 32k | 再加一个 pedagogy 文件 |

### 三种运行档位

| 档位 | 条件 | 状态维护 |
|---|---|---|
| A | 有 shell + Python | `edu.py` 维护 JSON |
| B | 有文件读写、无 shell | `assets/templates/` 手工 Markdown |
| C | 纯对话 | 每轮输出 STATE BLOCK |

### 本地状态引擎

`scripts/edu.py` 只使用 Python 标准库，提供：

- `init` / `doctor`：初始化与离线环境检查
- `ingest`：索引 txt / md / epub / pdf（PDF 优先 `pdftotext`，其次 `pypdf`）
- `search`：本地 BM25，中文按单字 + 双字切分
- `add-review` / `due` / `review`：SM-2 间隔重复
- `checkpoint`：追加会话记录、更新主题与误解
- `validate`：检查状态文件完整性

默认学习工作区是 `~/.edu`，可用 `EDU_HOME` 覆盖。所有数据留在本机。

---

## 五、参考来源

这个 skill 的设计建立在一批开源项目和教学研究之上。**没有复制任何项目的代码**；以下标注的是"参考了什么设计"。

### 对话教学与学习 skill

| 项目 | 参考内容 | 许可证 / 说明 |
|---|---|---|
| [mattpocock/skills — teach](https://github.com/mattpocock/skills) | Mission-first；教学工作区（lessons / reference / learning-records）；ZPD；desirable difficulty；检索、间隔、交错；测验选项等长与位置随机；来源引用 | 以仓库为准 |
| [GarethManning/education-agent-skills](https://github.com/GarethManning/education-agent-skills) | 165 个有证据标注的教育 skill；Domain 20 的学生端能力：渐进提示、信心校准、错误诊断、teach-back、生产性失败、SRL 会话包装、脚手架消退；明确排除学习风格 | CC BY-SA 4.0 |
| [anthropics/k12-teacher-skills](https://github.com/anthropics/k12-teacher-skills) | skill 与 `evals/` 一起交付；基于 documented misconceptions 设计干扰项；每个回答映射下一步教学动作；优雅降级 | 以仓库为准 |
| [max-astro/paper-reading-skills — read-paper](https://skillsmp.com/ko/creators/max-astro/paper-reading-skills/skills-read-paper) | 四阶段精读：triage → structure map → deep read（method / math / evidence）→ synthesis；三副眼镜；自然停顿点的苏格拉底提问；"主动阅读，不是被动消费" | 以仓库为准 |
| [silentdog918/book-reader-skill](https://github.com/silentdog918/book-reader-skill) | 基于 Adler《如何阅读一本书》的四层次阅读法：基础 → 检视 → 分析 → 主题 | 以仓库为准 |
| [koukekoukej-glitch/feynman-tutor](https://github.com/koukekoukej-glitch/feynman-tutor) | 反转师生关系：让用户教 AI，通过追问暴露理解断层 | 以仓库为准 |
| [michael-uplive021/learning-practice-coevolution](https://github.com/michael-uplive021/learning-practice-coevolution) | "一循环三角色"：Mentor / Digital Apprentice / Observer；学习者先说；一轮必须产出真实迁移练习和下一个学习目标 | MIT |
| [wangyendt/wayne-skills — learning-tutor](https://skillsmp.com/creators/wangyendt/wayne-skills/learning-tutor) | 诊断 → 15–25 分钟微课 → 迁移；显式会话开关；提示分级；`unassessed` 与 `supersedes` 的证据纪律；confidence ≠ mastery | 以仓库为准 |

### 完整学习系统 / ITS

| 项目 | 参考内容 | 许可证 |
|---|---|---|
| [ArnaudGuiovanna/tutor-mcp](https://github.com/ArnaudGuiovanna/tutor-mcp) | "Generative teaching. Deterministic pedagogy."；BKT + FSRS + 先修图；掌握度门槛放行 Feynman/迁移探测；冻结 rubric；两个工具的最小接口 | MIT |
| [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) | 辅导与出题互相反馈；trace forest 三级记忆；带证据的误解清单；出题器与验证器分离；子目标具体化 | Apache-2.0 |
| [THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC) | 文档 → 多智能体课堂；大纲 → 场景；教师/同学角色互相质疑；可恢复会话 | MIT |
| [aislamsilvalol-ctrl/noema](https://github.com/aislamsilvalol-ctrl/noema) | 概念知识图谱 + 先修关系；0–100 掌握度；FSRS；Mistake Bank；Explain / Socratic / Examiner / Study Partner / Feynman Evaluator 五种导师模式；强制引用 RAG | AGPL-3.0 |
| [LuoHaomin/read-paper](https://github.com/LuoHaomin/read-paper) | 中文论文精读与按类型适配模板 | 以仓库为准 |

### 学习科学依据

本 skill 使用的机制来自以下研究方向（只列概念与代表文献，不复制原文）：

- **检索练习**：Roediger & Karpicke (2006), *Test-enhanced learning*.
- **间隔重复**：Cepeda et al. (2006), *Distributed practice in verbal recall tasks*.
- **交错练习**：Rohrer & Taylor (2007), *The shuffling of mathematics problems improves learning*.
- **最近发展区**：Vygotsky (1978).
- **生产性失败**：Kapur (2008), *Productive failure*.
- **自我解释**：Chi et al. (1989).
- **示例消退**：Renkl & Atkinson (2003).
- **刻意练习**：Ericsson et al. (1993).
- **形成性反馈**：Black & Wiliam (1998).
- **反证：学习风格**：Pashler et al. (2008), *Learning styles: Concepts and evidence* — 本 skill 明确不采用。

### 明确没有采用

- 云端 embedding / 向量数据库 / 远程 RAG
- 完整 BKT / FSRS 参数拟合（改用可解释的 SM-2）
- 多智能体课堂与实时白板（对本地小模型过重）
- 学习风格 / VAK / 左右脑理论
- 自动 LLM 评审（离线成本高，改为人工 rubric）
- 联网搜索与"实时补资料"
- 一次生成完整课程或整本书摘要

---

## 六、安装

### 作为 Claude Code skill

```bash
git clone https://github.com/Xingcheng-wang/Education-mode-skill.git ~/.claude/skills/education-mode
```

### 其他 Agent 框架

把 `SKILL.md` 作为系统提示；脚本路径改为绝对路径；无 shell 时使用 `assets/templates/` 或 STATE BLOCK 模式。

### 初始化

```bash
python ~/.claude/skills/education-mode/scripts/edu.py init
python ~/.claude/skills/education-mode/scripts/edu.py doctor
```

默认工作区：`~/.edu`。可用环境变量 `EDU_HOME` 指定到其他位置。

### 首次使用

```bash
# 1. 把资料放进 inbox
cp book.pdf ~/.edu/corpus/inbox/

# 2. 建立本地索引
python ~/.claude/skills/education-mode/scripts/edu.py ingest \
  --file ~/.edu/corpus/inbox/book.pdf --id book-x

# 3. 在 Agent 中启动
#    /education-mode
#    或直接说："用教育模式帮我精读 book-x"
```

---

## 七、评测

`evals/rubric.md` 提供 8 个离线用例，覆盖：

1. 好奇心模式先诊断再讲解
2. 用户要求直接答案时不强迫苏格拉底
3. 系统学习只建小主题图
4. 技能训练先做基线
5. 精读先 triage、不伪造引用
6. 本地没有资料时诚实标注
7. 误解诊断与提示阶梯
8. 无 shell 时的降级

通过标准：至少 7/8。红线任一失败即不通过：联网、编造来源、无用户产出、把摘要当精读。

评测需要人工勾选，不依赖 LLM 评审；建议在目标生产机器上用实际模型和量化版本跑一遍。

---

## 八、已知限制

- PDF 需要 `pdftotext`（poppler）或 `pypdf`；扫描版需先离线 OCR。
- SM-2 是简化实现，不包含 FSRS 参数拟合。
- 无内置语音、图片理解、多模态。
- 4k–8k 上下文模型只能使用 `minimal-core.md`，无法做多会话主题图。
- 本地模型的指令遵循差异较大；上线前应按 `evals/rubric.md` 做模型特定验收。
- 会话记录可能包含用户原话；共享机器需设置目录权限。

---

## 九、后续工作

- 增加真实论文 PDF / EPUB 的分页与章节定位测试。
- 可选 FSRS 排程后端，同时保留 SM-2 作为默认。
- 多学习者档案与班级级汇总（仍保持本地）。
- 为目标模型补充自动化回归脚本；当前 rubric 为人工验收。
- 可选本地 OCR 钩子（不内置模型，只调用已有工具）。

---

## 十、致谢

感谢上述开源项目的作者与维护者。他们的公开设计让这个离线 skill 能在短时间内形成清晰的架构。所有引用项目的版权与许可证归各自作者所有；本项目未复制其代码，若后续引入将按相应许可证标注。

---

## License

[MIT](LICENSE)
