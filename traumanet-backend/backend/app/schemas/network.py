"""Esquemas Pydantic para consulta de red hospitalaria y derivación en cascada (Decisión 2)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.dispatch import DECISION_SUPPORT_NOTICE, EstadoVia, TipoRecurso


class RecursoResumen(BaseModel):
    recurso_id: int
    tipo_recurso: TipoRecurso
    total: int
    ocupados: int
    reservados: int
    disponibles: int
    actualizado_en: datetime


class ConexionResumen(BaseModel):
    destino_hospital_id: int
    destino_nombre: str
    tramo_id: str
    distancia_km: float
    tiempo_min: float
    incertidumbre_min: float
    estado_via: EstadoVia


class HospitalRedItem(BaseModel):
    hospital_id: int
    clave: str
    nombre: str
    municipio: str
    zona: str
    nivel_atencion: int
    especialidades: list[str]
    equipos_operativos: list[str]
    recursos: list[RecursoResumen]
    conexiones: list[ConexionResumen]


class NetworkOverviewResponse(BaseModel):
    decision_support_notice: str = DECISION_SUPPORT_NOTICE
    total_hospitales: int
    hospitales: list[HospitalRedItem]


class CascadeOption(BaseModel):
    hospital_id: int
    nombre: str
    zona: str
    nivel_atencion: int
    tramo_id: str
    distancia_km: float
    eta_min: float
    eta_margen_min: float
    estado_via: EstadoVia
    tipo_recurso: TipoRecurso
    recurso_disponibles: int
    data_vintage: datetime
    guardia_presente: bool
    viable: bool
    motivo_no_viable: str | None = None


class CascadeDerivationResponse(BaseModel):
    decision_support_notice: str = DECISION_SUPPORT_NOTICE
    hospital_saturado_id: int
    protocolo_codigo: str
    recurso_critico: TipoRecurso
    opciones_derivacion: list[CascadeOption]
    data_vintage: datetime | None = None


class TramoUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    estado_via: EstadoVia = Field(..., description="Nuevo estado operativo del tramo vial.")


class TramoUpdateResponse(BaseModel):
    tramo_id: str
    estado_via: EstadoVia
    aristas_actualizadas: int
