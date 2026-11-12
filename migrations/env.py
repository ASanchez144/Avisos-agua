from alembic import context
import sqlalchemy as sa

from backend.models import metadata

config = context.config


def run() -> None:
    if context.is_offline_mode():  # `alembic upgrade head --sql`: solo genera el SQL
        context.configure(url="postgresql://", target_metadata=metadata, literal_binds=True, dialect_name="postgresql")
        with context.begin_transaction():
            context.run_migrations()
        return
    connectable = config.attributes.get("connection")
    if connectable is None:
        connectable = sa.create_engine(config.get_main_option("sqlalchemy.url"))
    if isinstance(connectable, sa.Engine):
        with connectable.begin() as conn:
            context.configure(connection=conn, target_metadata=metadata)
            with context.begin_transaction():
                context.run_migrations()
    else:
        context.configure(connection=connectable, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()


run()
