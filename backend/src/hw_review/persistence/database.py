"""Engine construction for the local SQLite persistence adapter."""

from sqlalchemy import Engine, create_engine, event


def enable_sqlite_foreign_keys(engine: Engine) -> Engine:
    """Attach the mandatory SQLite foreign-key pragma before first use."""

    if engine.dialect.name != "sqlite":
        return engine

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
    return engine


def create_database_engine(database_url: str) -> Engine:
    """Create an engine without creating or migrating any application table."""

    return enable_sqlite_foreign_keys(create_engine(database_url, future=True))
