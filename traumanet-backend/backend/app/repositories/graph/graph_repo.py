"""Repositorio de Grafo (Neo4j) — consultas Cypher 100% parametrizadas."""
from __future__ import annotations

from typing import Any

from neo4j.exceptions import Neo4jError

from app.core.database import DatabaseClients
from app.core.exceptions import GraphUnavailableError, NotFoundError

Q_PING = "RETURN 1 AS ok"

Q_PROTOCOLO = """
MATCH (p:ProtocoloTrauma {codigo: $codigo})
OPTIONAL MATCH (p)-[re:REQUIERE_ESPECIALIDAD]->(e:Especialidad)
WHERE re.obligatoria = true
WITH p, collect(DISTINCT {codigo: e.codigo, grupo_alternativa: re.grupo_alternativa}) AS esp_req
OPTIONAL MATCH (p)-[rq:REQUIERE_EQUIPO]->(q:EquipoBiomedico)
WHERE rq.obligatoria = true
RETURN p.codigo AS codigo,
       p.nombre AS nombre,
       p.tipo_incidente AS tipo_incidente,
       p.recurso_critico AS recurso_critico,
       [x IN esp_req WHERE x.codigo IS NOT NULL] AS especialidades_requeridas,
       collect(DISTINCT q.codigo) AS equipos_requeridos
"""

Q_HOSPITALES_CAPACIDADES = """
MATCH (h:Hospital)
OPTIONAL MATCH (h)-[:CUENTA_CON]->(e:Especialidad)
WITH h, collect(DISTINCT e.codigo) AS especialidades
OPTIONAL MATCH (h)-[te:TIENE_EQUIPO]->(q:EquipoBiomedico)
WHERE te.operativo = true
RETURN h.hospital_id AS hospital_id,
       h.nombre AS nombre,
       h.zona AS zona,
       especialidades,
       collect(DISTINCT q.codigo) AS equipos_operativos
ORDER BY h.hospital_id
"""

Q_ANCHOR_POR_ZONA = """
MATCH (h:Hospital {zona: $zona})
RETURN h.hospital_id AS hospital_id
ORDER BY h.hospital_id
LIMIT 1
"""

# Calcula ruta directa y rutas de 2 saltos sin aristas bloqueadas desde un hospital origen.
Q_RUTAS_DESDE_HOSPITAL = """
MATCH (orig:Hospital {hospital_id: $origen_id})
MATCH (dest:Hospital)
WHERE dest.hospital_id <> orig.hospital_id
OPTIONAL MATCH (orig)-[direct:CONECTADO_CON]->(dest)
OPTIONAL MATCH (orig)-[r1:CONECTADO_CON]->(mid:Hospital)-[r2:CONECTADO_CON]->(dest)
WHERE r1.estado_via <> 'bloqueo' AND r2.estado_via <> 'bloqueo'
  AND mid.hospital_id <> orig.hospital_id AND mid.hospital_id <> dest.hospital_id
WITH orig, dest, direct,
     collect(
       CASE WHEN r1 IS NOT NULL AND r2 IS NOT NULL THEN {
         tramo_id: r1.tramo_id + ' + ' + r2.tramo_id,
         distancia_km: r1.distancia_km + r2.distancia_km,
         tiempo_base: r1.tiempo_min + r2.tiempo_min,
         tiempo_efectivo:
           (CASE WHEN r1.estado_via = 'demora' THEN r1.tiempo_min * $demora_factor ELSE r1.tiempo_min END) +
           (CASE WHEN r2.estado_via = 'demora' THEN r2.tiempo_min * $demora_factor ELSE r2.tiempo_min END),
         incertidumbre_min: r1.incertidumbre_min + r2.incertidumbre_min,
         estado_via: CASE WHEN r1.estado_via = 'demora' OR r2.estado_via = 'demora' THEN 'demora' ELSE 'normal' END
       } END
     ) AS indirectas_raw
WITH dest, direct, [x IN indirectas_raw WHERE x IS NOT NULL] AS indirectas
RETURN dest.hospital_id AS hospital_id,
       dest.zona AS zona,
       CASE WHEN direct IS NOT NULL THEN {
         tramo_id: direct.tramo_id,
         distancia_km: direct.distancia_km,
         tiempo_base: direct.tiempo_min,
         tiempo_efectivo:
           CASE WHEN direct.estado_via = 'demora' THEN direct.tiempo_min * $demora_factor ELSE direct.tiempo_min END,
         incertidumbre_min: direct.incertidumbre_min,
         estado_via: direct.estado_via
       } END AS directa,
       indirectas
"""

Q_NETWORK_EDGES = """
MATCH (a:Hospital)-[c:CONECTADO_CON]->(b:Hospital)
RETURN a.hospital_id AS origen_id,
       b.hospital_id AS destino_id,
       b.nombre AS destino_nombre,
       c.tramo_id AS tramo_id,
       c.distancia_km AS distancia_km,
       c.tiempo_min AS tiempo_min,
       c.incertidumbre_min AS incertidumbre_min,
       c.estado_via AS estado_via
ORDER BY a.hospital_id, c.tiempo_min
"""

