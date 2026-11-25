"""Autenticación y autorización formal mediante JWT firmado y PBKDF2-SHA256 (D-0005 / Q-05).

Retira el mecanismo temporal X-User-Role (A-09): todo endpoint protegido exige
`Authorization: Bearer <token>` respaldado contra `usuarios` de PostgreSQL.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings

UserRole = Literal["CRUM", "PARAMEDICO", "JEFE_URGENCIAS"]
VALID_ROLES: set[str] = {"CRUM", "PARAMEDICO", "JEFE_URGENCIAS"}
PBKDF2_ITERATIONS = 260_000

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ActorContext:
    usuario_id: int
    nombre_usuario: str
    role: UserRole
    hospital_id: int | None = None


def hash_password(password: str, salt_hex: str | None = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    try:
        scheme, iter_str, salt_hex, expected_hex = stored_hash.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            iterations,
        ).hex()
        return hmac.compare_digest(computed, expected_hex)
    except Exception:
        return False


def create_access_token(actor: ActorContext, settings: Settings) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(actor.usuario_id),
        "username": actor.nombre_usuario,
        "role": actor.role,
        "hospital_id": actor.hospital_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str, settings: Settings) -> ActorContext:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT expirado. Inicie sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    role = str(payload.get("role", "")).upper()
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT con rol inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        usuario_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT sin identificador de usuario válido.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    hospital_id = payload.get("hospital_id")
    return ActorContext(
        usuario_id=usuario_id,
        nombre_usuario=str(payload.get("username", "")),
        role=role,  # type: ignore[arg-type]
        hospital_id=int(hospital_id) if hospital_id is not None else None,
    )


def get_current_actor(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> ActorContext:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación mediante Authorization: Bearer <token>.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings: Settings = request.app.state.container.settings
    return decode_access_token(credentials.credentials, settings)


def require_roles(*allowed: UserRole):
    def _checker(actor: ActorContext = Depends(get_current_actor)) -> ActorContext:
        if actor.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"El rol '{actor.role}' no tiene permiso para esta operación "
                    f"(permitidos: {', '.join(allowed)})."
                ),
            )
        return actor

    return _checker
