from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GEO_", env_file=".env")

    database_url: str = "sqlite:///./geo.db"
    max_upload_bytes: int = 50 * 1024 * 1024        # 50 MB upload cap
    max_uncompressed_bytes: int = 300 * 1024 * 1024  # zip-bomb guard
    max_features: int = 100_000                      # processing guard


settings = Settings()
