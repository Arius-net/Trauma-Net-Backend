"""Prueba de concurrencia (R-02): dos solicitudes simultáneas por la última cama UCI de HOSP-02."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from app.core.dependencies import ServiceContainer
from tests.conftest import make_frap_payload


def _get_hosp2_uci_disponibles(container: ServiceContainer) -> int:
    cap = container.relational_repo.get_capacity_for_resource([2], "cama_uci")
    return cap[2]["disponibles"]


def test_concurrency_last_uci_bed_hosp02_strict_only_one_wins(
    client: TestClient,
    container: ServiceContainer,
    cleanup_registry: list[str],
    auth_headers: dict[str, dict[str, str]],
) -> None:
    assert _get_hosp2_uci_disponibles(container) == 1

    barrier = Barrier(2)

    def _fire(idx: int):
        payload = {
            "frap": make_frap_payload(
                tipo_incidente="infarto_agudo",
                municipio="Tuxtla Gutiérrez",
                syn_id=f"SYN-CONC0{idx}",
                ambulancia_id=None,
            ),
            "origen_hospital_id": 2,
            "preferred_hospital_id": 2,
            "strict_preferred_hospital": True,
        }
        barrier.wait(timeout=10)
        resp = client.post(
            "/api/v1/dispatch/evaluate-and-assign",
            headers=auth_headers["CRUM"],
            json=payload,
        )
        return resp.status_code, resp.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_fire, 1)
        f2 = pool.submit(_fire, 2)
        results = [f1.result(), f2.result()]

    for _code, body in results:
        if body.get("frap_id"):
            cleanup_registry.append(body["frap_id"])

    codes = sorted(code for code, _ in results)
    assert codes == [201, 409], f"Se esperaba [201, 409], llegó: {results}"

    winner_body = next(b for c, b in results if c == 201)
    loser_body = next(b for c, b in results if c == 409)

    assert winner_body["estado_despacho"] == "asignado"
    assert winner_body["hospital_asignado"]["hospital_id"] == 2
    assert winner_body["hospital_asignado"]["recurso_disponible_antes"] == 1
    assert winner_body["hospital_asignado"]["recurso_disponible_despues"] == 0

    assert loser_body["estado_despacho"] == "sin_asignacion"
    assert _get_hosp2_uci_disponibles(container) == 0

    loser_frap = container.document_repo.get_frap_by_id(loser_body["frap_id"])
    assert loser_frap is not None
    assert loser_frap["estado_frap"] == "sin_asignacion"


def test_concurrency_last_uci_bed_hosp02_with_automatic_derivation(
    client: TestClient,
    container: ServiceContainer,
    cleanup_registry: list[str],
    auth_headers: dict[str, dict[str, str]],
) -> None:
    assert _get_hosp2_uci_disponibles(container) == 1

    barrier = Barrier(2)

    def _fire(idx: int):
        payload = {
            "frap": make_frap_payload(
                tipo_incidente="infarto_agudo",
                municipio="Tuxtla Gutiérrez",
                syn_id=f"SYN-CDRV0{idx}",
                ambulancia_id=None,
            ),
            "origen_hospital_id": 2,
            "preferred_hospital_id": 2,
            "strict_preferred_hospital": False,
        }
        barrier.wait(timeout=10)
        resp = client.post(
            "/api/v1/dispatch/evaluate-and-assign",
            headers=auth_headers["CRUM"],
            json=payload,
        )
        return resp.status_code, resp.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_fire, 1)
        f2 = pool.submit(_fire, 2)
        results = [f1.result(), f2.result()]

    for _code, body in results:
        if body.get("frap_id"):
            cleanup_registry.append(body["frap_id"])

    assert all(code == 201 for code, _ in results), f"Ambas debían asignarse: {results}"
    assigned_ids = [b["hospital_asignado"]["hospital_id"] for _, b in results]
    assert assigned_ids.count(2) == 1
    derived_id = next(hid for hid in assigned_ids if hid != 2)
    assert derived_id in (1, 3)
    assert _get_hosp2_uci_disponibles(container) == 0
