"""Servicio de autenticación JWT respaldado por `usuarios` en PostgreSQL (D-0005 / Q-05)."""
from __future__ import annotations

from fastapi import HTTPException, status

from app.core.auth import ActorContext, create_access_token, verify_password
from app.core.config import Settings
from app.repositories.relational.relational_repo import RelationalRepository
from app.schemas.auth import LoginRequest, TokenResponse, UserProfileResponse


class AuthService:
    def __init__(self, settings: Settings, relational_repo: RelationalRepository) -> None:
        self._settings = settings
        self._relational = relational_repo

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self._relational.get_user_by_username(payload.nombre_usuario.strip())
        if user is None or not user["activo"] or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas o usuario inactivo.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        actor = ActorContext(
            usuario_id=user["usuario_id"],
            nombre_usuario=user["nombre_usuario"],
            role=user["rol"],
            hospital_id=user["hospital_id"],
        )
        token, expires_at = create_access_token(actor, self._settings)
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_at=expires_at,
            user=UserProfileResponse(
                usuario_id=user["usuario_id"],
                nombre_usuario=user["nombre_usuario"],
                rol=user["rol"],
                hospital_id=user["hospital_id"],
                hospital_nombre=user["hospital_nombre"],
            ),
        )

    def get_me(self, actor: ActorContext) -> UserProfileResponse:
        user = self._relational.get_user_by_id(actor.usuario_id)
        if user is None or not user["activo"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado o inactivo.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return UserProfileResponse(
            usuario_id=user["usuario_id"],
            nombre_usuario=user["nombre_usuario"],
            rol=user["rol"],
            hospital_id=user["hospital_id"],
            hospital_nombre=user["hospital_nombre"],
        )
