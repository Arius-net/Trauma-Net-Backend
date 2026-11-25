"""Pruebas de escritura parcial (R-01) autenticadas con JWT."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.dependencies import ServiceContainer, get_dispatch_service
from app.core.exceptions import DocumentUnavailableError, RelationalUnavailableError
from app.main import create_app
from app.services.dispatch_service import DispatchService
from tests.conftest import make_frap_payload


class _FailingReservationRelationalProxy:
    def __init__(self, real_repo):
        self._real = real_repo

    def __getattr__(self, name):
        return getattr(self._real, name)

    def reserve_resource_atomic(self, **_kwargs):
        raise RelationalUnavailableError("Fallo simulado de PostgreSQL durante reserva atómica")


class _FailingPostAssignMongoProxy:
    def __init__(self, real_repo):
        self._real = real_repo

    def __getattr__(self, name):
        return getattr(self._real, name)

    def update_frap_status(self, **kwargs):
        if kwargs.get("estado_frap") == "asignado":
            raise DocumentUnavailableError("Fallo simulado de MongoDB post-reserva")
        return self._real.update_frap_status(**kwargs)


def test_partial_write_postgres_failure_marks_frap_sin_asignacion(
    container: ServiceContainer,
    cleanup_registry: list[str],
    auth_headers: dict[str, dict[str, str]],
) -> None:
    test_app = create_app(settings=container.settings)
    failing_service = DispatchService(
        settings=container.settings,
        relational_repo=_FailingReservationRelationalProxy(container.relational_repo),
        document_repo=container.document_repo,
        graph_repo=container.graph_repo,
    )
    test_app.dependency_overrides[get_dispatch_service] = lambda: failing_service

    with TestClient(test_app) as test_client:
        resp = test_client.post(
            "/api/v1/dispatch/evaluate-and-assign",
            headers=auth_headers["PARAMEDICO"],
            json={
                "frap": make_frap_payload(
                    tipo_incidente="politrauma",
                    municipio="San Cristóbal de Las Casas",
                    syn_id="SYN-PART01",
                    ambulancia_id=None,
                )
            },
        )

    assert resp.status_code == 503
    body = resp.json()
    frap_id = body["frap_id"]
    cleanup_registry.append(frap_id)

    assert body["estado_despacho"] == "sin_asignacion"
    assert body["hospital_asignado"] is None
    assert body["reserva"] is None
    assert body["motivo_sin_asignacion"] is not None
    assert len(body["alternativas_rankeadas"]) >= 1
    assert body["data_vintage"] is not None
    assert body["incertidumbre_ruta"]["supuestos"]

    stored_frap = container.document_repo.get_frap_by_id(frap_id)
    assert stored_frap is not None
    assert stored_frap["estado_frap"] == "sin_asignacion"
    assert "relacional_no_disponible" in stored_frap["motivo_sin_asignacion"]
    assert container.relational_repo.get_traslado_by_frap_id(frap_id) is None


def test_partial_write_post_reservation_mongo_failure_compensates_postgres(
    container: ServiceContainer,
    cleanup_registry: list[str],
    auth_headers: dict[str, dict[str, str]],
) -> None:
    cap_antes = container.relational_repo.get_capacity_for_resource([5], "quirofano")[5]["disponibles"]

    test_app = create_app(settings=container.settings)
    failing_service = DispatchService(
        settings=container.settings,
        relational_repo=container.relational_repo,
        document_repo=_FailingPostAssignMongoProxy(container.document_repo),
        graph_repo=container.graph_repo,
    )
    test_app.dependency_overrides[get_dispatch_service] = lambda: failing_service

    with TestClient(test_app) as test_client:
        resp = test_client.post(
            "/api/v1/dispatch/evaluate-and-assign",
            headers=auth_headers["CRUM"],
            json={
                "frap": make_frap_payload(
                    tipo_incidente="politrauma",
                    municipio="San Cristóbal de Las Casas",
                    syn_id="SYN-PART02",
                    ambulancia_id=None,
                ),
                "preferred_hospital_id": 5,
                "strict_preferred_hospital": True,
            },
        )

    assert resp.status_code == 503
    body = resp.json()
    frap_id = body["frap_id"]
    cleanup_registry.append(frap_id)

    assert body["estado_despacho"] == "sin_asignacion"
    assert "compensada" in body["motivo_sin_asignacion"]

    cap_despues = container.relational_repo.get_capacity_for_resource([5], "quirofano")[5]["disponibles"]
    assert cap_despues == cap_antes

    traslado = container.relational_repo.get_traslado_by_frap_id(frap_id)
    assert traslado is not None
    assert traslado["estado"] == "cancelado"
    assert traslado["reservas"][0]["estado"] == "liberada"
