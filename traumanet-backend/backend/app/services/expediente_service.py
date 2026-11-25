"""Servicio de consulta de expediente FRAP unificado (Documental + Relacional)."""
from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.repositories.document.document_repo import DocumentRepository
from app.repositories.relational.relational_repo import RelationalRepository
from app.schemas.expediente import (
    ExpedienteFRAPResponse,
    ReservaExpediente,
    TrasladoExpediente,
)


class ExpedienteService:
    def __init__(
        self,
        document_repo: DocumentRepository,
        relational_repo: RelationalRepository,
    ) -> None:
        self._document = document_repo
        self._relational = relational_repo

    def get_expediente(self, frap_id: str) -> ExpedienteFRAPResponse:
        frap = self._document.get_frap_by_id(frap_id)
        if frap is None:
            raise NotFoundError(f"FRAP '{frap_id}' no encontrado en la base documental.")

        traslado_raw = self._relational.get_traslado_by_frap_id(frap_id)
        traslado = None
        if traslado_raw is not None:
            traslado = TrasladoExpediente(
                traslado_id=traslado_raw["traslado_id"],
                hospital_destino_id=traslado_raw["hospital_destino_id"],
                hospital_destino_nombre=traslado_raw["hospital_destino_nombre"],
                ambulancia_id=traslado_raw["ambulancia_id"],
                protocolo_codigo=traslado_raw["protocolo_codigo"],
                estado=traslado_raw["estado"],
                eta_min=traslado_raw["eta_min"],
                eta_margen_min=traslado_raw["eta_margen_min"],
                estado_via=traslado_raw["estado_via"],
                data_vintage=traslado_raw["data_vintage"],
                creado_en=traslado_raw["creado_en"],
                actualizado_en=traslado_raw["actualizado_en"],
                reservas=[ReservaExpediente(**r) for r in traslado_raw["reservas"]],
            )
        return ExpedienteFRAPResponse(frap_id=frap_id, frap=frap, traslado=traslado)

    def list_fraps(
        self,
        *,
        estado_frap: str | None = None,
        tipo_incidente: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        return self._document.list_fraps(
            estado_frap=estado_frap,
            tipo_incidente=tipo_incidente,
            limit=limit,
        )
