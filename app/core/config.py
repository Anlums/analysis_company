from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """项目配置。

    env_prefix="APP_" 是刻意加的：DATABASE_URL、DEEPSEEK_API_KEY 这类名字太通用，
    本机就存在一个全局的 DEEPSEEK_API_KEY，而 pydantic-settings 的优先级是
    「真实环境变量 > .env 文件」，没前缀时 .env 里的值会被系统变量静默覆盖。
    加前缀后本项目的配置只认 APP_* ，与机器上其他项目彻底隔离。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )

    app_name: str = "双语赋能多智能体：财报异常与可持续披露质量分析系统"
    debug: bool = False

    # 数据模型层
    database_url: str = (
        "mysql+pymysql://root:dev123456@localhost:3308/bilingual_agents?charset=utf8mb4"
    )
    redis_url: str = "redis://localhost:6379/0"

    # 模型层：模型既做语义理解，也承担全部指标计算，温度必须为 0
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-pro"
    llm_temperature: float = 0.0

    # 检索与证据层
    embedding_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    vector_backend: str = "mysql"  # mysql | qdrant

    # 可复现性：任务创建时固化，写入 version_snapshot
    schema_version: str = "v0.1"
    prompt_version: str = "v0.1"

    # 文档上传
    upload_dir: str = "data/uploads"
    max_upload_mb: int = 200

    # 前端开发服务器（Vite）
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
