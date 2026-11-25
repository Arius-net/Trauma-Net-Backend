"""Contenedor de dependencias por capas para FastAPI (permite inyección y pruebas limpias)."""
from __future__ import annotations

from fastapi import Request

from app.core.config import Settings, load_settings
from app.core.database import DatabaseClients
from app.repositories.document.document_repo import DocumentRepository
from app.repositories.graph.graph_repo import GraphRepository
from app.repositories.relational.relational_repo import RelationalRepository
from app.services.auth_service import AuthService
from app.services.capacity_service import CapacityService
from app.services.dispatch_service import DispatchService
from app.services.expediente_service import ExpedienteService
from app.services.network_service import NetworkService


class ServiceContainer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.clients = DatabaseClients(self.settings)
        self.relational_repo = RelationalRepository(self.clients)
        self.document_repo = DocumentRepository(self.clients)
        self.graph_repo = GraphRepository(self.clients)

        self.auth_service = AuthService(
            settings=self.settings,
            relational_repo=self.relational_repo,
        )
        self.dispatch_service = DispatchService(
            settings=self.settings,
            relational_repo=self.relational_repo,
            document_repo=self.document_repo,
            graph_repo=self.graph_repo,
        )
        self.network_service = NetworkService(
            settings=self.settings,
            relational_repo=self.relational_repo,
            graph_repo=self.graph_repo,
        )
        self.capacity_service = CapacityService(relational_repo=self.relational_repo)
        self.expediente_service = ExpedienteService(
            document_repo=self.document_repo,
            relational_repo=self.relational_repo,
        )

    def startup(self) -> None:
        self.clients.connect()

    def shutdown(self) -> None:
        self.clients.close()


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.container.auth_service


def get_dispatch_service(request: Request) -> DispatchService:
    return request.app.state.container.dispatch_service


def get_network_service(request: Request) -> NetworkService:
    return request.app.state.container.network_service


def get_capacity_service(request: Request) -> CapacityService:
    return request.app.state.container.capacity_service


def get_expediente_service(request: Request) -> ExpedienteService:
    return request.app.state.container.expediente_service
