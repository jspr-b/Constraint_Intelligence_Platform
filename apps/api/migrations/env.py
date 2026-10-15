"""Alembic environment: migrations run as the database owner, never as the app role."""

from alembic import context
from sqlalchemy import create_engine

from cip_api.db.models import Base
from cip_api.settings import get_settings

target_metadata = Base.metadata
TIMESCALE_INDEXES = {"operation_events_at_idx"}


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Ignore indexes TimescaleDB creates itself for hypertables."""
    return not (type_ == "index" and reflected and name in TIMESCALE_INDEXES)


def run_migrations_online() -> None:
    engine = create_engine(get_settings().db_url(as_owner=True))
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, include_object=include_object
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
