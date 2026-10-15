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
    redis_host: str = "localhost"
    redis_port: int = 56379
    version: str = "0.0.0"
    session_hours: int = 12
    """A personal or station session lasts one long shift; then sign in again."""
    pin_max_attempts: int = 5
    auth_provider: str = "dev"
    """``dev`` (dev login, pilot only) or ``oidc`` (e.g. Microsoft Entra ID, see docs/auth.md)."""
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None

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
