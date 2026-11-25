"""Configuración centralizada leída exclusivamente desde variables de entorno / .env."""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
logger = logging.getLogger("traumanet.config")
_EPHEMERAL_JWT_KEY: str | None = None


def _load_dotenv() -> None:
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _require_env(name: str, default: str | None = None) -> str:
    _load_dotenv()
    val = os.environ.get(name, default)
    if val is None or val == "":
        raise RuntimeError(f"Falta la variable de entorno requerida: {name} (ver .env.example)")
    return val


def _resolve_jwt_secret() -> str:
    global _EPHEMERAL_JWT_KEY
    _load_dotenv()
    val = os.environ.get("JWT_SECRET_KEY", "").strip()
    if val:
        return val
    if _EPHEMERAL_JWT_KEY is None:
        _EPHEMERAL_JWT_KEY = secrets.token_urlsafe(32)
        logger.warning(
            "JWT_SECRET_KEY no está definido en .env; usando clave efímera en memoria para esta sesión. "
            "Agregue JWT_SECRET_KEY en .env para persistir tokens entre reinicios."
        )
    return _EPHEMERAL_JWT_KEY


@dataclass(frozen=True)
class Settings:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str

    mongo_host: str
    mongo_port: int
    mongo_user: str
    mongo_password: str
    mongo_db: str

    neo4j_host: str
    neo4j_bolt_port: int
    neo4j_user: str
    neo4j_password: str

    reserva_ttl_min: int
    demora_penalty_factor: float

    jwt_secret_key: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    frontend_url: str

    @property
    def neo4j_uri(self) -> str:
        return f"bolt://{self.neo4j_host}:{self.neo4j_bolt_port}"

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.frontend_url.split(",") if o.strip()]
        if "http://localhost:3000" in origins and "http://127.0.0.1:3000" not in origins:
            origins.append("http://127.0.0.1:3000")
        return origins or ["http://localhost:3000", "http://127.0.0.1:3000"]


def load_settings() -> Settings:
    return Settings(
        postgres_host=_require_env("POSTGRES_HOST", "127.0.0.1"),
        postgres_port=int(_require_env("POSTGRES_PORT", "5432")),
        postgres_db=_require_env("POSTGRES_DB"),
        postgres_user=_require_env("POSTGRES_USER"),
        postgres_password=_require_env("POSTGRES_PASSWORD"),
        mongo_host=_require_env("MONGO_HOST", "127.0.0.1"),
        mongo_port=int(_require_env("MONGO_PORT", "27017")),
        mongo_user=_require_env("MONGO_USER"),
        mongo_password=_require_env("MONGO_PASSWORD"),
        mongo_db=_require_env("MONGO_DB", "traumanet"),
        neo4j_host=_require_env("NEO4J_HOST", "127.0.0.1"),
        neo4j_bolt_port=int(_require_env("NEO4J_BOLT_PORT", "7687")),
        neo4j_user=_require_env("NEO4J_USER", "neo4j"),
        neo4j_password=_require_env("NEO4J_PASSWORD"),
        reserva_ttl_min=int(_require_env("RESERVA_TTL_MIN", "15")),
        demora_penalty_factor=float(os.environ.get("DEMORA_PENALTY_FACTOR", "1.35")),
        jwt_secret_key=_resolve_jwt_secret(),
        jwt_algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        jwt_expire_minutes=int(os.environ.get("JWT_EXPIRE_MINUTES", "120")),
        frontend_url=os.environ.get("FRONTEND_URL", "http://localhost:3000"),
    )
