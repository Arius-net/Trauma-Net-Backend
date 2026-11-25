"""Pruebas de integridad por modelo (PostgreSQL, MongoDB y Neo4j) autenticadas con JWT."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import ServiceContainer
from app.core.exceptions import DocumentValidationError
from tests.conftest import make_frap_payload


def test_relational_rejects_negative_disponibles_via_check_constraint(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    resp = client.put(
        "/api/v1/hospitals/1/capacity",
        headers=auth_headers["JEFE_H1"],
        json={"tipo_recurso": "cama_uci", "total": 12, "ocupados": 15},
    )
    assert resp.status_code == 409
    assert "CHECK" in resp.json()["detail"] or "negativo" in resp.json()["detail"]


def test_relational_ttl_expiration_releases_bed_and_cancels_traslado(
    client: TestClient,
    container: ServiceContainer,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    traslado_id = str(uuid.uuid4())
    reserva_id = str(uuid.uuid4())
    fake_frap_id = "65f099999999999999999901"

    with container.clients.pg_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute("SELECT reservados FROM recursos_hospitalarios WHERE recurso_id = %s", (31,))
            res_antes = int(cur.fetchone()[0])

            cur.execute(
                "UPDATE recursos_hospitalarios SET reservados = reservados + 1 WHERE recurso_id = %s",
                (31,),
            )
            cur.execute(
                """INSERT INTO traslados (
                       traslado_id, frap_id, hospital_destino_id, protocolo_codigo,
                       estado, eta_min, eta_margen_min, estado_via, data_vintage, solicitado_por
                   ) VALUES (%s, %s, 3, 'PT-IAM', 'reservado', 12.0, 3.0, 'normal', now(), 1)""",
                (traslado_id, fake_frap_id),
            )
            cur.execute(
                """INSERT INTO reservas_recurso (
                       reserva_id, traslado_id, recurso_id, cantidad, estado, creada_en, expira_en
                   ) VALUES (%s, %s, 31, 1, 'activa', now() - interval '20 minutes', now() - interval '5 minutes')""",
                (reserva_id, traslado_id),
            )
            conn.commit()
        finally:
            cur.close()

    try:
        resp = client.post(
            "/api/v1/reservas/expire-overdue",
            headers=auth_headers["CRUM"],
        )
        assert resp.status_code == 200
        assert resp.json()["reservas_expiradas"] >= 1

        with container.clients.pg_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT estado, cerrada_en FROM reservas_recurso WHERE reserva_id = %s", (reserva_id,))
            estado_res, cerrada_en = cur.fetchone()
            cur.execute("SELECT estado FROM traslados WHERE traslado_id = %s", (traslado_id,))
            estado_tras = cur.fetchone()[0]
            cur.execute("SELECT reservados FROM recursos_hospitalarios WHERE recurso_id = %s", (31,))
            res_despues = int(cur.fetchone()[0])
            cur.close()

        assert estado_res == "expirada"
        assert cerrada_en is not None
        assert estado_tras == "cancelado"
        assert res_despues == res_antes
    finally:
        with container.clients.pg_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM reservas_recurso WHERE reserva_id = %s", (reserva_id,))
            cur.execute("DELETE FROM traslados WHERE traslado_id = %s", (traslado_id,))
            conn.commit()
            cur.close()


def test_document_rejects_malformed_frap_in_mongo_and_api(
    client: TestClient,
    container: ServiceContainer,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    with pytest.raises(DocumentValidationError):
        container.document_repo.insert_frap({"tipo_incidente": "politrauma", "incompleto": True})

    bad_frap = make_frap_payload(tipo_incidente="politrauma", syn_id="SYN-900010")
    bad_frap["protocolo_codigo"] = "PT-IAM"
    resp = client.post(
        "/api/v1/dispatch/evaluate-and-assign",
        headers=auth_headers["PARAMEDICO"],
        json={"frap": bad_frap},
    )
    assert resp.status_code == 422

    bad_tce = make_frap_payload(tipo_incidente="trauma_craneoencefalico", syn_id="SYN-900011")
    bad_tce["perfil"]["glasgow"]["total"] = 15
    resp2 = client.post(
        "/api/v1/dispatch/evaluate-and-assign",
        headers=auth_headers["PARAMEDICO"],
        json={"frap": bad_tce},
    )
    assert resp2.status_code == 422


def test_document_accepts_all_four_clinical_profiles(
    container: ServiceContainer,
    cleanup_registry: list[str],
) -> None:
    from app.schemas.frap import FRAPCreate

    for idx, tipo in enumerate(
        ["politrauma", "infarto_agudo", "trauma_craneoencefalico", "intoxicacion_quemaduras"],
        start=1,
    ):
        payload = make_frap_payload(tipo_incidente=tipo, syn_id=f"SYN-90010{idx}")
        model = FRAPCreate.model_validate(payload)
        frap_id = container.document_repo.insert_frap(model.to_mongo_document())
        cleanup_registry.append(frap_id)
        stored = container.document_repo.get_frap_by_id(frap_id)
        assert stored is not None
        assert stored["tipo_incidente"] == tipo
        assert stored["perfil"]["tipo"] == tipo


def test_graph_connectivity_and_road_block_rerouting(
    client: TestClient,
    container: ServiceContainer,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    hospitals_pg = container.relational_repo.get_hospitals_map()
    hospitals_graph, edges = container.graph_repo.get_network_topology()
    assert len(hospitals_graph) == 8
    assert {h["hospital_id"]: h["nombre"] for h in hospitals_graph} == {
        hid: m["nombre"] for hid, m in hospitals_pg.items()
    }
    assert sum(len(v) for v in edges.values()) == 56

    try:
        r_blk = client.patch(
            "/api/v1/network/tramos/T-TUX-COM",
            headers=auth_headers["CRUM"],
            json={"estado_via": "bloqueo"},
        )
        assert r_blk.status_code == 200
        assert r_blk.json()["aristas_actualizadas"] > 0

        eval_res = container.graph_repo.evaluate_hospitals_for_protocol(
            protocolo_codigo="PT-TCE",
            origen_hospital_id=7,
        )
        h1 = next(c for c in eval_res["compatibles"] if c["hospital_id"] == 1)
        assert "T-TUX-COM" not in h1["tramo_id"]
        assert "T-SCLC-COM" in h1["tramo_id"] and "T-TUX-SCLC" in h1["tramo_id"]
    finally:
        client.patch(
            "/api/v1/network/tramos/T-TUX-COM",
            headers=auth_headers["CRUM"],
            json={"estado_via": "normal"},
        )
