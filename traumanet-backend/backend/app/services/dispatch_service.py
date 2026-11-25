"""Servicio coordinador de la Decisión 1: asignación de hospital destino y reserva atómica.

Orquesta los tres repositorios (Documental -> Grafo -> Relacional) y aplica la política
explícita de fallos parciales (DATA_CONTEXT §3, R-01 y R-02).
"""
from __future__ import annotations

import logging
import unicodedata
from datetime import datetime, timezone
from typing import Any

from app.core.auth import ActorContext
from app.core.config import Settings
from app.core.exceptions import (
    DocumentUnavailableError,
    GraphUnavailableError,
    PartialWriteError,
    RelationalUnavailableError,
)
from app.repositories.document.document_repo import DocumentRepository
from app.repositories.graph.graph_repo import GraphRepository
from app.repositories.relational.relational_repo import RelationalRepository
from app.schemas.dispatch import (
    DECISION_SUPPORT_NOTICE,
    DispatchEvaluateRequest,
    DispatchEvaluateResponse,
    HospitalAsignado,
    HospitalCandidato,
    HospitalDescartado,
    IncertidumbreRuta,
    ReservaConfirmada,
)

logger = logging.getLogger("traumanet.dispatch")


def _normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower().strip()


def infer_zona(municipio: str) -> str:
    norm = _normalize_text(municipio)
    if "comitan" in norm:
        return "comitan"
    if "cristobal" in norm or "teopisca" in norm or "oxchuc" in norm:
        return "san_cristobal"
    return "tuxtla"


def _check_guardia_for_protocol(
    presentes: set[str],
    protocolo: dict[str, Any],
) -> tuple[bool, list[str]]:
    faltantes: list[str] = []
    grupos: dict[str, list[str]] = {}
    for req in protocolo["especialidades_requeridas"]:
        cod = req["codigo"]
        grp = req.get("grupo_alternativa")
        if grp:
            grupos.setdefault(grp, []).append(cod)
        elif cod not in presentes:
            faltantes.append(cod)
    for _grp, opciones in grupos.items():
        if not any(c in presentes for c in opciones):
            faltantes.append(" o ".join(opciones))
    return (len(faltantes) == 0), faltantes


def _build_route_uncertainty(
    eta_min: float | None,
    margen_min: float | None,
    estado_via: str | None,
    demora_factor: float,
) -> IncertidumbreRuta:
    if eta_min is None or margen_min is None:
        return IncertidumbreRuta(
            eta_base_min=None,
            margen_min=None,
            eta_minimo_min=None,
            eta_maximo_min=None,
            estado_via=None,
            supuestos="Sin ruta viable evaluada; requiere coordinación manual del CRUM.",
        )
    eta_lo = round(max(1.0, eta_min - margen_min), 1)
    eta_hi = round(eta_min + margen_min, 1)
    return IncertidumbreRuta(
        eta_base_min=round(eta_min, 1),
        margen_min=round(margen_min, 1),
        eta_minimo_min=eta_lo,
        eta_maximo_min=eta_hi,
        estado_via=estado_via,  # type: ignore[arg-type]
        supuestos=(
            f"Tiempos base del corredor Tuxtla-San Cristóbal-Comitán (topología de referencia A-05); "
            f"factor de penalización por demora={demora_factor}x; aristas en bloqueo excluidas."
        ),
    )


