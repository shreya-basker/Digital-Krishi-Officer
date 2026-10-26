from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/agrisathi"
    jwt_secret: str = "dev-only-secret-change-me-in-the-env-file"
    jwt_expire_minutes: int = 60 * 24 * 7

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # data.gov.in key for live Agmarknet mandi prices; sample prices are used without it
    data_gov_api_key: str = ""

    weather_cache_minutes: int = 60
    frontend_dir: Path = ROOT_DIR / "frontend"


settings = Settings()
