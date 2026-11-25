"""Excepciones de dominio para separar errores de persistencia de la capa HTTP."""
from __future__ import annotations


class TraumaNetError(Exception):
    """Error base de dominio."""


class NotFoundError(TraumaNetError):
    """Recurso o entidad inexistente."""


class DocumentValidationError(TraumaNetError):
    """Documento FRAP rechazado por el esquema de validación."""


class CapacityConflictError(TraumaNetError):
    """Violación de integridad de capacidad (ej. disponibles < 0 o reserva incompatible)."""


class RelationalUnavailableError(TraumaNetError):
    """Fallo de conectividad o ejecución en la base relacional (PostgreSQL)."""


class DocumentUnavailableError(TraumaNetError):
    """Fallo de conectividad o ejecución en la base documental (MongoDB)."""


class GraphUnavailableError(TraumaNetError):
    """Fallo de conectividad o ejecución en la base de grafo (Neo4j)."""


class PartialWriteError(TraumaNetError):
    """Fallo parcial en escritura multiparadigma: nunca se reporta éxito total."""

    def __init__(self, message: str, payload: dict, status_code: int = 503):
        super().__init__(message)
        self.payload = payload
        self.status_code = status_code
