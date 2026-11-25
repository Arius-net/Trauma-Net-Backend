"""Repositorio Documental (MongoDB) — acceso aislado a la colección `fraps`."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError, WriteError

from app.core.database import DatabaseClients
from app.core.exceptions import DocumentUnavailableError, DocumentValidationError


def _serialize_frap(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    if "_id" in out:
        out["frap_id"] = str(out.pop("_id"))
    return out


class DocumentRepository:
    """Gestiona documentos FRAP en MongoDB respetando el validador $jsonSchema."""

    COLLECTION = "fraps"

    def __init__(self, clients: DatabaseClients) -> None:
        self._clients = clients

    @property
    def _col(self):
        return self._clients.mongo_db[self.COLLECTION]

    def ping(self) -> bool:
        try:
            res = self._clients.mongo_db.command("ping")
            return bool(res.get("ok"))
        except Exception:
            return False

    def insert_frap(self, document: dict[str, Any]) -> str:
        try:
            res = self._col.insert_one(document)
            return str(res.inserted_id)
        except WriteError as exc:
            if exc.code == 121:
                raise DocumentValidationError(
                    f"FRAP rechazado por el validador $jsonSchema de MongoDB: {exc.details}"
                ) from exc
            raise DocumentUnavailableError(f"Error escribiendo FRAP en MongoDB: {exc}") from exc
        except PyMongoError as exc:
            raise DocumentUnavailableError(f"MongoDB no disponible al insertar FRAP: {exc}") from exc

    def update_frap_status(
        self,
        *,
        frap_id: str,
        estado_frap: str,
        hospital_destino_id: int | None = None,
        traslado_id: str | None = None,
        ambulancia_id: int | None = None,
        motivo_sin_asignacion: str | None = None,
    ) -> bool:
        try:
            oid = ObjectId(frap_id)
        except InvalidId:
            return False

        update_set: dict[str, Any] = {
            "estado_frap": estado_frap,
            "actualizado_en": datetime.now(timezone.utc),
        }
        if hospital_destino_id is not None:
            update_set["hospital_destino_id"] = int(hospital_destino_id)
        if traslado_id is not None:
            update_set["traslado_id"] = str(traslado_id)
        if ambulancia_id is not None:
            update_set["ambulancia_id"] = int(ambulancia_id)
        if motivo_sin_asignacion is not None:
            update_set["motivo_sin_asignacion"] = str(motivo_sin_asignacion)[:300]

        try:
            res = self._col.update_one({"_id": oid}, {"$set": update_set})
            return res.matched_count == 1
        except WriteError as exc:
            if exc.code == 121:
                raise DocumentValidationError(
                    f"Actualización de FRAP rechazada por $jsonSchema: {exc.details}"
                ) from exc
            raise DocumentUnavailableError(f"Error actualizando FRAP en MongoDB: {exc}") from exc
        except PyMongoError as exc:
            raise DocumentUnavailableError(f"MongoDB no disponible al actualizar FRAP: {exc}") from exc

    def get_frap_by_id(self, frap_id: str) -> dict[str, Any] | None:
        try:
            oid = ObjectId(frap_id)
        except InvalidId:
            return None
        try:
            doc = self._col.find_one({"_id": oid})
            return _serialize_frap(doc) if doc is not None else None
        except PyMongoError as exc:
            raise DocumentUnavailableError(f"MongoDB no disponible al leer FRAP: {exc}") from exc

    def list_fraps(
        self,
        *,
        estado_frap: str | None = None,
        tipo_incidente: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if estado_frap is not None:
            query["estado_frap"] = estado_frap
        if tipo_incidente is not None:
            query["tipo_incidente"] = tipo_incidente
        try:
            cursor = self._col.find(query).sort("creado_en", -1).limit(max(1, min(limit, 200)))
            return [_serialize_frap(d) for d in cursor]
        except PyMongoError as exc:
            raise DocumentUnavailableError(f"MongoDB no disponible al listar FRAPs: {exc}") from exc
