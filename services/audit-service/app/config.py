from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    database_url: str = "sqlite:///./audit.db"
    port: int = 8008
    host: str = "0.0.0.0"


settings = Settings()
