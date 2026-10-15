"""Service settings from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CIP_", env_file=".env", extra="ignore")

    env: str = "dev"
    db_host: str = "localhost"
    db_port: int = 55432
    db_name: str = "cip"
    db_owner: str = "cip_owner"
    db_owner_password: str = "cip_owner_dev"
    db_app_user: str = "cip_app"
    db_app_password: str = "cip_app_dev"
    redis_port: int = 56379

    def db_url(self, as_owner: bool = False) -> str:
        user, password = (
            (self.db_owner, self.db_owner_password)
            if as_owner
            else (self.db_app_user, self.db_app_password)
        )
        return (
            f"postgresql+psycopg://{user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
