"""Database connections."""

from almasix.config import env

config = {
    "default": env("DB_CONNECTION", "sqlite"),
    "connections": {
        "sqlite": {
            "driver": "sqlite",
            "database": env("DB_DATABASE", "database/database.sqlite"),
        },
        "pgsql": {
            "driver": "pgsql",
            "host": env("DB_HOST", "127.0.0.1"),
            "port": env("DB_PORT", 5432),
            "database": env("DB_DATABASE", "almasix"),
            "username": env("DB_USERNAME", "almasix"),
            "password": env("DB_PASSWORD", ""),
        },
        "mysql": {
            "driver": "mysql",
            "host": env("DB_HOST", "127.0.0.1"),
            "port": env("DB_PORT", 3306),
            "database": env("DB_DATABASE", "almasix"),
            "username": env("DB_USERNAME", "almasix"),
            "password": env("DB_PASSWORD", ""),
        },
        "mariadb": {
            "driver": "mariadb",
            "host": env("DB_HOST", "127.0.0.1"),
            "port": env("DB_PORT", 3306),
            "database": env("DB_DATABASE", "almasix"),
            "username": env("DB_USERNAME", "almasix"),
            "password": env("DB_PASSWORD", ""),
        },
        "sqlsrv": {
            "driver": "sqlsrv",
            "host": env("DB_HOST", "127.0.0.1"),
            "port": env("DB_PORT", 1433),
            "database": env("DB_DATABASE", "almasix"),
            "username": env("DB_USERNAME", "sa"),
            "password": env("DB_PASSWORD", ""),
            "odbc_driver": env("DB_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
            "trust_server_certificate": env("DB_TRUST_SERVER_CERTIFICATE", "yes"),
        },
        "oracle": {
            "driver": "oracle",
            "host": env("DB_HOST", "127.0.0.1"),
            "port": env("DB_PORT", 1521),
            "service_name": env("DB_SERVICE_NAME", env("DB_DATABASE", "ORCL")),
            "username": env("DB_USERNAME", "almasix"),
            "password": env("DB_PASSWORD", ""),
        },
    },
}
