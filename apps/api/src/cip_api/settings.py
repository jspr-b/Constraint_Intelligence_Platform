"""Service settings from environment variables (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
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
    source_id: str = "unknown"
    """Source the image was built from (scripts/source_id.sh); ``unknown`` outside images."""
    session_hours: int = 12
    """A personal or station session lasts one long shift; then sign in again."""
    pin_max_attempts: int = 5
    auth_provider: str = "dev"
    """``dev`` (dev login, pilot only) or ``oidc`` (e.g. Microsoft Entra ID, see docs/auth.md)."""
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    data_dir: Path = Path(__file__).resolve().parents[4] / "var" / "data"
    """Uploaded exports and their standard layout, per tenant and plant (gitignored)."""
    max_upload_mb: int = 100
    run_jobs_inline: bool = False
    refresh_timeout_min: int = 10
    """A recalculation still running after this long counts as failed: the page offers a retry."""
    data_old_after_days: int = 7
    """From this age (days since the newest touchpoint) pages ask for new events."""
    anthropic_api_key: SecretStr | None = None
    """The mapping wizard's AI (ADR-0011 §4). Unset: rules only and "AI not connected". Only
    from the environment or the host's secret store, never in code, git or logs."""
    ai_model: str = "claude-sonnet-5-5"
    ai_max_eur_per_import: float = 0.5
    ai_max_eur_per_month: float = 20.0
    """Above a limit the wizard falls back to rules and says so."""
    ai_eur_per_mtok_in: float = 3.0
    ai_eur_per_mtok_out: float = 15.0
    """Price per million tokens used to count the cost; set to the contract's prices."""
    ai_timeout_s: float = 20.0
    ai_retries: int = 2
    """Run jobs in the request instead of a worker (tests only)."""

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
