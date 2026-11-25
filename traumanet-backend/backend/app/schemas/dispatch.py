"""Esquemas Pydantic de entrada y salida para el flujo estrella de la Decisión 1."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.frap import FRAPCreate

ZonaCorredor = Literal["tuxtla", "san_cristobal", "comitan"]
TipoRecurso = Literal["cama_uci", "quirofano", "sala_choque"]
EstadoVia = Literal["normal", "demora", "bloqueo"]

DECISION_SUPPORT_NOTICE = (
    "TraumaNet apoya la decisión; no decide ni sustituye el criterio clínico del regulador médico del CRUM."
)


class DispatchEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frap: FRAPCreate
    origen_zona: ZonaCorredor | None = Field(
        default=None,
        description="Zona de origen del incidente (se infiere del municipio si se omite).",
    )
    origen_hospital_id: int | None = Field(
        default=None,
        ge=1,
        description="Hospital de origen o referencia más cercano si el traslado parte desde una unidad.",
    )
    preferred_hospital_id: int | None = Field(
        default=None,
        ge=1,
        description="Hospital priorizado explícitamente por el CRUM para intentar la reserva primero.",
    )
    strict_preferred_hospital: bool = Field(
        default=False,
        description="Si es true junto con preferred_hospital_id, no deriva automáticamente a otros nodos si falla el preferido.",
    )
    ttl_minutos: int | None = Field(
        default=None,
        ge=1,
        le=120,
        description="Sobrescribe el TTL por defecto de la reserva (RESERVA_TTL_MIN=15).",
    )


class IncertidumbreRuta(BaseModel):
    eta_base_min: float | None = None
    margen_min: float | None = None
    eta_minimo_min: float | None = None
    eta_maximo_min: float | None = None
    estado_via: EstadoVia | None = None
    supuestos: str


class HospitalCandidato(BaseModel):
    hospital_id: int
    nombre: str
    zona: str
    municipio: str
    nivel_atencion: int
    eta_min: float
    eta_margen_min: float
    estado_via: EstadoVia
    tramo_id: str | None = None
    tipo_recurso: TipoRecurso
    recurso_disponibles: int
    data_vintage: datetime
    guardia_especialista_presente: bool
    compatible_grafo: bool
    compatible_operativo: bool


class HospitalDescartado(BaseModel):
    hospital_id: int
    nombre: str
    zona: str
    motivos_descarte: list[str]


class HospitalAsignado(BaseModel):
    hospital_id: int
    nombre: str
    municipio: str
    zona: str
    nivel_atencion: int
    eta_min: float
    eta_margen_min: float
    estado_via: EstadoVia
    tramo_id: str | None = None
    recurso_disponible_antes: int
    recurso_disponible_despues: int
    data_vintage: datetime


class ReservaConfirmada(BaseModel):
    reserva_id: str
    traslado_id: str
    recurso_id: int
    tipo_recurso: TipoRecurso
    cantidad: int
    estado: str
    creada_en: datetime
    expira_en: datetime
    ttl_minutos: int


class DispatchEvaluateResponse(BaseModel):
    decision_support_notice: str = DECISION_SUPPORT_NOTICE
    estado_despacho: Literal["asignado", "sin_asignacion"]
    frap_id: str
    protocolo_codigo: str
    recurso_critico: TipoRecurso | None = None
    hospital_asignado: HospitalAsignado | None = None
    reserva: ReservaConfirmada | None = None
    alternativas_rankeadas: list[HospitalCandidato] = Field(default_factory=list)
    hospitales_descartados: list[HospitalDescartado] = Field(default_factory=list)
    data_vintage: datetime | None = None
    data_vintage_segundos: int | None = None
    incertidumbre_ruta: IncertidumbreRuta
    alerta_concurrencia: bool = False
    motivo_sin_asignacion: str | None = None
    mensaje: str
