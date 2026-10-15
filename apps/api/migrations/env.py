"""Alembic environment: migrations run as the database owner, never as the app role."""

from alembic import context
from sqlalchemy import create_engine

from cip_api.db.models import Base
from cip_api.settings import get_settings

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(get_settings().db_url(as_owner=True))
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
