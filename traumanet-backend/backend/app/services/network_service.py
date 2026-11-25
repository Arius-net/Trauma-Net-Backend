"""Servicio de red hospitalaria y derivación en cascada (Grafo + Relacional)."""
from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.repositories.graph.graph_repo import GraphRepository
from app.repositories.relational.relational_repo import RelationalRepository
from app.schemas.network import (
    CascadeDerivationResponse,
    CascadeOption,
    ConexionResumen,
    HospitalRedItem,
    NetworkOverviewResponse,
    RecursoResumen,
    TramoUpdateResponse,
)
from app.services.dispatch_service import _check_guardia_for_protocol


class NetworkService:
    def __init__(
        self,
        settings: Settings,
        relational_repo: RelationalRepository,
        graph_repo: GraphRepository,
    ) -> None:
        self._settings = settings
        self._relational = relational_repo
        self._graph = graph_repo

    def get_network_overview(self) -> NetworkOverviewResponse:
        hospitals_pg = self._relational.get_hospitals_map()
        resources_pg = self._relational.get_all_resources_by_hospital()
        hospitals_graph, edges_by_origin = self._graph.get_network_topology()

        items: list[HospitalRedItem] = []
        for hg in hospitals_graph:
            hid = int(hg["hospital_id"])
            meta = hospitals_pg.get(hid)
            if meta is None:
                continue
            items.append(
                HospitalRedItem(
                    hospital_id=hid,
                    clave=meta["clave"],
                    nombre=meta["nombre"],
                    municipio=meta["municipio"],
                    zona=hg["zona"],
                    nivel_atencion=meta["nivel_atencion"],
                    especialidades=sorted(hg["especialidades"]),
                    equipos_operativos=sorted(hg["equipos_operativos"]),
                    recursos=[RecursoResumen(**r) for r in resources_pg.get(hid, [])],
                    conexiones=[ConexionResumen(**e) for e in edges_by_origin.get(hid, [])],
                )
            )
        return NetworkOverviewResponse(total_hospitales=len(items), hospitales=items)

    def evaluate_cascade_derivation(
        self,
        *,
        hospital_saturado_id: int,
        protocolo_codigo: str,
    ) -> CascadeDerivationResponse:
        hospitals_pg = self._relational.get_hospitals_map()
        if hospital_saturado_id not in hospitals_pg:
            raise NotFoundError(f"Hospital saturado {hospital_saturado_id} no existe.")

        eval_res = self._graph.evaluate_hospitals_for_protocol(
            protocolo_codigo=protocolo_codigo,
            origen_hospital_id=hospital_saturado_id,
            demora_factor=self._settings.demora_penalty_factor,
        )
        protocolo = eval_res["protocolo"]
        recurso_critico = protocolo["recurso_critico"]
        vecinos = [c for c in eval_res["compatibles"] if c["hospital_id"] != hospital_saturado_id]

        vecino_ids = [v["hospital_id"] for v in vecinos]
        cap_map = self._relational.get_capacity_for_resource(vecino_ids, recurso_critico)
        req_esp = [r["codigo"] for r in protocolo["especialidades_requeridas"]]
        guardia_map = self._relational.get_active_guardia(vecino_ids, req_esp)

        opciones: list[CascadeOption] = []
        vintages = []
        for v in vecinos:
            hid = v["hospital_id"]
            meta = hospitals_pg.get(hid)
            cap = cap_map.get(hid)
            if meta is None or cap is None:
                continue
            vintages.append(cap["actualizado_en"])
            guardia_ok, faltantes = _check_guardia_for_protocol(guardia_map.get(hid, set()), protocolo)
            disponibles = int(cap["disponibles"])
            motivos = []
            if not guardia_ok:
                motivos.append(f"Guardia ausente: {', '.join(faltantes)}")
            if disponibles < 1:
                motivos.append(f"Sin {recurso_critico} disponible")

            opciones.append(
                CascadeOption(
                    hospital_id=hid,
                    nombre=meta["nombre"],
                    zona=v["zona"],
                    nivel_atencion=meta["nivel_atencion"],
                    tramo_id=v["tramo_id"],
                    distancia_km=v["distancia_km"],
                    eta_min=v["eta_min"],
                    eta_margen_min=v["eta_margen_min"],
                    estado_via=v["estado_via"],
                    tipo_recurso=recurso_critico,
                    recurso_disponibles=disponibles,
                    data_vintage=cap["actualizado_en"],
                    guardia_presente=guardia_ok,
                    viable=(len(motivos) == 0),
                    motivo_no_viable="; ".join(motivos) if motivos else None,
                )
            )

        opciones.sort(key=lambda o: (not o.viable, o.eta_min))
        return CascadeDerivationResponse(
            hospital_saturado_id=hospital_saturado_id,
            protocolo_codigo=protocolo_codigo,
            recurso_critico=recurso_critico,
            opciones_derivacion=opciones,
            data_vintage=min(vintages) if vintages else None,
        )

    def update_tramo_estado(self, tramo_id: str, estado_via: str) -> TramoUpdateResponse:
        updated = self._graph.update_tramo_estado(tramo_id=tramo_id, estado_via=estado_via)
        if updated == 0:
            raise NotFoundError(f"No se encontraron aristas para el tramo '{tramo_id}'.")
        return TramoUpdateResponse(
            tramo_id=tramo_id,
            estado_via=estado_via,  # type: ignore[arg-type]
            aristas_actualizadas=updated,
        )
