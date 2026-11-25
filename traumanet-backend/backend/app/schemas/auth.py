"""Esquemas Pydantic para autenticación JWT (POST /api/v1/auth/login y GET /api/v1/auth/me)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre_usuario: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)


class UserProfileResponse(BaseModel):
    usuario_id: int
    nombre_usuario: str
    rol: str
    hospital_id: int | None = None
    hospital_nombre: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserProfileResponse
