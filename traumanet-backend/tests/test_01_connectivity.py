"""Pruebas de conectividad a los tres motores y autenticación/autorización JWT (D-0005 / Q-05)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.dependencies import ServiceContainer


def test_direct_engine_pings(container: ServiceContainer) -> None:
    assert container.relational_repo.ping() is True, "PostgreSQL no respondió"
    assert container.document_repo.ping() is True, "MongoDB no respondió"
    assert container.graph_repo.ping() is True, "Neo4j no respondió"


def test_health_endpoint_reports_all_three_engines_up(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["engines"] == {
        "postgresql": "up",
        "mongodb": "up",
        "neo4j": "up",
    }


def test_jwt_login_valid_and_me_profile(client: TestClient) -> None:
    # Login válido para los 3 roles
    for username, password, expected_role, expected_hosp in [
        ("crum_sintetico_01", "TraumaCrum2026!", "CRUM", None),
        ("paramedico_sint_01", "TraumaParam2026!", "PARAMEDICO", None),
        ("jefe_urg_h1", "TraumaJefe2026!", "JEFE_URGENCIAS", 1),
    ]:
        r_login = client.post(
            "/api/v1/auth/login",
            json={"nombre_usuario": username, "password": password},
        )
        assert r_login.status_code == 200
        body = r_login.json()
        assert body["token_type"] == "bearer"
        assert body["user"]["rol"] == expected_role
        assert body["user"]["hospital_id"] == expected_hosp

        r_me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert r_me.status_code == 200
        assert r_me.json()["nombre_usuario"] == username
        assert r_me.json()["rol"] == expected_role


def test_jwt_invalid_credentials_and_role_enforcement(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
) -> None:
    # Credenciales inválidas -> 401
    r_bad = client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "crum_sintetico_01", "password": "PasswordIncorrecta!"},
    )
    assert r_bad.status_code == 401

    # Sin token Bearer -> 401
    r_missing = client.get("/api/v1/network/hospitals")
    assert r_missing.status_code == 401

    # Intento de bypass con header legacy X-User-Role (retirado en D-0005) -> 401
    r_legacy = client.get("/api/v1/network/hospitals", headers={"X-User-Role": "CRUM"})
    assert r_legacy.status_code == 401

    # Token malformado -> 401
    r_tampered = client.get(
        "/api/v1/network/hospitals",
        headers={"Authorization": "Bearer token.invalido.firmado"},
    )
    assert r_tampered.status_code == 401

    # Acceso denegado por rol: PARAMEDICO no puede actualizar capacidad -> 403
    r_forbidden = client.put(
        "/api/v1/hospitals/1/capacity",
        headers=auth_headers["PARAMEDICO"],
        json={"tipo_recurso": "cama_uci", "total": 12, "ocupados": 9},
    )
    assert r_forbidden.status_code == 403

    # JEFE_URGENCIAS de H5 no puede modificar capacidad de H1 -> 409
    r_other_hosp = client.put(
        "/api/v1/hospitals/1/capacity",
        headers=auth_headers["JEFE_H5"],
        json={"tipo_recurso": "cama_uci", "total": 12, "ocupados": 9},
    )
    assert r_other_hosp.status_code == 409
