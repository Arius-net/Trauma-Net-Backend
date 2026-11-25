"""Utilidades compartidas de los scripts de base de datos (sin secretos en el código)."""
import os
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    """Carga <raíz>/.env sin sobrescribir variables ya definidas en el entorno."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def env(name: str, default: str | None = None) -> str:
    load_env()
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Falta la variable de entorno {name} (ver .env.example)")
    return value


@contextmanager
def pg_connect():
    """Conexión DB-API 2.0 a PostgreSQL vía pg8000 (driver Python puro)."""
    import pg8000.dbapi as pg

    conn = pg.connect(
        host=env("POSTGRES_HOST", "127.0.0.1"),
        port=int(env("POSTGRES_PORT", "5432")),
        database=env("POSTGRES_DB"),
        user=env("POSTGRES_USER"),
        password=env("POSTGRES_PASSWORD"),
    )
    try:
        yield conn
    finally:
        conn.close()


def mongo_db():
    from pymongo import MongoClient

    client = MongoClient(
        host=env("MONGO_HOST", "127.0.0.1"),
        port=int(env("MONGO_PORT", "27017")),
        username=env("MONGO_USER"),
        password=env("MONGO_PASSWORD"),
        authSource="admin",
        tz_aware=True,
        serverSelectionTimeoutMS=5000,
    )
    return client, client[env("MONGO_DB")]


def neo4j_driver():
    from neo4j import GraphDatabase

    uri = f"bolt://{env('NEO4J_HOST', '127.0.0.1')}:{env('NEO4J_BOLT_PORT', '7687')}"
    return GraphDatabase.driver(uri, auth=(env("NEO4J_USER", "neo4j"), env("NEO4J_PASSWORD")))
