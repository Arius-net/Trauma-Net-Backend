"""Carga el grafo del corredor Tuxtla – San Cristóbal – Comitán (idempotente, MERGE).

Los hospitales (hospital_id, nombre) se leen de PostgreSQL, fuente de verdad (R-03).
Toda consulta Cypher es estática y recibe los datos como parámetros ($rows).
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import neo4j_driver, pg_connect  # noqa: E402

ZONA_POR_MUNICIPIO = {
    "Tuxtla Gutiérrez": "tuxtla",
    "San Cristóbal de Las Casas": "san_cristobal",
    "Comitán de Domínguez": "comitan",
}

ESPECIALIDADES = {
    "CIRUGIA_TRAUMA": "Cirugía de trauma", "ANESTESIOLOGIA": "Anestesiología",
    "MEDICINA_CRITICA": "Medicina crítica", "NEUROCIRUGIA": "Neurocirugía",
    "CARDIOLOGIA_INTERVENCIONISTA": "Cardiología intervencionista", "TOXICOLOGIA": "Toxicología",
    "CIRUGIA_PLASTICA": "Cirugía plástica",
}
EQUIPOS = {
    "TAC": "Tomógrafo", "BANCO_SANGRE": "Banco de sangre", "QUIROFANO_TRAUMA": "Quirófano de trauma",
    "QUIROFANO_NEURO": "Quirófano de neurocirugía", "HEMODINAMIA": "Sala de hemodinamia",
    "ECG": "Electrocardiógrafo", "DESFIBRILADOR": "Desfibrilador", "VENTILADOR": "Ventilador mecánico",
    "UNIDAD_QUEMADOS": "Unidad de quemados",
}
PROTOCOLOS = {
    "PT-POLITRAUMA": ("Protocolo de politrauma", "politrauma", "quirofano"),
    "PT-IAM": ("Protocolo de infarto agudo", "infarto_agudo", "cama_uci"),
    "PT-TCE": ("Protocolo de TCE", "trauma_craneoencefalico", "cama_uci"),
    "PT-INTOX-QUEM": ("Protocolo de intoxicación/quemaduras", "intoxicacion_quemaduras", "sala_choque"),
}
# (protocolo, especialidad, grupo_alternativa) — con grupo, basta cumplir una del grupo (A-10)
REQ_ESP = [
    ("PT-POLITRAUMA", "CIRUGIA_TRAUMA", None), ("PT-POLITRAUMA", "ANESTESIOLOGIA", None),
    ("PT-POLITRAUMA", "MEDICINA_CRITICA", None),
    ("PT-IAM", "CARDIOLOGIA_INTERVENCIONISTA", None), ("PT-IAM", "MEDICINA_CRITICA", None),
    ("PT-TCE", "NEUROCIRUGIA", None), ("PT-TCE", "ANESTESIOLOGIA", None),
    ("PT-INTOX-QUEM", "TOXICOLOGIA", "TOX_O_PLAST"), ("PT-INTOX-QUEM", "CIRUGIA_PLASTICA", "TOX_O_PLAST"),
    ("PT-INTOX-QUEM", "MEDICINA_CRITICA", None),
]
REQ_EQ = [
    ("PT-POLITRAUMA", "TAC"), ("PT-POLITRAUMA", "BANCO_SANGRE"), ("PT-POLITRAUMA", "QUIROFANO_TRAUMA"),
    ("PT-IAM", "HEMODINAMIA"), ("PT-IAM", "ECG"), ("PT-IAM", "DESFIBRILADOR"),
    ("PT-TCE", "TAC"), ("PT-TCE", "QUIROFANO_NEURO"), ("PT-TCE", "VENTILADOR"),
    ("PT-INTOX-QUEM", "UNIDAD_QUEMADOS"), ("PT-INTOX-QUEM", "VENTILADOR"),
]
CUENTA_CON = {  # especialidad -> hospitales (tabla de capacidades sintéticas de D01)
    "CIRUGIA_TRAUMA": [1, 2, 3, 4, 5, 6, 7], "ANESTESIOLOGIA": [1, 2, 3, 4, 5, 6, 7, 8],
    "MEDICINA_CRITICA": [1, 2, 3, 4, 5], "NEUROCIRUGIA": [1, 2],
    "CARDIOLOGIA_INTERVENCIONISTA": [1, 2, 3], "TOXICOLOGIA": [1, 3, 5], "CIRUGIA_PLASTICA": [1],
}
TIENE_EQUIPO = {
    "TAC": [1, 2, 3, 4, 5, 7], "BANCO_SANGRE": [1, 2, 3, 4, 5, 6, 7, 8],
    "QUIROFANO_TRAUMA": [1, 2, 3, 4, 5, 6, 7], "QUIROFANO_NEURO": [1, 2], "HEMODINAMIA": [1, 2, 3],
    "ECG": list(range(1, 9)), "DESFIBRILADOR": list(range(1, 9)), "VENTILADOR": list(range(1, 9)),
    "UNIDAD_QUEMADOS": [1],
}
# Tramos entre zonas: (distancia_km, tiempo_min, incertidumbre_min). Aproximados (A-05).
TRAMOS = {
    frozenset(("tuxtla", "san_cristobal")): ("T-TUX-SCLC", 85.0, 70.0, 15.0),
    frozenset(("san_cristobal", "comitan")): ("T-SCLC-COM", 90.0, 85.0, 20.0),
    frozenset(("tuxtla", "comitan")): ("T-TUX-COM", 160.0, 140.0, 25.0),
}
DESFASE_MIN = {1: 0, 2: 2, 3: 4, 4: 3, 5: 0, 6: 3, 7: 0, 8: 2}  # desfase intraurbano fijo por hospital


def build_edges(hospitales: list[dict]) -> list[dict]:
    ahora = datetime.now(timezone.utc).isoformat()
    edges = []
    for a in hospitales:
        for b in hospitales:
            if a["hospital_id"] == b["hospital_id"]:
                continue
            ia, ib = a["hospital_id"], b["hospital_id"]
            if a["zona"] == b["zona"]:
                tiempo = 6.0 + 2.0 * ((ia * ib) % 7)
                edge = (f"T-LOCAL-{a['zona']}", round(tiempo * 0.45, 1), tiempo, 3.0)
            else:
                tramo, km, minutos, inc = TRAMOS[frozenset((a["zona"], b["zona"]))]
                extra = DESFASE_MIN[ia] + DESFASE_MIN[ib]
                edge = (tramo, km + extra * 0.5, minutos + extra, inc)
            edges.append({"a": ia, "b": ib, "tramo_id": edge[0], "distancia_km": edge[1],
                          "tiempo_min": edge[2], "incertidumbre_min": edge[3], "actualizado_en": ahora})
    return edges


Q_HOSPITAL = ("UNWIND $rows AS r MERGE (h:Hospital {hospital_id: r.hospital_id}) "
              "SET h.nombre = r.nombre, h.zona = r.zona")
Q_ESP = "UNWIND $rows AS r MERGE (e:Especialidad {codigo: r.codigo}) SET e.nombre = r.nombre"
Q_EQ = "UNWIND $rows AS r MERGE (q:EquipoBiomedico {codigo: r.codigo}) SET q.nombre = r.nombre"
Q_PROT = ("UNWIND $rows AS r MERGE (p:ProtocoloTrauma {codigo: r.codigo}) "
          "SET p.nombre = r.nombre, p.tipo_incidente = r.tipo_incidente, p.recurso_critico = r.recurso_critico")
Q_CUENTA = ("UNWIND $rows AS r MATCH (h:Hospital {hospital_id: r.h}) MATCH (e:Especialidad {codigo: r.e}) "
            "MERGE (h)-[c:CUENTA_CON]->(e) SET c.guardia_24h = r.g24")
Q_TIENE = ("UNWIND $rows AS r MATCH (h:Hospital {hospital_id: r.h}) MATCH (q:EquipoBiomedico {codigo: r.q}) "
           "MERGE (h)-[t:TIENE_EQUIPO]->(q) SET t.operativo = true")
Q_REQ_ESP = ("UNWIND $rows AS r MATCH (p:ProtocoloTrauma {codigo: r.p}) MATCH (e:Especialidad {codigo: r.e}) "
             "MERGE (p)-[x:REQUIERE_ESPECIALIDAD]->(e) SET x.obligatoria = true, x.grupo_alternativa = r.grupo")
Q_REQ_EQ = ("UNWIND $rows AS r MATCH (p:ProtocoloTrauma {codigo: r.p}) MATCH (q:EquipoBiomedico {codigo: r.q}) "
            "MERGE (p)-[x:REQUIERE_EQUIPO]->(q) SET x.obligatoria = true")
Q_CONECTADO = ("UNWIND $rows AS r MATCH (a:Hospital {hospital_id: r.a}) MATCH (b:Hospital {hospital_id: r.b}) "
               "MERGE (a)-[c:CONECTADO_CON]->(b) "
               "SET c.tramo_id = r.tramo_id, c.distancia_km = r.distancia_km, c.tiempo_min = r.tiempo_min, "
               "c.estado_via = 'normal', c.incertidumbre_min = r.incertidumbre_min, "
               "c.actualizado_en = datetime(r.actualizado_en)")


def leer_hospitales() -> list[dict]:
    with pg_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT hospital_id, nombre, municipio FROM hospitales ORDER BY hospital_id")
        rows = cur.fetchall()
        cur.close()
    return [{"hospital_id": i, "nombre": n, "zona": ZONA_POR_MUNICIPIO[m]} for i, n, m in rows]


def main() -> None:
    hospitales = leer_hospitales()
    if not hospitales:
        raise SystemExit("PostgreSQL no tiene hospitales: cargue primero la base relacional")
    statements = [s.strip() for s in (Path(__file__).with_name("01_constraints.cypher")).read_text(encoding="utf-8").split(";") if s.strip()]
    loads = [
        (Q_HOSPITAL, hospitales),
        (Q_ESP, [{"codigo": c, "nombre": n} for c, n in ESPECIALIDADES.items()]),
        (Q_EQ, [{"codigo": c, "nombre": n} for c, n in EQUIPOS.items()]),
        (Q_PROT, [{"codigo": c, "nombre": n, "tipo_incidente": t, "recurso_critico": rc}
                  for c, (n, t, rc) in PROTOCOLOS.items()]),
        (Q_CUENTA, [{"h": h, "e": e, "g24": True} for e, hs in CUENTA_CON.items() for h in hs]),
        (Q_TIENE, [{"h": h, "q": q} for q, hs in TIENE_EQUIPO.items() for h in hs]),
        (Q_REQ_ESP, [{"p": p, "e": e, "grupo": g} for p, e, g in REQ_ESP]),
        (Q_REQ_EQ, [{"p": p, "q": q} for p, q in REQ_EQ]),
        (Q_CONECTADO, build_edges(hospitales)),
    ]
    driver = neo4j_driver()
    try:
        with driver.session() as session:
            for stmt in statements:
                session.run(stmt).consume()
            for query, rows in loads:
                session.run(query, rows=rows).consume()
        print(f"[neo4j] constraints creadas; {len(hospitales)} hospitales y su red cargados")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