Q_UPDATE_TRAMO = """
MATCH ()-[c:CONECTADO_CON {tramo_id: $tramo_id}]->()
SET c.estado_via = $estado_via,
    c.actualizado_en = datetime()
RETURN count(c) AS actualizadas
"""


def _check_protocol_match(
    hospital: dict[str, Any],
    protocolo: dict[str, Any],
) -> tuple[bool, list[str], list[str]]:
    """Evalúa especialidades (incluyendo grupo_alternativa A-10) y equipo operativo."""
    esp_set = set(hospital["especialidades"])
    eq_set = set(hospital["equipos_operativos"])
    motivos: list[str] = []
    esp_necesarias_guardia: list[str] = []

    grupos: dict[str, list[str]] = {}
    for req in protocolo["especialidades_requeridas"]:
        cod = req["codigo"]
        grp = req.get("grupo_alternativa")
        if grp:
            grupos.setdefault(grp, []).append(cod)
        else:
            if cod not in esp_set:
                motivos.append(f"No cuenta con especialidad requerida: {cod}")
            else:
                esp_necesarias_guardia.append(cod)

    for grp, opciones in grupos.items():
        presentes = [c for c in opciones if c in esp_set]
        if not presentes:
            motivos.append(f"No cuenta con ninguna especialidad alternativa requerida ({' o '.join(opciones)})")
        else:
            # Para guardia se aceptará cualquiera de las alternativas que el hospital sí posee
            esp_necesarias_guardia.extend(presentes)

    for eq in protocolo["equipos_requeridos"]:
        if eq not in eq_set:
            motivos.append(f"Falta equipo biomédico operativo: {eq}")

    return (len(motivos) == 0), motivos, esp_necesarias_guardia


def _select_best_route(directa: dict | None, indirectas: list[dict]) -> dict[str, Any]:
    opciones: list[dict[str, Any]] = []
    if directa is not None and directa["estado_via"] != "bloqueo":
        opciones.append(directa)
    opciones.extend(indirectas)
    if opciones:
        mejor = min(opciones, key=lambda r: float(r["tiempo_efectivo"]))
        return {
            "alcanzable": True,
            "tramo_id": mejor["tramo_id"],
            "distancia_km": round(float(mejor["distancia_km"]), 1),
            "eta_min": round(float(mejor["tiempo_efectivo"]), 1),
            "eta_margen_min": round(
                float(mejor["incertidumbre_min"]) * (1.5 if mejor["estado_via"] == "demora" else 1.0),
                1,
            ),
            "estado_via": mejor["estado_via"],
        }
    tramo = directa["tramo_id"] if directa is not None else "desconocido"
    return {
        "alcanzable": False,
        "tramo_id": tramo,
        "distancia_km": round(float(directa["distancia_km"]), 1) if directa else 0.0,
        "eta_min": 0.0,
        "eta_margen_min": 0.0,
        "estado_via": "bloqueo",
    }


