"""Esquemas Pydantic para la Hoja de Atención Prehospitalaria (FRAP) con 4 perfiles clínicos."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

TipoIncidente = Literal[
    "politrauma",
    "infarto_agudo",
    "trauma_craneoencefalico",
    "intoxicacion_quemaduras",
]
ProtocoloCodigo = Literal["PT-POLITRAUMA", "PT-IAM", "PT-TCE", "PT-INTOX-QUEM"]
EstadoFrap = Literal["reportado", "evaluando", "asignado", "sin_asignacion", "cerrado"]

PROTOCOLO_POR_INCIDENTE: dict[str, str] = {
    "politrauma": "PT-POLITRAUMA",
    "infarto_agudo": "PT-IAM",
    "trauma_craneoencefalico": "PT-TCE",
    "intoxicacion_quemaduras": "PT-INTOX-QUEM",
}


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PacienteSintetico(StrictModel):
    id_sintetico: str = Field(..., pattern=r"^SYN-[0-9A-Z]{6,12}$")
    sexo: Literal["F", "M", "indeterminado"]
    grupo_edad: Literal["pediatrico", "adulto", "adulto_mayor"]


class UbicacionEscena(StrictModel):
    municipio: str = Field(..., min_length=2, max_length=80)
    latitud: float = Field(..., ge=-90, le=90)
    longitud: float = Field(..., ge=-180, le=180)
    tramo_id: str | None = Field(default=None, max_length=40)
    referencia: str | None = Field(default=None, max_length=200)


class Triage(StrictModel):
    nivel: Literal["rojo", "amarillo", "verde", "negro"]
    evaluado_en: datetime
    observaciones: str | None = Field(default=None, max_length=500)


class SignosVitales(StrictModel):
    medido_en: datetime
    fc: int = Field(..., ge=0, le=300)
    fr: int = Field(..., ge=0, le=80)
    ta_sistolica: int = Field(..., ge=0, le=350)
    ta_diastolica: int = Field(..., ge=0, le=250)
    spo2: int = Field(..., ge=0, le=100)
    temperatura_c: float | None = Field(default=None, ge=20, le=45)
    glucosa_mgdl: int | None = Field(default=None, ge=0, le=1500)


class MedicamentoAplicado(StrictModel):
    nombre: str = Field(..., max_length=80)
    dosis: str = Field(..., max_length=40)
    via: Literal["iv", "io", "im", "vo", "sl", "inhalada", "topica"]
    aplicado_en: datetime


class LesionPolitrauma(StrictModel):
    region: Literal[
        "cabeza",
        "cuello",
        "torax",
        "abdomen",
        "pelvis",
        "columna",
        "extremidad_sup",
        "extremidad_inf",
    ]
    tipo_lesion: str = Field(..., max_length=80)
    ais: int = Field(..., ge=1, le=6)


class PerfilPolitrauma(StrictModel):
    tipo: Literal["politrauma"]
    mecanismo_lesion: Literal[
        "colision_vehicular",
        "atropellamiento",
        "caida_altura",
        "arma_blanca",
        "arma_fuego",
        "aplastamiento",
        "otro",
    ]
    lesiones: list[LesionPolitrauma] = Field(..., min_length=1)
    hemorragia_activa: bool
    torniquete_aplicado: bool | None = None
    requiere_quirofano_sospechado: bool | None = None
    iss_estimado: int | None = Field(default=None, ge=0, le=75)


class EcgHallazgo(StrictModel):
    elevacion_st: bool
    derivaciones_afectadas: list[
        Literal["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    ]
    ritmo: Literal[
        "sinusal",
        "fibrilacion_auricular",
        "taquicardia_ventricular",
        "fibrilacion_ventricular",
        "bloqueo_av",
        "otro",
    ] | None = None


class PerfilInfartoAgudo(StrictModel):
    tipo: Literal["infarto_agudo"]
    ecg: EcgHallazgo
    killip: int = Field(..., ge=1, le=4)
    inicio_dolor_min: int = Field(..., ge=0, le=4320)
    trombolisis_aplicada: bool | None = None
    troponina_rapida_positiva: bool | None = None


class GlasgowEscala(StrictModel):
    ocular: int = Field(..., ge=1, le=4)
    verbal: int = Field(..., ge=1, le=5)
    motor: int = Field(..., ge=1, le=6)
    total: int = Field(..., ge=3, le=15)

    @model_validator(mode="after")
    def _check_sum(self) -> "GlasgowEscala":
        if self.ocular + self.verbal + self.motor != self.total:
            raise ValueError("glasgow.total debe ser igual a ocular + verbal + motor.")
        return self


class PupilasHallazgo(StrictModel):
    izquierda_mm: float = Field(..., ge=1, le=9)
    derecha_mm: float = Field(..., ge=1, le=9)
    reactivas: bool


class PerfilTCE(StrictModel):
    tipo: Literal["trauma_craneoencefalico"]
    glasgow: GlasgowEscala
    pupilas: PupilasHallazgo
    signos_herniacion: bool | None = None
    via_aerea_asegurada: bool | None = None
    anticoagulado: bool | None = None
    convulsiones: bool | None = None


class PerfilIntoxicacionQuemaduras(StrictModel):
    tipo: Literal["intoxicacion_quemaduras"]
    subtipo: Literal["intoxicacion", "quemadura", "mixto"]
    agente: str | None = Field(default=None, max_length=100)
    via_exposicion: Literal["oral", "inhalada", "dermica", "parenteral", "ocular"] | None = None
    sct_quemada_pct: float | None = Field(default=None, ge=0, le=100)
    grado_quemadura: Literal["1", "2", "3"] | None = None
    lesion_inhalatoria: bool | None = None
    via_aerea_comprometida: bool
    descontaminacion_realizada: bool | None = None
    antidoto_aplicado: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def _check_subtipo_fields(self) -> "PerfilIntoxicacionQuemaduras":
        if self.subtipo in ("intoxicacion", "mixto") and not self.agente:
            raise ValueError("Para subtipo intoxicacion/mixto se requiere indicar el agente.")
        if self.subtipo in ("quemadura", "mixto") and self.sct_quemada_pct is None:
            raise ValueError("Para subtipo quemadura/mixto se requiere sct_quemada_pct.")
        return self


PerfilClinico = Annotated[
    Union[PerfilPolitrauma, PerfilInfartoAgudo, PerfilTCE, PerfilIntoxicacionQuemaduras],
    Field(discriminator="tipo"),
]


class FRAPCreate(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    tipo_incidente: TipoIncidente
    paciente_sintetico: PacienteSintetico
    ubicacion_escena: UbicacionEscena
    triage: Triage
    protocolo_codigo: ProtocoloCodigo
    signos_vitales: list[SignosVitales] = Field(..., min_length=1)
    ambulancia_id: int | None = Field(default=None, ge=1)
    medicamentos_aplicados: list[MedicamentoAplicado] | None = None
    notas: str | None = Field(default=None, max_length=2000)
    adjuntos: list[str] | None = None
    perfil: PerfilClinico

    @model_validator(mode="after")
    def _check_coherence(self) -> "FRAPCreate":
        if self.perfil.tipo != self.tipo_incidente:
            raise ValueError(
                f"Incoherencia: tipo_incidente='{self.tipo_incidente}' no coincide con perfil.tipo='{self.perfil.tipo}'."
            )
        expected_protocol = PROTOCOLO_POR_INCIDENTE[self.tipo_incidente]
        if self.protocolo_codigo != expected_protocol:
            raise ValueError(
                f"Incoherencia: protocolo_codigo='{self.protocolo_codigo}' no corresponde a '{self.tipo_incidente}' (esperado '{expected_protocol}')."
            )
        return self

    def to_mongo_document(self, estado_frap: EstadoFrap = "reportado") -> dict:
        """Convierte a dict compatible con $jsonSchema de MongoDB (fechas UTC y sin claves None)."""
        now_utc = datetime.now(timezone.utc)
        raw = self.model_dump(exclude_none=True)
        raw["estado_frap"] = estado_frap
        raw["creado_en"] = now_utc
        raw["actualizado_en"] = now_utc
        raw["triage"]["evaluado_en"] = _ensure_utc(raw["triage"]["evaluado_en"])
        for sv in raw["signos_vitales"]:
            sv["medido_en"] = _ensure_utc(sv["medido_en"])
        if "medicamentos_aplicados" in raw:
            for med in raw["medicamentos_aplicados"]:
                med["aplicado_en"] = _ensure_utc(med["aplicado_en"])
        return raw
