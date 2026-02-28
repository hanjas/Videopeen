from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "videopeen"
    upload_dir: str = "./uploads"
    output_dir: str = "./outputs"
    anthropic_api_key: str = ""
    vision_model: str = "claude-sonnet-4-5-20250514"
    text_model: str = "claude-sonnet-4-5-20250514"
    frontend_url: str = "http://localhost:5173"
    default_chunk_size: int = 120
    max_upload_size_mb: int = 2048

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def ensure_dirs(self) -> None:
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
