from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 应用程序 ---
    APP_NAME: str = "AI 校园助手"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    CORS_ALLOW_ORIGINS: str = "http://127.0.0.1:5173,http://localhost:5173"

    # --- MySQL 数据库 ---
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str
    MYSQL_DATABASE: str = "ai_assistant"

    # --- Redis 数据库 ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str
    REDIS_DB: int = 0

    # --- JWT 配置 ---
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 1 天

    # --- AES (密码传输加密) ---
    # UTF-8 密钥字符串 (16/24/32 字符 → AES-128/192/256)
    # 必须与前端 CryptoJS 使用的密钥一致
    AES_SECRET_KEY: str

    # --- 隐私配置 ---
    DID_SALT: str

    # --- 对话上下文 ---
    MAX_HISTORY_COUNT: int = 10

    # --- 阿里云 DashScope ---
    ALI_API_KEY: str
    DASHSCOPE_TRUST_ENV_PROXY: bool = False
    DASHSCOPE_MAX_INPUT_CHARS: int = 28000
    BAILIAN_APP_ID: str

    # --- LLM 模型配置 ---
    # 意图理解
    LLM_MODEL_INTENT_CLASSIFY: str = "qwen-turbo"
    # 查询改写
    LLM_MODEL_QUERY_REWRITE: str = "qwen-turbo"
    # 最终回答生成
    LLM_MODEL_FINAL_ANSWER: str = "qwen-plus"
    # 思考决策 / 工具规划
    LLM_MODEL_TOOL_PLANNER: str = "qwen-plus"
    # 向量检索 query 拆解
    LLM_MODEL_VECTOR_DECOMPOSE: str = "qwen-turbo"
    # hybrid 路径重排
    LLM_MODEL_HYBRID_RERANK: str = "qwen-turbo"
    # 安全检测
    LLM_MODEL_SAFETY_CHECK: str = "qwen-turbo"
    # 图像理解
    LLM_MODEL_IMAGE_UNDERSTANDING: str = "qwen-vl-plus"
    # 语音识别
    LLM_MODEL_SPEECH_RECOGNITION: str = "paraformer-realtime-v1"

    # --- 阿里云百炼检索 API ---
    ALIBABA_CLOUD_ACCESS_KEY_ID: str
    ALIBABA_CLOUD_ACCESS_KEY_SECRET: str
    BAILIAN_WORKSPACE_ID: str
    BAILIAN_INDEX_ID: str
    BAILIAN_ENDPOINT: str = "bailian.cn-beijing.aliyuncs.com"

    # --- 缓存 TTL (秒) ---
    CACHE_TTL_SENSITIVE: int = 1800   # 30 分钟
    CACHE_TTL_NORMAL: int = 86400     # 1 天

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        if self.REDIS_PASSWORD:
            return (
                f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}"
                f":{self.REDIS_PORT}/{self.REDIS_DB}"
            )
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def cors_allow_origins(self) -> list[str]:
        raw = (self.CORS_ALLOW_ORIGINS or "").strip()
        if not raw:
            return []
        if raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]


settings = Settings()
