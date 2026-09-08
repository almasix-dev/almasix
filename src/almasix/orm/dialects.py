"""Dialect helpers — Laravel-shaped drivers over SQLAlchemy async dialects."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus, urlencode


def quote_ident(dialect: Any, name: str) -> str:
    """Quote an identifier for the active dialect."""
    return dialect.identifier_preparer.quote_identifier(name)


def drop_table_sql(table: str, dialect: Any, *, if_exists: bool = False) -> str:
    """Compile ``DROP TABLE`` / ``DROP TABLE IF EXISTS`` for the dialect."""
    qt = quote_ident(dialect, table)
    name = dialect.name
    if name == "oracle":
        if if_exists:
            safe = table.replace("'", "''")
            return (
                "BEGIN EXECUTE IMMEDIATE 'DROP TABLE "
                f'"{safe}"'
                "'; EXCEPTION WHEN OTHERS THEN "
                "IF SQLCODE != -942 THEN RAISE; END IF; END;"
            )
        return f"DROP TABLE {qt}"
    if if_exists:
        return f"DROP TABLE IF EXISTS {qt}"
    return f"DROP TABLE {qt}"


def rename_column_sql(table: str, old: str, new: str, dialect: Any) -> str:
    """Compile a column rename for the dialect."""
    name = dialect.name
    qt = quote_ident(dialect, table)
    if name == "mssql":
        return f"EXEC sp_rename '{table}.{old}', '{new}', 'COLUMN'"
    return (
        f"ALTER TABLE {qt} RENAME COLUMN {quote_ident(dialect, old)} "
        f"TO {quote_ident(dialect, new)}"
    )


def build_async_url(config: dict[str, Any]) -> str:
    """Build an async SQLAlchemy URL from a Laravel-shaped connection dict."""
    if config.get("url"):
        return ensure_async_driver(str(config["url"]))

    driver = str(config.get("driver", "sqlite")).lower()
    if driver == "sqlite":
        database = str(config.get("database", ":memory:"))
        return f"sqlite+aiosqlite:///{database}"

    user = str(config.get("username", "") or "")
    password = str(config.get("password", "") or "")
    host = str(config.get("host", "127.0.0.1") or "127.0.0.1")
    port = config.get("port")
    database = str(config.get("database", "") or "")
    auth = f"{quote_plus(user)}:{quote_plus(password)}@" if user else ""
    hostname = f"{host}:{port}" if port else host

    if driver in {"pgsql", "postgres", "postgresql"}:
        return f"postgresql+asyncpg://{auth}{hostname}/{database}"

    if driver in {"mysql", "mariadb"}:
        return f"mysql+aiomysql://{auth}{hostname}/{database}"

    if driver in {"sqlsrv", "mssql", "sqlserver"}:
        odbc = str(
            config.get("odbc_driver")
            or config.get("odbc_driver_name")
            or "ODBC Driver 18 for SQL Server"
        )
        query = urlencode(
            {
                "driver": odbc,
                "TrustServerCertificate": str(
                    config.get("trust_server_certificate", "yes")
                ),
            }
        )
        return f"mssql+aioodbc://{auth}{hostname}/{database}?{query}"

    if driver == "oracle":
        service = str(
            config.get("service_name") or config.get("sid") or database or "ORCL"
        )
        query = urlencode({"service_name": service})
        return f"oracle+oracledb_async://{auth}{hostname}/?{query}"

    raise ValueError(f"Unsupported database driver: {driver!r}")


def ensure_async_driver(url: str) -> str:
    """Upgrade a sync URL to its async driver so app config stays familiar."""
    # Longer / more-specific prefixes first.
    replacements = (
        ("mssql+pyodbc://", "mssql+aioodbc://"),
        ("oracle+oracledb://", "oracle+oracledb_async://"),
        ("sqlite://", "sqlite+aiosqlite://"),
        ("postgresql://", "postgresql+asyncpg://"),
        ("postgres://", "postgresql+asyncpg://"),
        ("mysql://", "mysql+aiomysql://"),
        ("mariadb://", "mysql+aiomysql://"),
        ("mssql://", "mssql+aioodbc://"),
        ("sqlsrv://", "mssql+aioodbc://"),
        ("oracle://", "oracle+oracledb_async://"),
    )
    for prefix, replacement in replacements:
        if url.startswith(prefix):
            return replacement + url[len(prefix) :]
    return url
