from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "private-doc-intel-demo"
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    embedding_provider: str = "fastembed-local"
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    answer_provider: str = "extractive"
    answer_model_name: str = ""
    local_answer_model_name: str = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
    local_answer_max_tokens: int = 280
    local_answer_temperature: float = 0.2
    answer_api_base_url: str = ""
    answer_api_key: str = ""
    answer_api_timeout_seconds: float = 30.0
    local_model_runtime: str = "mlx-lm"
    vector_backend: str = "sqlite-fts5"
    vector_collection: str = "documents"
    storage_root: str = "data"
    vector_data_root: str = ""
    uploads_dir_name: str = "uploads"
    database_filename: str = "doc_intel.sqlite3"
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 5
    local_model_config_dir: str = "config/model-profiles"
    model_artifact_root: str = "~/Library/Caches/Private-AI-Lab/models"
    embedding_cache_root: str = ""
    answer_model_cache_root: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
