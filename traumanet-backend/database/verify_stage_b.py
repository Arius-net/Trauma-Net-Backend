"""Verificación de la Etapa B: arranque, poblado, integridad y consistencia entre bases.
Uso:  python 08_APPLICATION/database/verify_stage_b.py   (requiere haber cargado las tres bases)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pg8000.dbapi as pg  # noqa: E402
from bson import ObjectId  # noqa: E402
from common import mongo_db, neo4j_driver, pg_connect  # noqa: E402
from pymongo.errors import WriteError  # noqa: E402

resultados: list[tuple[str, bool, str]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    resultados.append((nombre, ok, detalle))
    print(f"[{'OK' if ok else 'FALLO'}] {nombre} {detalle}")


def pg_sqlstate(exc: Exception) -> str | None:
    if exc.args and isinstance(exc.args[0], dict):
        return exc.args[0].get("C")
    return None


def main() -> int:
    # --- Relacional
    with pg_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT hospital_id, nombre FROM hospitales")
        ids_pg = {r[0]: r[1] for r in cur.fetchall()}
        check("pg: 8 hospitales", len(ids_pg) == 8, f"({len(ids_pg)})")

        tabs = ["recursos_hospitalarios", "ambulancias", "personal_guardia", "traslados", "reservas_recurso", "usuarios"]
        for t in tabs:
            cur.execute(f"SELECT count(*) FROM {t}")  # nombre de tabla fijo de esta lista blanca
            n = cur.fetchone()[0]
            check(f"pg: {t} poblada", n > 0, f"({n})")

        try:
            cur.execute("UPDATE recursos_hospitalarios SET ocupados = total + 1 WHERE recurso_id = %s", (11,))
            conn.commit()
            check("pg: CHECK rechaza disponibles negativos", False)
        except pg.DatabaseError as exc:
            conn.rollback()
            check("pg: CHECK rechaza disponibles negativos", pg_sqlstate(exc) == "23514", f"(SQLSTATE={pg_sqlstate(exc)})")

        cur.execute(
            """SELECT count(*) FROM recursos_hospitalarios r
               WHERE r.reservados <> COALESCE((SELECT sum(cantidad) FROM reservas_recurso s
                     WHERE s.recurso_id = r.recurso_id AND s.estado IN ('activa','confirmada')), 0)"""
        )
        desajuste = cur.fetchone()[0]
        check("pg: reservados == reservas vivas", desajuste == 0)

        cur.execute("SELECT frap_id FROM traslados")
        frap_ids = {r[0] for r in cur.fetchall()}
        cur.close()

    # --- Documental
    client, db = mongo_db()
    try:
        n = db["fraps"].count_documents({})
        check("mongo: 8 FRAP sintéticos", n == 8, f"({n})")
        tipos = set(db["fraps"].distinct("tipo_incidente"))
        check("mongo: 4 perfiles clínicos presentes", len(tipos) == 4, f"({sorted(tipos)})")
        try:
            db["fraps"].insert_one({"_id": ObjectId(), "tipo_incidente": "politrauma"})
            check("mongo: validador rechaza FRAP malformado", False)
        except WriteError as exc:
            check("mongo: validador rechaza FRAP malformado", exc.code == 121)
        existentes = {str(d["_id"]) for d in db["fraps"].find({}, {"_id": 1})}
        check("consistencia: traslados.frap_id existen en Mongo", frap_ids <= existentes)
        destinos = {d["hospital_destino_id"] for d in db["fraps"].find({"hospital_destino_id": {"$exists": True}})}
        check("consistencia: hospital_destino_id de FRAP existe en pg", destinos <= set(ids_pg))
    finally:
        client.close()

    # --- Grafo
    driver = neo4j_driver()
    try:
        with driver.session() as s:
            filas = s.run("MATCH (h:Hospital) RETURN h.hospital_id AS id, h.nombre AS nombre").data()
            check("neo4j: 8 hospitales", len(filas) == 8, f"({len(filas)})")
            check("consistencia: hospital_id y nombre iguales en pg y neo4j",
                  {f["id"]: f["nombre"] for f in filas} == ids_pg)
            aristas = s.run("MATCH ()-[c:CONECTADO_CON]->() RETURN count(c) AS n").single()["n"]
            check("neo4j: red completa dirigida (56 aristas)", aristas == 56, f"({aristas})")
            malas = s.run("MATCH ()-[c:CONECTADO_CON]->() WHERE NOT c.tiempo_min > 0 OR NOT c.distancia_km > 0 "
                          "OR NOT c.estado_via IN ['normal','demora','bloqueo'] RETURN count(c) AS n").single()["n"]
            check("neo4j: aristas con pesos y estado válidos", malas == 0)
            compat = s.run(
                """MATCH (p:ProtocoloTrauma {codigo: $codigo})-[:REQUIERE_EQUIPO]->(q:EquipoBiomedico)
                   WITH p, collect(q) AS req
                   MATCH (h:Hospital) WHERE all(x IN req WHERE (h)-[:TIENE_EQUIPO {operativo: true}]->(x))
                   RETURN count(h) AS n""", codigo="PT-TCE").single()["n"]
            check("neo4j: consulta de compatibilidad (PT-TCE por equipo → 2 hospitales)", compat == 2, f"({compat})")
    finally:
        driver.close()

    fallos = [r for r in resultados if not r[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} verificaciones OK")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
