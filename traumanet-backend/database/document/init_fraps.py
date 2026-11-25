"""Crea la colección `fraps` con validador $jsonSchema y carga FRAP sintéticos (idempotente: recrea la colección).

Fuente del esquema: fraps_schema.json (copia de D01 `fraps_json_schema.json`), convertido a $jsonSchema de MongoDB.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import mongo_db  # noqa: E402

SCHEMA_FILE = Path(__file__).with_name("fraps_schema.json")
DATE_PREFIX = r"^\d{4}-\d{2}-\d{2}T"


def to_mongo_schema(node, in_properties: bool = False):
    """Traduce el subconjunto portable de JSON Schema (D01) a $jsonSchema de MongoDB."""
    if isinstance(node, list):
        return [to_mongo_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    if in_properties:  # mapa nombre_de_campo -> esquema
        return {k: to_mongo_schema(v) for k, v in node.items()}
    out = {}
    for key, value in node.items():
        if key in ("$comment", "title"):
            continue
        if key == "properties":
            out[key] = to_mongo_schema(value, in_properties=True)
        else:
            out[key] = to_mongo_schema(value)
    if out.get("type") == "integer":
        del out["type"]
        out["bsonType"] = ["int", "long"]
    elif out.get("type") == "string" and str(out.get("pattern", "")).startswith(DATE_PREFIX):
        out.pop("type")
        out.pop("pattern")
        out["bsonType"] = "date"
    return out


def build_validator() -> dict:
    schema = to_mongo_schema(json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))
    schema["properties"]["_id"] = {"bsonType": "objectId"}
    return {"$jsonSchema": schema}


# ---------------------------------------------------------------- datos sintéticos
T0 = datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc)


def oid(n: int) -> ObjectId:
    return ObjectId(f"65f0{n:020d}")  # coincide con traslados.frap_id del seed relacional


def vitals(minute: int, fc, fr, sis, dia, spo2):
    return {"medido_en": T0 + timedelta(minutes=minute), "fc": fc, "fr": fr,
            "ta_sistolica": sis, "ta_diastolica": dia, "spo2": spo2}


PERFILES = {
    "politrauma": {"tipo": "politrauma", "mecanismo_lesion": "colision_vehicular",
                   "lesiones": [{"region": "torax", "tipo_lesion": "contusion pulmonar", "ais": 3},
                                {"region": "abdomen", "tipo_lesion": "laceracion hepatica", "ais": 4}],
                   "hemorragia_activa": True, "torniquete_aplicado": False,
                   "requiere_quirofano_sospechado": True, "iss_estimado": 25},
    "infarto": {"tipo": "infarto_agudo",
                "ecg": {"elevacion_st": True, "derivaciones_afectadas": ["II", "III", "aVF"], "ritmo": "sinusal"},
                "killip": 2, "inicio_dolor_min": 90, "trombolisis_aplicada": False,
                "troponina_rapida_positiva": True},
    "tce": {"tipo": "trauma_craneoencefalico",
            "glasgow": {"ocular": 2, "verbal": 2, "motor": 4, "total": 8},
            "pupilas": {"izquierda_mm": 5.0, "derecha_mm": 3.0, "reactivas": False},
            "signos_herniacion": True, "via_aerea_asegurada": True, "anticoagulado": False, "convulsiones": False},
    "quemadura": {"tipo": "intoxicacion_quemaduras", "subtipo": "quemadura", "sct_quemada_pct": 35.5,
                  "grado_quemadura": "2", "lesion_inhalatoria": True, "via_aerea_comprometida": True,
                  "descontaminacion_realizada": False},
    "intoxicacion": {"tipo": "intoxicacion_quemaduras", "subtipo": "intoxicacion", "agente": "organofosforado",
                     "via_exposicion": "oral", "via_aerea_comprometida": False,
                     "descontaminacion_realizada": True, "antidoto_aplicado": "atropina"},
}

# (n, tipo_incidente, protocolo, estado, perfil, triage, municipio, lat, lon, extras)
SEMILLAS = [
    (1, "politrauma", "PT-POLITRAUMA", "asignado", "politrauma", "rojo", "Chiapa de Corzo", 16.70, -93.01,
     {"hospital_destino_id": 1, "ambulancia_id": 1, "traslado_id": "a0000000-0000-4000-8000-000000000001"}),
    (2, "infarto_agudo", "PT-IAM", "asignado", "infarto", "rojo", "Tuxtla Gutiérrez", 16.75, -93.12,
     {"hospital_destino_id": 2, "ambulancia_id": 3, "traslado_id": "a0000000-0000-4000-8000-000000000002"}),
    (3, "politrauma", "PT-POLITRAUMA", "reportado", "politrauma", "rojo", "Teopisca", 16.54, -92.47, {}),
    (4, "infarto_agudo", "PT-IAM", "reportado", "infarto", "amarillo", "San Cristóbal de Las Casas", 16.74, -92.64, {}),
    (5, "trauma_craneoencefalico", "PT-TCE", "evaluando", "tce", "rojo", "Comitán de Domínguez", 16.25, -92.13, {}),
    (6, "trauma_craneoencefalico", "PT-TCE", "sin_asignacion", "tce", "rojo", "Comitán de Domínguez", 16.26, -92.14,
     {"motivo_sin_asignacion": "sin cama UCI compatible al momento de la evaluacion (dato sintetico)"}),
    (7, "intoxicacion_quemaduras", "PT-INTOX-QUEM", "reportado", "intoxicacion", "amarillo", "Tuxtla Gutiérrez", 16.76, -93.10, {}),
    (8, "intoxicacion_quemaduras", "PT-INTOX-QUEM", "reportado", "quemadura", "rojo", "San Cristóbal de Las Casas", 16.73, -92.65, {}),
]


def build_docs() -> list[dict]:
    docs = []
    for n, tipo, prot, estado, perfil, nivel, muni, lat, lon, extra in SEMILLAS:
        doc = {
            "_id": oid(n), "schema_version": "1.0", "tipo_incidente": tipo, "estado_frap": estado,
            "creado_en": T0 + timedelta(minutes=n), "actualizado_en": T0 + timedelta(minutes=n + 1),
            "paciente_sintetico": {"id_sintetico": f"SYN-{n:06d}", "sexo": "F" if n % 2 else "M",
                                   "grupo_edad": ["adulto", "adulto_mayor", "pediatrico"][n % 3]},
            "ubicacion_escena": {"municipio": muni, "latitud": lat, "longitud": lon},
            "triage": {"nivel": nivel, "evaluado_en": T0 + timedelta(minutes=n), "observaciones": "dato sintetico"},
            "protocolo_codigo": prot,
            "signos_vitales": [vitals(n, 118, 24, 95, 60, 91), vitals(n + 6, 112, 22, 100, 64, 94)],
            "medicamentos_aplicados": [{"nombre": "solucion salina", "dosis": "500 ml", "via": "iv",
                                        "aplicado_en": T0 + timedelta(minutes=n + 3)}],
            "notas": "FRAP sintetico para pruebas",
            "perfil": PERFILES[perfil],
        }
        doc.update(extra)
        docs.append(doc)
    return docs


def main() -> None:
    client, db = mongo_db()
    try:
        if "fraps" in db.list_collection_names():
            db.drop_collection("fraps")
        db.create_collection("fraps", validator=build_validator(),
                             validationLevel="strict", validationAction="error")
        col = db["fraps"]
        col.create_index([("estado_frap", 1), ("creado_en", -1)], name="ix_estado_creado")
        col.create_index([("tipo_incidente", 1)], name="ix_tipo")
        col.create_index([("traslado_id", 1)], name="ux_traslado", unique=True,
                         partialFilterExpression={"traslado_id": {"$type": "string"}})
        res = col.insert_many(build_docs())
        print(f"[mongo] fraps creada con validador; {len(res.inserted_ids)} FRAP sinteticos cargados")
    finally:
        client.close()


if __name__ == "__main__":
    main()
