from alembic import context
from sqlalchemy import create_engine
from app.config import Settings
from app.database import Base

config = context.config
connection = config.attributes.get('connection')


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=Settings().database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif connection is not None:
    run(connection)
else:
    engine = create_engine(Settings().database_url)
    with engine.connect() as connection:
        run(connection)
