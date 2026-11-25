"""Prueba E2E completa de la Decisión 1 y endpoints complementarios con autenticación JWT."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.dependencies import ServiceContainer
from tests.conftest import make_frap_payload


def test_e2e_decision_1_tce_discards_absent_guardia_and_assigns_hosp01(
    client: TestClient,
    container: ServiceContainer,
    cleanup_registry: list[str],
    auth_headers: dict[str, dict[str, str]],
) -> None:
    payload = {
        "frap": make_frap_payload(
            tipo_incidente="trauma_craneoencefalico",
            municipio="Comitán de Domínguez",
            lat=16.251,
            lon=-92.134,
            syn_id="SYN-E2E001",
            ambulancia_id=8,
        ),
        "origen_zona": "comitan",
    }

    resp = client.post(
        "/api/v1/dispatch/evaluate-and-assign",
        headers=auth_headers["PARAMEDICO"],
        json=payload,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    frap_id = body["frap_id"]
    cleanup_registry.append(frap_id)

    assert "apoya la decisión" in body["decision_support_notice"].lower()
    assert body["estado_despacho"] == "asignado"
    assert body["protocolo_codigo"] == "PT-TCE"
    assert body["recurso_critico"] == "cama_uci"
    assert body["data_vintage"] is not None
    assert body["data_vintage_segundos"] is not None
    assert body["incertidumbre_ruta"]["eta_base_min"] > 0
    assert body["incertidumbre_ruta"]["margen_min"] > 0
    assert body["incertidumbre_ruta"]["eta_maximo_min"] > body["incertidumbre_ruta"]["eta_minimo_min"]

    assert body["hospital_asignado"]["hospital_id"] == 1
    assert body["reserva"]["ttl_minutos"] == 15
    assert body["reserva"]["estado"] == "activa"

    descartados_by_id = {d["hospital_id"]: d["motivos_descarte"] for d in body["hospitales_descartados"]}
    assert 2 in descartados_by_id
    assert any("guardia" in m.lower() and "neurocirugia" in m.lower() for m in descartados_by_id[2])
    assert 7 in descartados_by_id

    # Expediente unificado (MongoDB + PostgreSQL)
    exp_resp = client.get(
        f"/api/v1/expedientes/{frap_id}",
        headers=auth_headers["CRUM"],
    )
    assert exp_resp.status_code == 200
    exp = exp_resp.json()
    assert exp["frap"]["estado_frap"] == "asignado"
    assert exp["frap"]["hospital_destino_id"] == 1
    assert exp["traslado"]["traslado_id"] == body["reserva"]["traslado_id"]
    assert exp["traslado"]["estado"] == "reservado"
    assert exp["traslado"]["reservas"][0]["reserva_id"] == body["reserva"]["reserva_id"]

    # Listado de reservas entrantes del hospital 1 para JEFE_URGENCIAS
    res_list = client.get(
        "/api/v1/hospitals/1/reservas",
        headers=auth_headers["JEFE_H1"],
    )
    assert res_list.status_code == 200
    assert any(r["reserva_id"] == body["reserva"]["reserva_id"] for r in res_list.json())

    # Confirmación de reserva por JEFE_URGENCIAS de H1
    conf_resp = client.post(
        f"/api/v1/reservas/{body['reserva']['reserva_id']}/confirm",
        headers=auth_headers["JEFE_H1"],
    )
    assert conf_resp.status_code == 200
    assert conf_resp.json()["estado_reserva"] == "confirmada"
    assert conf_resp.json()["estado_traslado"] == "confirmado"


def test_complementary_network_cascade_and_capacity_endpoints(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    net_resp = client.get("/api/v1/network/hospitals", headers=auth_headers["CRUM"])
    assert net_resp.status_code == 200
    net = net_resp.json()
    assert net["total_hospitales"] == 8
    assert all(len(h["recursos"]) == 3 for h in net["hospitales"])

    casc_resp = client.get(
        "/api/v1/network/cascade",
        params={"hospital_saturado_id": 1, "protocolo_codigo": "PT-IAM"},
        headers=auth_headers["CRUM"],
    )
    assert casc_resp.status_code == 200
    casc = casc_resp.json()
    assert casc["recurso_critico"] == "cama_uci"
    assert casc["data_vintage"] is not None
    vecinos_ids = [o["hospital_id"] for o in casc["opciones_derivacion"]]
    assert set(vecinos_ids) == {2, 3}

    cap_resp = client.get(
        "/api/v1/hospitals/5/capacity",
        headers=auth_headers["JEFE_H5"],
    )
    assert cap_resp.status_code == 200
    assert cap_resp.json()["hospital_id"] == 5
