# 双语赋能多智能体：财报异常与可持续披露质量分析系统

证据驱动型多智能体投研分析系统。五个智能体：**综合调度、数据提取、双语对齐、财务分析、ESG 对比**。

## 技术栈

| 层次 | 选型 |
|---|---|
| 交互控制层 | Vue 3 + TypeScript + Vite + Element Plus + Pinia + PDF.js（前端独立仓库） |
| 应用服务层 | FastAPI + Pydantic + ARQ |
| 智能体编排层 | LangGraph |
| 检索与证据层 | BGE-M3 + BM25 + RRF + BGE-reranker-v2-m3 |
| 数据模型层 | MySQL 8.0 + Redis |
| 模型层 | DeepSeek-V4.1（不做微调，领域知识与计算规则经提示词注入） |
| 解析层 | PaddleOCR + Unstructured.io |

## 环境准备

需要 Python 3.11、uv、Docker Desktop。

```bash
# 1. 装依赖（分三批，重的放最后）
uv sync                                    # 骨架依赖
uv add langgraph langchain-core openai rank-bm25   # 智能体与检索
uv add openai                              # 已含在上一步

# 解析相关（约 1.5 GB，确认磁盘后再装）
uv add paddlepaddle paddleocr unstructured

# 向量与重排模型（约 2.5 GB，会拉入 torch）
uv add FlagEmbedding
```

```bash
# 2. 起 MySQL（8.0；Redis 用已有容器）
# 宿主端口是 3308：3306 被本机原生 MySQL 5.7 占用，3307 被另一个项目预留
docker compose up -d

# 3. 配环境变量
cp .env.example .env
# 填入 DEEPSEEK_API_KEY
```

## 初始化数据库

```bash
uv run alembic upgrade head                  # 建表
uv run python -m app.seed.field_registry     # 灌 46 个字段到 field_registry
```

## 启动

```bash
uv run uvicorn app.main:app --reload
```

- 接口文档 http://127.0.0.1:8000/docs
- 健康检查 http://127.0.0.1:8000/health

## 目录结构

```
app/
├── main.py              FastAPI 入口
├── core/                配置、数据库、Redis
├── api/v1/              路由：任务 / 文档 / 证据 / SSE
├── models/              SQLAlchemy ORM
├── schemas/             Pydantic 出入参
├── agents/              五个智能体与编排图
│   └── state.py         编排图共享状态
├── retrieval/           解析 · 分块 · 向量 · 混合检索
├── prompts/             提示词模板（按版本存放）
└── tools/               规则引擎 · MCP 通道
```

## 设计文档

在 `D:\OneDrive\图片\Desktop\分析公司项目`：

- `双语赋能多智能体_技术架构设计文档.docx`（完整版 / 精简版）
- `数据字段编码注册表.docx` —— 字段编码与下游用途，建库建 Schema 的依据
- `各个智能体/` —— 五份智能体计划书
