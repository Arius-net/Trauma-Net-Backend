"""Gestión centralizada de clientes/conexiones para los tres paradigmas de persistencia."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pg8000.dbapi as pg
from neo4j import Driver, GraphDatabase
from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import Settings


class DatabaseClients:
    """Mantiene la configuración de PostgreSQL y los clientes singleton de MongoDB y Neo4j."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._mongo_client: MongoClient | None = None
        self._neo4j_driver: Driver | None = None

    def connect(self) -> None:
        if self._mongo_client is None:
            self._mongo_client = MongoClient(
                host=self.settings.mongo_host,
                port=self.settings.mongo_port,
                username=self.settings.mongo_user,
                password=self.settings.mongo_password,
                authSource="admin",
                tz_aware=True,
                serverSelectionTimeoutMS=5000,
            )
        if self._neo4j_driver is None:
            self._neo4j_driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user, self.settings.neo4j_password),
            )

    def close(self) -> None:
        if self._mongo_client is not None:
            self._mongo_client.close()
            self._mongo_client = None
        if self._neo4j_driver is not None:
            self._neo4j_driver.close()
            self._neo4j_driver = None

    @contextmanager
    def pg_connection(self) -> Iterator[pg.Connection]:
        """Abre una conexión dedicada a PostgreSQL (segura para concurrencia entre hilos)."""
        conn = pg.connect(
            host=self.settings.postgres_host,
            port=self.settings.postgres_port,
            database=self.settings.postgres_db,
            user=self.settings.postgres_user,
            password=self.settings.postgres_password,
            timeout=10,
        )
        try:
            yield conn
        finally:
            conn.close()

    @property
    def mongo_db(self) -> Database:
        if self._mongo_client is None:
            self.connect()
        assert self._mongo_client is not None
        return self._mongo_client[self.settings.mongo_db]

    @property
    def neo4j_driver(self) -> Driver:
        if self._neo4j_driver is None:
            self.connect()
        assert self._neo4j_driver is not None
        return self._neo4j_driver
