from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / '.env', env_prefix='LEGALLENS_', extra='ignore'
    )
    database_url: str = 'sqlite:///./data/legallens.db'
    storage_dir: Path = Path('data/files')
    allowed_origins: str = 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000'
    secure_cookies: bool = False
    session_hours: int = 12
    max_upload_mb: int = 20
    max_workspace_documents: int = 50
    max_pages: int = 200
    expensive_requests_per_minute: int = 20
    auto_migrate: bool = True
    testing: bool = False
    model_base_url: str = ''
    model_api_key: str = ''
    model_name: str = ''
    embedding_base_url: str = ''
    embedding_api_key: str = ''
    embedding_model: str = ''
