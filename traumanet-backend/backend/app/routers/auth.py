"""Router de autenticación formal JWT: login y perfil actual."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import ActorContext, get_current_actor
from app.core.dependencies import get_auth_service
from app.schemas.auth import LoginRequest, TokenResponse, UserProfileResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Autenticación (JWT)"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Autentica usuario contra PostgreSQL y emite JWT Bearer",
)
def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return service.login(payload)


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Devuelve el perfil autenticado del token JWT vigente",
)
def me(
    actor: ActorContext = Depends(get_current_actor),
    service: AuthService = Depends(get_auth_service),
) -> UserProfileResponse:
    return service.get_me(actor)
