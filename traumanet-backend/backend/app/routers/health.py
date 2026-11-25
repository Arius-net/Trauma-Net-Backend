"""Router de salud y conectividad a los tres motores."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.dependencies import ServiceContainer, get_container

router = APIRouter(prefix="/health", tags=["Salud"])


@router.get("", summary="Verifica conectividad con PostgreSQL, MongoDB y Neo4j")
def health_check(response: Response, container: ServiceContainer = Depends(get_container)) -> dict:
    pg_ok = container.relational_repo.ping()
    mongo_ok = container.document_repo.ping()
    neo4j_ok = container.graph_repo.ping()
    all_ok = pg_ok and mongo_ok and neo4j_ok
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if all_ok else "degraded",
        "engines": {
            "postgresql": "up" if pg_ok else "down",
            "mongodb": "up" if mongo_ok else "down",
            "neo4j": "up" if neo4j_ok else "down",
        },
    }