class DispatchService:
    def __init__(
        self,
        settings: Settings,
        relational_repo: RelationalRepository,
        document_repo: DocumentRepository,
        graph_repo: GraphRepository,
    ) -> None:
        self._settings = settings
        self._relational = relational_repo
        self._document = document_repo
        self._graph = graph_repo

    def _safe_mark_sin_asignacion(self, frap_id: str, motivo: str) -> None:
        try:
            self._document.update_frap_status(
                frap_id=frap_id,
                estado_frap="sin_asignacion",
                motivo_sin_asignacion=motivo,
            )
        except Exception as exc:
            logger.error(
                "RECONCILIACION_REQUERIDA: no se pudo marcar frap_id=%s como sin_asignacion (%s): %s",
                frap_id,
                motivo,
                exc,
            )

    def evaluate_and_assign(
        self,
        request: DispatchEvaluateRequest,
        actor: ActorContext,
    ) -> DispatchEvaluateResponse:
        frap_req = request.frap
        ttl = request.ttl_minutos or self._settings.reserva_ttl_min
        zona_origen = request.origen_zona or infer_zona(frap_req.ubicacion_escena.municipio)

        # 1) Persistir FRAP en Documental (MongoDB) — si falla aquí no hay efectos secundarios
        frap_doc = frap_req.to_mongo_document(estado_frap="reportado")
        frap_id = self._document.insert_frap(frap_doc)
        self._document.update_frap_status(frap_id=frap_id, estado_frap="evaluando")

        # 2) Consultar compatibilidad clínica y rutas en Grafo (Neo4j)
        try:
            graph_eval = self._graph.evaluate_hospitals_for_protocol(
                protocolo_codigo=frap_req.protocolo_codigo,
                origen_zona=zona_origen,
                origen_hospital_id=request.origen_hospital_id,
                demora_factor=self._settings.demora_penalty_factor,
            )
        except GraphUnavailableError as exc:
            motivo = "grafo_no_disponible: no se pudo evaluar compatibilidad ni rutas en Neo4j"
            self._safe_mark_sin_asignacion(frap_id, motivo)
            payload = DispatchEvaluateResponse(
                decision_support_notice=DECISION_SUPPORT_NOTICE,
                estado_despacho="sin_asignacion",
                frap_id=frap_id,
                protocolo_codigo=frap_req.protocolo_codigo,
                incertidumbre_ruta=_build_route_uncertainty(
                    None, None, None, self._settings.demora_penalty_factor
                ),
                motivo_sin_asignacion=motivo,
                mensaje="FRAP registrado en estado sin_asignacion por indisponibilidad del grafo. Intervención del CRUM requerida.",
            )
            raise PartialWriteError(str(exc), payload.model_dump(mode="json"), status_code=503) from exc

        protocolo = graph_eval["protocolo"]
        recurso_critico: str = protocolo["recurso_critico"]
        compatibles_grafo: list[dict[str, Any]] = graph_eval["compatibles"]
        descartados_map: dict[int, HospitalDescartado] = {
            d["hospital_id"]: HospitalDescartado(
                hospital_id=d["hospital_id"],
                nombre=d["nombre"],
                zona=d["zona"],
                motivos_descarte=list(d["motivos_descarte"]),
            )
            for d in graph_eval["descartados"]
        }

        # 3) Consultar capacidad en vivo y guardias en Relacional (PostgreSQL)
        compatible_ids = [c["hospital_id"] for c in compatibles_grafo]
        all_req_esp = [r["codigo"] for r in protocolo["especialidades_requeridas"]]
        try:
            hospitals_meta = self._relational.get_hospitals_map()
            capacity_map = self._relational.get_capacity_for_resource(compatible_ids, recurso_critico)
            guardia_map = self._relational.get_active_guardia(compatible_ids, all_req_esp)
        except RelationalUnavailableError as exc:
            motivo = "relacional_no_disponible: fallo al consultar capacidad en vivo en PostgreSQL"
            self._safe_mark_sin_asignacion(frap_id, motivo)
            payload = DispatchEvaluateResponse(
                decision_support_notice=DECISION_SUPPORT_NOTICE,
                estado_despacho="sin_asignacion",
                frap_id=frap_id,
                protocolo_codigo=frap_req.protocolo_codigo,
                recurso_critico=recurso_critico,  # type: ignore[arg-type]
                hospitales_descartados=list(descartados_map.values()),
                incertidumbre_ruta=_build_route_uncertainty(
                    compatibles_grafo[0]["eta_min"] if compatibles_grafo else None,
                    compatibles_grafo[0]["eta_margen_min"] if compatibles_grafo else None,
                    compatibles_grafo[0]["estado_via"] if compatibles_grafo else None,
                    self._settings.demora_penalty_factor,
                ),
                motivo_sin_asignacion=motivo,
                mensaje="FRAP guardado en estado sin_asignacion porque PostgreSQL no respondió al consultar capacidad en vivo.",
            )
            raise PartialWriteError(str(exc), payload.model_dump(mode="json"), status_code=503) from exc

        # 4) Cruzar compatibilidad de grafo + capacidad real + guardia activa
        now_utc = datetime.now(timezone.utc)
        alternativas: list[HospitalCandidato] = []
        viables: list[HospitalCandidato] = []
        vintages: list[datetime] = []

        for c in compatibles_grafo:
            hid = c["hospital_id"]
            meta = hospitals_meta.get(hid)
            cap = capacity_map.get(hid)
            if meta is None or cap is None:
                descartados_map[hid] = HospitalDescartado(
                    hospital_id=hid,
                    nombre=c["nombre"],
                    zona=c["zona"],
                    motivos_descarte=[f"Hospital sin inventario activo de '{recurso_critico}' en base relacional"],
                )
                continue

            vintages.append(cap["actualizado_en"])
            guardia_ok, esp_ausentes = _check_guardia_for_protocol(guardia_map.get(hid, set()), protocolo)
            disponibles = int(cap["disponibles"])

            motivos_op: list[str] = []
            if not guardia_ok:
                motivos_op.append(
                    f"Especialista de guardia ausente en turno actual: {', '.join(esp_ausentes)}"
                )
            if disponibles < 1:
                motivos_op.append(f"Sin disponibilidad en vivo de {recurso_critico} (0 disponibles)")

            candidato = HospitalCandidato(
                hospital_id=hid,
                nombre=meta["nombre"],
                zona=c["zona"],
                municipio=meta["municipio"],
                nivel_atencion=meta["nivel_atencion"],
                eta_min=c["eta_min"],
                eta_margen_min=c["eta_margen_min"],
                estado_via=c["estado_via"],
                tramo_id=c["tramo_id"],
                tipo_recurso=recurso_critico,  # type: ignore[arg-type]
                recurso_disponibles=disponibles,
                data_vintage=cap["actualizado_en"],
                guardia_especialista_presente=guardia_ok,
                compatible_grafo=True,
                compatible_operativo=(len(motivos_op) == 0),
            )
            alternativas.append(candidato)
            if candidato.compatible_operativo:
                viables.append(candidato)
            else:
                descartados_map[hid] = HospitalDescartado(
                    hospital_id=hid,
                    nombre=meta["nombre"],
                    zona=c["zona"],
                    motivos_descarte=motivos_op,
                )

        oldest_vintage = min(vintages) if vintages else None
        vintage_seconds = (
            max(0, int((now_utc - oldest_vintage).total_seconds()))
            if oldest_vintage is not None
            else None
        )

        # Aplicar preferencia explícita del CRUM si se solicitó
        attempt_list = list(viables)
        if request.preferred_hospital_id is not None:
            pref = [v for v in attempt_list if v.hospital_id == request.preferred_hospital_id]
            others = [v for v in attempt_list if v.hospital_id != request.preferred_hospital_id]
            if request.strict_preferred_hospital:
                attempt_list = pref
            else:
                attempt_list = pref + others

        # 5) Ejecutar reserva atómica ACID con bloqueo de fila (SELECT ... FOR UPDATE)
        alerta_concurrencia = False
        assigned_candidate: HospitalCandidato | None = None
        reserva_result: dict[str, Any] | None = None

        for cand in attempt_list:
            try:
                res = self._relational.reserve_resource_atomic(
                    hospital_id=cand.hospital_id,
                    tipo_recurso=recurso_critico,
                    frap_id=frap_id,
                    protocolo_codigo=frap_req.protocolo_codigo,
                    eta_min=cand.eta_min,
                    eta_margen_min=cand.eta_margen_min,
                    estado_via=cand.estado_via,
                    solicitado_por=actor.usuario_id,
                    ambulancia_id=frap_req.ambulancia_id,
                    ttl_minutos=ttl,
                    cantidad=1,
                )
            except RelationalUnavailableError as exc:
                motivo = "relacional_no_disponible: fallo durante transacción de reserva en PostgreSQL"
                self._safe_mark_sin_asignacion(frap_id, motivo)
                payload = DispatchEvaluateResponse(
                    decision_support_notice=DECISION_SUPPORT_NOTICE,
                    estado_despacho="sin_asignacion",
                    frap_id=frap_id,
                    protocolo_codigo=frap_req.protocolo_codigo,
                    recurso_critico=recurso_critico,  # type: ignore[arg-type]
                    alternativas_rankeadas=alternativas,
                    hospitales_descartados=list(descartados_map.values()),
                    data_vintage=oldest_vintage,
                    data_vintage_segundos=vintage_seconds,
                    incertidumbre_ruta=_build_route_uncertainty(
                        cand.eta_min,
                        cand.eta_margen_min,
                        cand.estado_via,
                        self._settings.demora_penalty_factor,
                    ),
                    alerta_concurrencia=alerta_concurrencia,
                    motivo_sin_asignacion=motivo,
                    mensaje=(
                        "FRAP guardado en MongoDB y marcado como sin_asignacion porque falló la reserva en PostgreSQL. "
                        "Se adjuntan alternativas evaluadas para decisión manual del CRUM."
                    ),
                )
                raise PartialWriteError(str(exc), payload.model_dump(mode="json"), status_code=503) from exc

            if res is None:
                # Perdió carrera de concurrencia o el recurso se agotó entre la lectura y FOR UPDATE
                alerta_concurrencia = True
                descartados_map[cand.hospital_id] = HospitalDescartado(
                    hospital_id=cand.hospital_id,
                    nombre=cand.nombre,
                    zona=cand.zona,
                    motivos_descarte=[
                        f"Sin disponibilidad al intentar reserva atómica de {recurso_critico} (concurrencia detectada)"
                    ],
                )
                continue

            assigned_candidate = cand
            reserva_result = res
            break

        # 6) Si no se logró reservar en ningún hospital viable -> marcar FRAP sin_asignacion (HTTP 409)
        if assigned_candidate is None or reserva_result is None:
            if not compatibles_grafo:
                motivo = (
                    f"sin_compatibilidad_red: ningún hospital cumple el protocolo {frap_req.protocolo_codigo} "
                    "o todas las rutas hacia hospitales compatibles están bloqueadas"
                )
            elif alerta_concurrencia:
                motivo = (
                    f"sin_disponibilidad: concurrencia detectada al reservar {recurso_critico}; "
                    "el recurso se agotó durante el bloqueo atómico de fila"
                )
            elif request.preferred_hospital_id is not None and request.strict_preferred_hospital:
                pref_disc = descartados_map.get(request.preferred_hospital_id)
                detalle_pref = "; ".join(pref_disc.motivos_descarte) if pref_disc else "sin disponibilidad"
                motivo = (
                    f"hospital_preferido_no_viable: HOSP-0{request.preferred_hospital_id} descartado "
                    f"({detalle_pref})"
                )
            else:
                sin_guardia = sum(1 for a in alternativas if not a.guardia_especialista_presente)
                sin_cama = sum(1 for a in alternativas if a.recurso_disponibles < 1)
                if alternativas and sin_guardia == len(alternativas) and sin_cama == 0:
                    motivo = (
                        "sin_guardia_activa: los hospitales compatibles en red no tienen "
                        "especialistas de guardia vigentes en el turno actual"
                    )
                elif alternativas and sin_guardia > 0 and sin_cama > 0:
                    motivo = (
                        f"sin_viabilidad_operativa: entre los {len(alternativas)} hospitales compatibles, "
                        f"{sin_guardia} carecen de guardia vigente y {sin_cama} no tienen {recurso_critico} disponible"
                    )
                else:
                    motivo = (
                        f"sin_disponibilidad: ningún hospital compatible con guardia activa cuenta con "
                        f"{recurso_critico} disponible"
                    )
            self._safe_mark_sin_asignacion(frap_id, motivo)
            ref_cand = alternativas[0] if alternativas else None
            payload = DispatchEvaluateResponse(
                decision_support_notice=DECISION_SUPPORT_NOTICE,
                estado_despacho="sin_asignacion",
                frap_id=frap_id,
                protocolo_codigo=frap_req.protocolo_codigo,
                recurso_critico=recurso_critico,  # type: ignore[arg-type]
                alternativas_rankeadas=alternativas,
                hospitales_descartados=list(descartados_map.values()),
                data_vintage=oldest_vintage,
                data_vintage_segundos=vintage_seconds,
                incertidumbre_ruta=_build_route_uncertainty(
                    ref_cand.eta_min if ref_cand else None,
                    ref_cand.eta_margen_min if ref_cand else None,
                    ref_cand.estado_via if ref_cand else None,
                    self._settings.demora_penalty_factor,
                ),
                alerta_concurrencia=alerta_concurrencia,
                motivo_sin_asignacion=motivo,
                mensaje=(
                    f"No se concretó reserva atómica ({motivo}). El FRAP quedó en estado sin_asignacion "
                    "para evaluación manual o estabilización coordinada por el CRUM."
                ),
            )
            raise PartialWriteError(motivo, payload.model_dump(mode="json"), status_code=409)

        # 7) Actualizar FRAP en MongoDB a 'asignado'; si falla, compensar liberando reserva en PostgreSQL
        try:
            self._document.update_frap_status(
                frap_id=frap_id,
                estado_frap="asignado",
                hospital_destino_id=assigned_candidate.hospital_id,
                traslado_id=reserva_result["traslado_id"],
                ambulancia_id=frap_req.ambulancia_id,
            )
        except DocumentUnavailableError as exc:
            compensated = self._relational.compensate_release_reservation(
                reserva_result["reserva_id"], reserva_result["traslado_id"]
            )
            motivo = (
                "fallo_actualizacion_frap_post_reserva: reserva compensada en PostgreSQL"
                if compensated
                else "fallo_actualizacion_frap_post_reserva: requiere reconciliación manual"
            )
            payload = DispatchEvaluateResponse(
                decision_support_notice=DECISION_SUPPORT_NOTICE,
                estado_despacho="sin_asignacion",
                frap_id=frap_id,
                protocolo_codigo=frap_req.protocolo_codigo,
                recurso_critico=recurso_critico,  # type: ignore[arg-type]
                alternativas_rankeadas=alternativas,
                hospitales_descartados=list(descartados_map.values()),
                data_vintage=reserva_result["data_vintage"],
                data_vintage_segundos=vintage_seconds,
                incertidumbre_ruta=_build_route_uncertainty(
                    assigned_candidate.eta_min,
                    assigned_candidate.eta_margen_min,
                    assigned_candidate.estado_via,
                    self._settings.demora_penalty_factor,
                ),
                alerta_concurrencia=alerta_concurrencia,
                motivo_sin_asignacion=motivo,
                mensaje="Fallo al confirmar estado del FRAP tras reservar; se aplicó compensación en PostgreSQL.",
            )
            raise PartialWriteError(str(exc), payload.model_dump(mode="json"), status_code=503) from exc

        # 8) Respuesta unificada de la Decisión 1
        assigned_vintage = reserva_result["data_vintage"]
        assigned_vintage_sec = max(0, int((now_utc - assigned_vintage).total_seconds()))
        return DispatchEvaluateResponse(
            decision_support_notice=DECISION_SUPPORT_NOTICE,
            estado_despacho="asignado",
            frap_id=frap_id,
            protocolo_codigo=frap_req.protocolo_codigo,
            recurso_critico=recurso_critico,  # type: ignore[arg-type]
            hospital_asignado=HospitalAsignado(
                hospital_id=assigned_candidate.hospital_id,
                nombre=assigned_candidate.nombre,
                municipio=assigned_candidate.municipio,
                zona=assigned_candidate.zona,
                nivel_atencion=assigned_candidate.nivel_atencion,
                eta_min=assigned_candidate.eta_min,
                eta_margen_min=assigned_candidate.eta_margen_min,
                estado_via=assigned_candidate.estado_via,
                tramo_id=assigned_candidate.tramo_id,
                recurso_disponible_antes=reserva_result["disponibles_antes"],
                recurso_disponible_despues=reserva_result["disponibles_despues"],
                data_vintage=assigned_vintage,
            ),
            reserva=ReservaConfirmada(
                reserva_id=reserva_result["reserva_id"],
                traslado_id=reserva_result["traslado_id"],
                recurso_id=reserva_result["recurso_id"],
                tipo_recurso=recurso_critico,  # type: ignore[arg-type]
                cantidad=reserva_result["cantidad"],
                estado=reserva_result["estado"],
                creada_en=reserva_result["creada_en"],
                expira_en=reserva_result["expira_en"],
                ttl_minutos=reserva_result["ttl_minutos"],
            ),
            alternativas_rankeadas=alternativas,
            hospitales_descartados=list(descartados_map.values()),
            data_vintage=assigned_vintage,
            data_vintage_segundos=assigned_vintage_sec,
            incertidumbre_ruta=_build_route_uncertainty(
                assigned_candidate.eta_min,
                assigned_candidate.eta_margen_min,
                assigned_candidate.estado_via,
                self._settings.demora_penalty_factor,
            ),
            alerta_concurrencia=alerta_concurrencia,
            mensaje=(
                f"Propuesta confirmada con reserva temporal ({ttl} min) de {recurso_critico} "
                f"en {assigned_candidate.nombre}. Sujeta a autorización final del regulador CRUM."
            ),
        )
