"""Multi-driver URL + DDL parity (Laravel DB set + optional Oracle)."""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite

from almasix.orm.connection import ConnectionError_, _ensure_async_driver, _normalize_url
from almasix.orm.dialects import drop_table_sql, quote_ident, rename_column_sql
from almasix.orm.schema import Blueprint, compile_table_statements


def test_normalize_url_laravel_drivers() -> None:
    assert _normalize_url({"driver": "sqlite", "database": ":memory:"}).startswith(
        "sqlite+aiosqlite"
    )
    assert "asyncpg" in _normalize_url(
        {
            "driver": "pgsql",
            "username": "u",
            "password": "p",
            "host": "h",
            "port": 5432,
            "database": "db",
        }
    )
    assert "aiomysql" in _normalize_url(
        {"driver": "mysql", "username": "u", "host": "h", "database": "db"}
    )
    assert "aiomysql" in _normalize_url(
        {"driver": "mariadb", "username": "u", "host": "h", "database": "db"}
    )
    sqlsrv = _normalize_url(
        {
            "driver": "sqlsrv",
            "username": "sa",
            "password": "secret",
            "host": "db",
            "port": 1433,
            "database": "almasix",
        }
    )
    assert sqlsrv.startswith("mssql+aioodbc://")
    assert "ODBC+Driver+18+for+SQL+Server" in sqlsrv or "ODBC Driver 18" in sqlsrv

    ora = _normalize_url(
        {
            "driver": "oracle",
            "username": "system",
            "password": "oracle",
            "host": "db",
            "port": 1521,
            "service_name": "FREEPDB1",
        }
    )
    assert ora.startswith("oracle+oracledb_async://")
    assert "service_name=FREEPDB1" in ora

    with pytest.raises(ConnectionError_):
        _normalize_url({"driver": "db2"})


def test_ensure_async_driver_prefixes() -> None:
    assert _ensure_async_driver("sqlite:///tmp.db").startswith("sqlite+aiosqlite")
    assert "asyncpg" in _ensure_async_driver("postgresql://u:p@h/db")
    assert "aiomysql" in _ensure_async_driver("mysql://u:p@h/db")
    assert "aiomysql" in _ensure_async_driver("mariadb://u:p@h/db")
    assert _ensure_async_driver("mssql+pyodbc://u:p@h/db").startswith("mssql+aioodbc")
    assert _ensure_async_driver("mssql://u:p@h/db").startswith("mssql+aioodbc")
    assert _ensure_async_driver("sqlsrv://u:p@h/db").startswith("mssql+aioodbc")
    assert _ensure_async_driver("oracle://u:p@h/?service_name=X").startswith(
        "oracle+oracledb_async"
    )
    assert _ensure_async_driver("oracle+oracledb://u:p@h/").startswith("oracle+oracledb_async")


@pytest.mark.parametrize(
    "dialect_factory",
    [sqlite.dialect, postgresql.dialect, mysql.dialect, mssql.dialect, oracle.dialect],
)
def test_quote_and_drop_rename_per_dialect(dialect_factory) -> None:
    dialect = dialect_factory()
    quoted = quote_ident(dialect, "posts")
    assert "posts" in quoted
    drop = drop_table_sql("posts", dialect, if_exists=True)
    rename = rename_column_sql("posts", "title", "headline", dialect)
    if dialect.name == "mssql":
        assert "sp_rename" in rename
        assert "DROP TABLE IF EXISTS" in drop
    elif dialect.name == "oracle":
        assert "RENAME COLUMN" in rename
        assert "SQLCODE != -942" in drop
    else:
        assert "RENAME COLUMN" in rename
        assert "DROP TABLE IF EXISTS" in drop


def test_compile_alter_ddl_across_dialects() -> None:
    bp = Blueprint("posts")
    bp.string("slug").nullable().after("title")
    bp.foreign("user_id").references("id").on("users").cascade_on_delete()

    mysql_sql = compile_table_statements(bp, mysql.dialect())
    assert any("AFTER" in statement for statement in mysql_sql)
    assert any("FOREIGN KEY" in statement for statement in mysql_sql)

    pg_sql = compile_table_statements(bp, postgresql.dialect())
    assert any("FOREIGN KEY" in statement for statement in pg_sql)
    assert all("AFTER" not in statement for statement in pg_sql)

    mssql_sql = compile_table_statements(bp, mssql.dialect())
    assert any("FOREIGN KEY" in statement for statement in mssql_sql)
    assert any("[" in statement for statement in mssql_sql)

    oracle_sql = compile_table_statements(bp, oracle.dialect())
    assert any("FOREIGN KEY" in statement for statement in oracle_sql)
