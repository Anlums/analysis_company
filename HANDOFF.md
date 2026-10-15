# 项目交接说明（HANDOFF）

> 本文件用于把项目上下文交接给新的 AI 会话或新加入的成员。
> 最后更新：2026-10-15

---

## 一、项目一句话

**双语赋能多智能体：财报异常与可持续披露质量分析系统**

参赛「2026 年北京市大学生金融人工智能竞赛 · 金融投研智能体构建」主题。证据驱动型多智能体投研系统，面向**全行业**（不限于林业）。

五个智能体：

| 智能体 | 职责 |
|---|---|
| **综合调度智能体** | 协调中枢，系统唯一与用户交互的主体，不承担专业分析 |
| **数据提取智能体** | 非结构化文档 → 结构化数据，**证据锚点生成端** |
| **双语对齐智能体** | IFRS→CAS、CASS-ESG 6.0→ISSB+GRI 的准则映射 |
| **财务分析智能体** | 会计口径识别 → 十二项指标 → 六大风险主题 → 四级信号灯 |
| **ESG 对比智能体** | CASS-ESG 6.0 七维披露质量评分 + 置信度 + 漂绿三层检测 |

---

## 二、两个目录（务必分清）

| | 路径 | 内容 |
|---|---|---|
| **文档** | `D:\OneDrive\图片\Desktop\分析公司项目` | 设计文档 + 20 家公司年报 PDF（国内 10 家 + 国外 10 家） |
| **代码** | `D:\develop\program\PythonProgram\analysis_company` | 本仓库。故意放在 OneDrive 之外——venv 上万个小文件放 OneDrive 里会同步冲突、拖慢 PyCharm 索引 |

---

## 三、要读的文件

### 必读（4 份）

1. **`双语赋能多智能体_技术架构设计文档.docx`**（文档目录根）——技术总纲，274 段 / 22 张表，涵盖选型、五层架构、编排机制、数据模型、可扩展性、非功能性设计。另有 `_精简版.docx`，一页速览。
2. **`数据字段编码注册表.docx`**（文档目录根）——46 个字段的编码、名称、单位、来源位置、**下游用途**，是建数据库 Schema 的唯一依据。
3. **`各个智能体/综合调度智能体计划书.docx`**——动态编排机制（能力池、任务节点状态机、异常处置、一次任务的完整走查）。
4. **本仓库 `README.md`** + `app/` 下的 6 个 .py 文件。

### 按当前任务加读

| 要做什么 | 加读 |
|---|---|
| 数据提取 | `各个智能体/数据提取智能体计划书.docx` |
| 双语对齐 | `各个智能体/双语对齐智能体计划书.docx` + `双语模块完整设计(1)(3).docx` |
| 财务分析 | `各个智能体/财务分析模块计划书(2).docx` |
| ESG 对比 | `各个智能体/ESG对比智能体计划书.docx` |

### 不要读（已废弃，读了反而误导）

- `废弃箱/` 4 份：竞赛讨论稿、三六七内容、最初版计划书（即原「正式版计划书」）、纠错核查智能体计划书
- `参考文件/` 4 份：ForestSight 时期的第三/六/七章草稿与指导教师评审稿

这些里面全是**旧设计**：审计评分智能体、纠错核查智能体、pgvector、Streamlit、林业定位。

> 唯一仍有参考价值的是指导教师评审稿对「核心能力 / 扩展能力」的两级划分，但那只是范围参考，不是设计依据。

---

## 四、必须遵守的约定

**这八条最容易搞错，写代码前先确认：**

1. **项目名不叫 ForestSight**——那是旧名，已废弃。
2. **五个智能体，没有纠错核查**。它已取消，不要再加回来。
3. **全部计算由大模型承担**，系统里**没有**程序化计算模块。因此：提示词必须写明计算口径与取数规则，且 `LLM_TEMPERATURE=0`，模型响应按提示词哈希缓存。
4. **不做模型微调**。所有领域知识（财会准则、ESG 框架、行业规则）靠提示词注入，提示词按版本管理并在固定测试集上做回归验证。
5. **前端是 Vue 3 + TypeScript + Vite + Element Plus + Pinia + PDF.js**，不是 React，更不是 Streamlit。
6. **面向全行业**。林业（林权抵押、碳汇、生物资产、森林认证）只是当前的行业包与验证数据集，不是项目定位。
7. **数据库 MySQL 8.0**（不是 pgvector / PostgreSQL）。MySQL 8.0 无原生向量类型，向量检索走抽象接口 `VectorStore`，原型期实现为「MySQL BLOB + 内存索引」，规模增长后切 Qdrant。
8. **Redis 用独立的 Docker 容器**，连接串是 `redis://localhost:6379/0`——**不是** `http://localhost:6379/`，Redis 不认 http 协议。

---

## 五、当前进度

### 文档：已完成

技术架构（完整版 + 精简版）、五份智能体计划书、字段编码注册表，全部口径一致，图表编号连贯。

### 代码：骨架 + 数据模型层

