"""Fixtures compartidas para la suite Pytest de TraumaNet (Etapa D)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.dependencies import ServiceContainer
from app.main import create_app


@pytest.fixture(scope="session")
def app():
    application = create_app()
    application.state.container.startup()
    yield application
    application.state.container.shutdown()


@pytest.fixture(scope="session")
def client(app) -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(client: TestClient) -> dict[str, dict[str, str]]:
    """Obtiene tokens JWT reales vía POST /api/v1/auth/login para los 3 roles sintéticos."""
    credentials = {
        "CRUM": ("crum_sintetico_01", "TraumaCrum2026!"),
        "PARAMEDICO": ("paramedico_sint_01", "TraumaParam2026!"),
        "JEFE_H1": ("jefe_urg_h1", "TraumaJefe2026!"),
        "JEFE_H5": ("jefe_urg_h5", "TraumaJefe2026!"),
    }
    headers: dict[str, dict[str, str]] = {}
    for key, (username, password) in credentials.items():
        resp = client.post(
            "/api/v1/auth/login",
            json={"nombre_usuario": username, "password": password},
        )
        assert resp.status_code == 200, f"Login falló para {username}: {resp.text}"
        token = resp.json()["access_token"]
        headers[key] = {"Authorization": f"Bearer {token}"}
    return headers


@pytest.fixture(scope="session")
def container(app) -> ServiceContainer:
    return app.state.container


@pytest.fixture
def cleanup_registry(container: ServiceContainer):
    """Limpia FRAPs, traslados y reservas sintéticas creadas por cada prueba y restaura contadores."""
    frap_ids: list[str] = []
    yield frap_ids

    if not frap_ids:
        return

    with container.clients.pg_connection() as conn:
        cur = conn.cursor()
        try:
            for fid in frap_ids:
                cur.execute(
                    """SELECT r.reserva_id, r.recurso_id, r.cantidad, r.estado, t.traslado_id
                       FROM traslados t
                       LEFT JOIN reservas_recurso r ON r.traslado_id = t.traslado_id
                       WHERE t.frap_id = %s""",
                    (fid,),
                )
                rows = cur.fetchall()
                for reserva_id, recurso_id, cantidad, estado, traslado_id in rows:
                    if reserva_id is not None:
                        if estado in ("activa", "confirmada") and recurso_id is not None:
                            cur.execute(
                                """UPDATE recursos_hospitalarios
                                   SET reservados = GREATEST(reservados - %s, 0)
                                   WHERE recurso_id = %s""",
                                (cantidad, recurso_id),
                            )
                        cur.execute(
                            "DELETE FROM reservas_recurso WHERE reserva_id = %s",
                            (reserva_id,),
                        )
                cur.execute("DELETE FROM traslados WHERE frap_id = %s", (fid,))
            conn.commit()
        finally:
            cur.close()

    oids = [ObjectId(fid) for fid in frap_ids if ObjectId.is_valid(fid)]
    if oids:
        container.clients.mongo_db["fraps"].delete_many({"_id": {"$in": oids}})


def make_frap_payload(
    *,
    tipo_incidente: str = "politrauma",
    municipio: str = "San Cristóbal de Las Casas",
    lat: float = 16.737,
    lon: float = -92.638,
    syn_id: str = "SYN-900001",
    ambulancia_id: int | None = 6,
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    base: dict[str, Any] = {
        "schema_version": "1.0",
        "tipo_incidente": tipo_incidente,
        "paciente_sintetico": {
            "id_sintetico": syn_id,
            "sexo": "M",
            "grupo_edad": "adulto",
        },
        "ubicacion_escena": {
            "municipio": municipio,
            "latitud": lat,
            "longitud": lon,
            "referencia": "Dato sintético de prueba automatizada",
        },
        "triage": {
            "nivel": "rojo",
            "evaluado_en": now_iso,
            "observaciones": "Prueba automatizada (sin PHI)",
        },
        "signos_vitales": [
            {
                "medido_en": now_iso,
                "fc": 122,
                "fr": 26,
                "ta_sistolica": 88,
                "ta_diastolica": 54,
                "spo2": 90,
            }
        ],
        "notas": "Registro sintético generado por Pytest",
    }
    if ambulancia_id is not None:
        base["ambulancia_id"] = ambulancia_id

    if tipo_incidente == "politrauma":
        base["protocolo_codigo"] = "PT-POLITRAUMA"
        base["perfil"] = {
            "tipo": "politrauma",
            "mecanismo_lesion": "colision_vehicular",
            "lesiones": [
                {"region": "torax", "tipo_lesion": "neumotorax", "ais": 4},
                {"region": "abdomen", "tipo_lesion": "trauma cerrado", "ais": 3},
            ],
            "hemorragia_activa": True,
            "requiere_quirofano_sospechado": True,
            "iss_estimado": 25,
        }
    elif tipo_incidente == "infarto_agudo":
        base["protocolo_codigo"] = "PT-IAM"
        base["perfil"] = {
            "tipo": "infarto_agudo",
            "ecg": {
                "elevacion_st": True,
                "derivaciones_afectadas": ["V1", "V2", "V3", "V4"],
                "ritmo": "sinusal",
            },
            "killip": 2,
            "inicio_dolor_min": 65,
            "troponina_rapida_positiva": True,
        }
    elif tipo_incidente == "trauma_craneoencefalico":
        base["protocolo_codigo"] = "PT-TCE"
        base["perfil"] = {
            "tipo": "trauma_craneoencefalico",
            "glasgow": {"ocular": 2, "verbal": 2, "motor": 4, "total": 8},
            "pupilas": {"izquierda_mm": 5.0, "derecha_mm": 3.0, "reactivas": False},
            "signos_herniacion": True,
            "via_aerea_asegurada": True,
        }
    elif tipo_incidente == "intoxicacion_quemaduras":
        base["protocolo_codigo"] = "PT-INTOX-QUEM"
        base["perfil"] = {
            "tipo": "intoxicacion_quemaduras",
            "subtipo": "quemadura",
            "sct_quemada_pct": 32.0,
            "grado_quemadura": "2",
            "lesion_inhalatoria": True,
            "via_aerea_comprometida": True,
        }
    else:
        raise ValueError(f"tipo_incidente no soportado: {tipo_incidente}")
    return base