class GraphRepository:
    """Acceso aislado a Neo4j: topología vial, especialidades, equipos y protocolos de trauma."""

    def __init__(self, clients: DatabaseClients) -> None:
        self._clients = clients

    def ping(self) -> bool:
        try:
            with self._clients.neo4j_driver.session() as session:
                rec = session.run(Q_PING).single()
                return rec is not None and rec["ok"] == 1
        except Exception:
            return False

    def get_protocol_requirements(self, protocolo_codigo: str) -> dict[str, Any] | None:
        try:
            with self._clients.neo4j_driver.session() as session:
                rec = session.run(Q_PROTOCOLO, codigo=protocolo_codigo).single()
                if rec is None:
                    return None
                return {
                    "codigo": rec["codigo"],
                    "nombre": rec["nombre"],
                    "tipo_incidente": rec["tipo_incidente"],
                    "recurso_critico": rec["recurso_critico"],
                    "especialidades_requeridas": rec["especialidades_requeridas"],
                    "equipos_requeridos": [e for e in rec["equipos_requeridos"] if e is not None],
                }
        except Neo4jError as exc:
            raise GraphUnavailableError(f"Error consultando protocolo en Neo4j: {exc}") from exc
        except Exception as exc:
            raise GraphUnavailableError(f"Neo4j no disponible al consultar protocolo: {exc}") from exc

    def evaluate_hospitals_for_protocol(
        self,
        *,
        protocolo_codigo: str,
        origen_zona: str | None = None,
        origen_hospital_id: int | None = None,
        demora_factor: float = 1.35,
    ) -> dict[str, Any]:
        """Evalúa todos los hospitales del corredor para un protocolo y ordena los compatibles por ETA."""
        protocolo = self.get_protocol_requirements(protocolo_codigo)
        if protocolo is None:
            raise NotFoundError(f"Protocolo de trauma '{protocolo_codigo}' no existe en el grafo.")

        try:
            with self._clients.neo4j_driver.session() as session:
                hospitales = session.run(Q_HOSPITALES_CAPACIDADES).data()

                anchor_id = origen_hospital_id
                if anchor_id is None and origen_zona:
                    rec = session.run(Q_ANCHOR_POR_ZONA, zona=origen_zona).single()
                    if rec is not None:
                        anchor_id = int(rec["hospital_id"])
                if anchor_id is None and hospitales:
                    anchor_id = int(hospitales[0]["hospital_id"])

                rutas_por_hosp: dict[int, dict[str, Any]] = {}
                if anchor_id is not None:
                    # Origen mismo: tiempo mínimo local de arribo (cumple CHECK eta_min > 0)
                    anchor_zona = next(
                        (h["zona"] for h in hospitales if h["hospital_id"] == anchor_id),
                        origen_zona or "tuxtla",
                    )
                    rutas_por_hosp[anchor_id] = {
                        "alcanzable": True,
                        "tramo_id": f"T-LOCAL-{anchor_zona}",
                        "distancia_km": 2.0,
                        "eta_min": 5.0 if origen_hospital_id is not None else 8.0,
                        "eta_margen_min": 3.0,
                        "estado_via": "normal",
                    }
                    rutas_raw = session.run(
                        Q_RUTAS_DESDE_HOSPITAL,
                        origen_id=anchor_id,
                        demora_factor=float(demora_factor),
                    ).data()
                    for row in rutas_raw:
                        rutas_por_hosp[int(row["hospital_id"])] = _select_best_route(
                            row["directa"], row["indirectas"]
                        )
        except Neo4jError as exc:
            raise GraphUnavailableError(f"Error ejecutando consulta de rutas en Neo4j: {exc}") from exc
        except Exception as exc:
            raise GraphUnavailableError(f"Neo4j no disponible durante evaluación de red: {exc}") from exc

        compatibles: list[dict[str, Any]] = []
        descartados: list[dict[str, Any]] = []

        for h in hospitales:
            hid = int(h["hospital_id"])
            cumple, motivos, esp_guardia = _check_protocol_match(h, protocolo)
            ruta = rutas_por_hosp.get(
                hid,
                {
                    "alcanzable": False,
                    "tramo_id": "desconocido",
                    "distancia_km": 0.0,
                    "eta_min": 0.0,
                    "eta_margen_min": 0.0,
                    "estado_via": "bloqueo",
                },
            )
            if not ruta["alcanzable"]:
                motivos.append(f"Ruta bloqueada sin alternativa vial disponible (tramo {ruta['tramo_id']})")

            entry = {
                "hospital_id": hid,
                "nombre": h["nombre"],
                "zona": h["zona"],
                "especialidades_hospital": h["especialidades"],
                "equipos_operativos": h["equipos_operativos"],
                "especialidades_para_guardia": esp_guardia,
                "tramo_id": ruta["tramo_id"],
                "distancia_km": ruta["distancia_km"],
                "eta_min": ruta["eta_min"],
                "eta_margen_min": ruta["eta_margen_min"],
                "estado_via": ruta["estado_via"],
                "motivos_descarte": motivos,
            }
            if cumple and ruta["alcanzable"]:
                compatibles.append(entry)
            else:
                descartados.append(entry)

        compatibles.sort(key=lambda item: (item["eta_min"], item["hospital_id"]))
        return {
            "protocolo": protocolo,
            "origen_anchor_id": anchor_id,
            "compatibles": compatibles,
            "descartados": descartados,
        }

    def get_network_topology(self) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
        try:
            with self._clients.neo4j_driver.session() as session:
                hospitales = session.run(Q_HOSPITALES_CAPACIDADES).data()
                edges = session.run(Q_NETWORK_EDGES).data()
        except Exception as exc:
            raise GraphUnavailableError(f"Error leyendo topología de Neo4j: {exc}") from exc

        edges_by_origin: dict[int, list[dict[str, Any]]] = {}
        for e in edges:
            edges_by_origin.setdefault(int(e["origen_id"]), []).append(
                {
                    "destino_hospital_id": int(e["destino_id"]),
                    "destino_nombre": e["destino_nombre"],
                    "tramo_id": e["tramo_id"],
                    "distancia_km": float(e["distancia_km"]),
                    "tiempo_min": float(e["tiempo_min"]),
                    "incertidumbre_min": float(e["incertidumbre_min"]),
                    "estado_via": e["estado_via"],
                }
            )
        return hospitales, edges_by_origin

    def update_tramo_estado(self, tramo_id: str, estado_via: str) -> int:
        try:
            with self._clients.neo4j_driver.session() as session:
                rec = session.run(
                    Q_UPDATE_TRAMO, tramo_id=tramo_id, estado_via=estado_via
                ).single()
                return int(rec["actualizadas"]) if rec else 0
        except Exception as exc:
            raise GraphUnavailableError(f"Error actualizando estado de tramo en Neo4j: {exc}") from exc