- **包管理**：uv（不是 pip），Python **3.11.15**，PyPI 走阿里云镜像
- **已装 66 个包**，分两批：
  - 骨架：fastapi / uvicorn / sqlalchemy 2.1.4 / pymysql / alembic / redis 5.3.1 / arq / pydantic-settings / sse-starlette / httpx / python-multipart / cryptography
  - 智能体与检索：langgraph 1.2.15 / langchain-core 1.6.10 / openai 3.31.0 / rank-bm25 / numpy
- **未装（体积大，按需再装）**：`paddlepaddle + paddleocr + unstructured`（约 1.5 GB）、`FlagEmbedding`（约 2.5 GB，会拉 torch）
- **未装 pytest**（写测试前需 `uv add --dev pytest`）

**骨架文件**：
  - `app/core/config.py` —— pydantic-settings 配置
  - `app/core/database.py` —— SQLAlchemy 引擎与会话
  - `app/core/redis.py` —— Redis 客户端
  - `app/agents/state.py` —— 编排图共享状态（含 `merge_dict` 并行合并策略）
  - `app/main.py` —— FastAPI 入口（含 CORS，已指向 Vite 的 5173）
  - `app/api/v1/router.py` —— 路由占位（**仍为空壳，业务路由一个没有**）
  - `app/schemas/common.py` —— 统一响应外壳

**数据模型层（2026-10-15 建成，33 张表 + Pydantic Schema）**：

两个 Alembic 迁移，覆盖技术架构文档 9.1 表 18 的全部八个域：

| 域 | 表 | 迁移 |
|---|---|---|
| 公司域 | `company`、`company_alias` | `1c7bdc0caa95` |
| 文档域 | `document`、`document_block`、`chunk`、`chunk_block` | `1c7bdc0caa95` |
| 证据域 | `evidence`、`conclusion_evidence` | `1c7bdc0caa95` |
| 字段表 | `field_registry`、`field_value` | `1c7bdc0caa95` |
| 可复现性 | `prompt_version`、`llm_call_cache` | `1c7bdc0caa95` |
| 任务域 | `task`、`task_node`、`task_output`、`version_snapshot` | `dbab0deefa3f` |
| 能力与编排 | `capability`、`orchestration_checkpoint`、`checkpoint_write` | `dbab0deefa3f` |
| 准则映射域 | `standard_mapping`、`mapping_record`、`annotation_library` | `dbab0deefa3f` |
| 配置域 | `industry`、`indicator_applicability`、`term_dictionary`、`rule_set`、`threshold`、`weight_scheme` | `dbab0deefa3f` |
| 标注评估域 | `annotation`、`error_case`、`eval_sample`、`eval_metric` | `dbab0deefa3f` |
| 审计域 | `audit_log`（+ 已有 `llm_call_cache`） | `dbab0deefa3f` |

- 模型按域分文件放在 `app/models/`；`__init__.py` 统一导出（Alembic autogenerate 依赖这个导入副作用，漏导入会被当成删表）
- **3 张表不在 9.1 表 18 的清单里**，但其他章节明确要求其存在：`capability`（7.6 与 10.3 规定了登记字段，调度靠它做就绪判定）、`orchestration_checkpoint` / `checkpoint_write`（9.4 明确要求在 MySQL 中建）
- **53 个字段已灌入 `field_registry`**：`uv run python -m app.seed.field_registry`（upsert 幂等，变更字段只改 `app/seed/field_registry.py` 重跑，不需要迁移）
  - 46 个来自《数据字段编码注册表》：BS 11 / IS 8 / CF 3 / ENV 8 / SOC 4 / GOV 4 / FOR 8
  - 7 个为 2026-10-15 补齐：`BS_AR_FIN`、`IS_INTEREST_INCOME`（指标②⑨ 取数口径），以及 `META_*` 5 个（会计口径识别）
  - **`META_` 是新增的类别前缀**，原编码规则只列了七个报表/ESG 类别，需回填进注册表文档
- **季度数据不新增编码**：用 `field_value.period` 承载 Q1–Q4
- **Pydantic Schema** 在 `app/schemas/`：`evidence.py`（含锚点解析与校验）、`company.py`、`document.py`、`field.py`、`task.py`、`common.py`。只覆盖 API 实际暴露的实体，配置域/准则映射域/标注评估域等开工时再补
- **外键 11 条全在域内**，遵循 9.1「不跨域做物理外键约束」。`field_value.field_code → field_registry.field_code` 这条保证未登记的编码写不进去
- `Base.metadata` 已配约束命名约定（`app/core/database.py`），否则 Alembic 会渲染出 `drop_constraint(None, ...)` 导致迁移失败
- **迁移的 downgrade 需手工维护**：Alembic 生成的是「先 drop_index 再 drop_table」，而 MySQL 拒绝删除被外键占用的索引，直接跑会失败。两个迁移的 downgrade 都已改成只 drop_table（子表在前），往返已实测通过
- 端到端验证已过：锚点链路可回指原文、任务—节点—产出链路、检查点、阈值、七维权重（合计 1.0）、审计日志均可写入

**配置层**：`.env` 的键名全部带 `APP_` 前缀（`APP_DATABASE_URL`、`APP_DEEPSEEK_API_KEY` 等）。原因是本机存在全局 `DEEPSEEK_API_KEY`，而 pydantic-settings 的优先级是「真实环境变量 > .env 文件」，没前缀时 `.env` 里的值会被系统变量静默覆盖。加前缀后与机器上其他项目彻底隔离。

**未建**：任务域、准则映射域、配置域其余表、标注与评估域、审计日志表。这些域当前无数据来源，等对应智能体开工时再建。

### 环境约束（踩过的坑，别重复踩）

1. **MySQL 宿主端口是 3308，不是 3306**。本机 3306 被原生 MySQL 5.7 服务（Windows 服务 `MySQL57`，开机自启）占用，3307 被另一个项目的 `mysql8` 容器预留。改端口要同步改三处：`docker-compose.yml`、`.env`/`.env.example`、`app/core/config.py`。
2. **`alembic.ini` 必须保持纯 ASCII**。Alembic 用 `encoding="locale"` 读它，本机 locale 是 GBK，写中文进去直接 `UnicodeDecodeError`。`alembic revision -m` 的备注也别用中文，会生成乱码文件名（迁移 `.py` 文件内部写中文没问题）。
3. 本项目的 MySQL 容器叫 `bilingual-agents-mysql`，库名 `bilingual_agents`。
4. **代码目录还没 git 仓库**（只有 `.gitignore`）。6 周协作 + 提示词版本管理，建议尽早 `git init`。
5. 仓库里的 `src/word/` 是空目录，应为 PyCharm 误建。

### 冒烟测试

`/health` 返回 `{"status":"ok"}`，`/docs` 返回 200，`uv run alembic upgrade head` 通过，`field_registry` 46 行。

### 版本提醒

langgraph 装的是 **1.2.15**，比撰写设计文档时新。已实测 `StateGraph` / `Send` / `Command` / `interrupt` / `BaseCheckpointSaver` 全部可用，文档里的中断恢复、并行扇出、自定义 MySQL 检查点都能落地；但**写代码时以实际 API 为准**。

---

## 六、下一步建议

Schema 已完成，**下一步是数据提取智能体的解析流水线**（PDF → 块序列 → 证据锚点）。这条链路打通了，整个系统的「结论可回指原文」才立得住。分三步：

1. **先做块序列生成**（不调模型）：PDF 逐页版面分析 → 块序列 → 按 `文档标识:页号:块序号` 确定性生成 `block_id` → 落 `document_block`。块标识必须与解析器版本无关、可重复。
2. **再做入库脚本**：把 20 家公司的年报 PDF 批量注册进 `company` / `document` / `document_block`，`doc_code` 用可读的稳定编码（如 `CN_000663_2024_ANNUAL`），便于人工排查证据锚点。
3. **最后接抽取**：按调度下发的字段清单抽取 46 个字段，绑定证据锚点写入 `field_value`。这一步才需要 `DEEPSEEK_API_KEY`。

前置：`uv add paddlepaddle paddleocr unstructured`（约 1.5 GB，确认磁盘）。

**另外三件应当尽早做的小事**：
- `git init` —— 目前完全没有版本控制
- `uv add --dev pytest` —— 用户规范要求 80% 覆盖率与 TDD，但测试框架还没装
- 把 `field_registry` / `field_value` 补登记进技术架构文档 §9 的表清单（见第七节第 5 条）

---

## 七、已知未决项

1. 注册表里环境/社会/治理那 16 个字段只是**常用指标子集**，需与 CASS-ESG 6.0 附录的完整指标清单逐条对齐后补充。补充时只改 `app/seed/field_registry.py` 重跑种子，不动表结构。
2. 向量存储实现待选：原型期「MySQL BLOB + 内存索引」，还是直接上 Qdrant。
3. MCP 通道仍为预留，Wind / iFinD 未接入。
4. 音频输入（FunASR）已写入设计文档，但标注为**扩展能力**，核心闭环跑通后再接入。
5. **技术架构文档 §9 的表清单缺 `field_registry` / `field_value`**。§9.1 表 18 列的 8 个域 28 张表里没有承载那 46 个字段值的表，而 §8.5 又要求「指标数值、跨企业对比、期间筛选」走关系库精确查询——原设计漏了这一环。代码已按长表方案建好并落库，但**文档尚未回填**，需补登记以保持"文档是建库唯一依据"这一约定。

---

## 八、快速开始

```bash
# 装依赖（重型的两批按需再装）
uv sync

# 起 MySQL（Redis 用已有容器；宿主端口 3308，原因见第五节「环境约束」）
docker compose up -d

# 配环境变量，填 DEEPSEEK_API_KEY
cp .env.example .env

# 建表 + 灌字段注册表（MySQL 首次启动需等健康检查通过，约 20 秒）
uv run alembic upgrade head
uv run python -m app.seed.field_registry

# 启动
uv run uvicorn app.main:app --reload
```

- 接口文档 http://127.0.0.1:8000/docs
- 健康检查 http://127.0.0.1:8000/health
