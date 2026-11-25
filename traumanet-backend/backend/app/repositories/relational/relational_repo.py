"""Repositorio Relacional (PostgreSQL) — consultas 100% parametrizadas y control ACID."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pg8000.dbapi as pg

from app.core.database import DatabaseClients
from app.core.exceptions import (
    CapacityConflictError,
    NotFoundError,
    RelationalUnavailableError,
)


def _sqlstate(exc: Exception) -> str | None:
    if exc.args and isinstance(exc.args[0], dict):
        return exc.args[0].get("C")
    return None


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class RelationalRepository:
    """Acceso aislado a PostgreSQL: capacidad hospitalaria, guardias, traslados y reservas ACID."""

    def __init__(self, clients: DatabaseClients) -> None:
        self._clients = clients

    def ping(self) -> bool:
        try:
            with self._clients.pg_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                row = cur.fetchone()
                cur.close()
                return row is not None and row[0] == 1
        except Exception:
            return False

    def get_hospitals_map(self) -> dict[int, dict[str, Any]]:
        try:
            with self._clients.pg_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """SELECT hospital_id, clave, nombre, municipio, nivel_atencion, latitud, longitud, activo
                       FROM hospitales
                       WHERE activo = TRUE
                       ORDER BY hospital_id"""
                )
                rows = cur.fetchall()
                cur.close()
        except Exception as exc:
            raise RelationalUnavailableError(f"Error consultando hospitales en PostgreSQL: {exc}") from exc

        return {
            r[0]: {
                "hospital_id": r[0],
                "clave": r[1],
                "nombre": r[2],
                "municipio": r[3],
                "nivel_atencion": int(r[4]),
                "latitud": float(r[5]),
                "longitud": float(r[6]),
                "activo": bool(r[7]),
            }
            for r in rows
        }

    def get_all_resources_by_hospital(self) -> dict[int, list[dict[str, Any]]]:
        try:
            with self._clients.pg_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """SELECT recurso_id, hospital_id, tipo_recurso, total, ocupados, reservados,
                              disponibles, actualizado_en
                       FROM recursos_hospitalarios
                       ORDER BY hospital_id, tipo_recurso"""
                )
                rows = cur.fetchall()
                cur.close()
        except Exception as exc:
            raise RelationalUnavailableError(f"Error consultando recursos en PostgreSQL: {exc}") from exc

        result: dict[int, list[dict[str, Any]]] = {}
        for r in rows:
            item = {
                "recurso_id": r[0],
                "hospital_id": r[1],
                "tipo_recurso": r[2],
                "total": int(r[3]),
                "ocupados": int(r[4]),
                "reservados": int(r[5]),
                "disponibles": int(r[6]),
                "actualizado_en": _ensure_utc(r[7]),
            }
            result.setdefault(r[1], []).append(item)
        return result

    def get_capacity_for_resource(
        self, hospital_ids: list[int], tipo_recurso: str
    ) -> dict[int, dict[str, Any]]:
        if not hospital_ids:
            return {}
        try:
            with self._clients.pg_connection() as conn:
                # Expirar reservas vencidas antes de leer capacidad en vivo (regla R2a)
                self._expire_overdue_in_conn(conn)
                conn.commit()
                cur = conn.cursor()
                cur.execute(
                    """SELECT recurso_id, hospital_id, tipo_recurso, total, ocupados, reservados,
                              disponibles, actualizado_en
                       FROM recursos_hospitalarios
                       WHERE hospital_id = ANY(%s) AND tipo_recurso = %s""",
                    (list(hospital_ids), tipo_recurso),
                )
                rows = cur.fetchall()
                cur.close()
        except Exception as exc:
            raise RelationalUnavailableError(f"Error consultando capacidad en PostgreSQL: {exc}") from exc

        return {
            r[1]: {
                "recurso_id": r[0],
                "hospital_id": r[1],
                "tipo_recurso": r[2],
                "total": int(r[3]),
                "ocupados": int(r[4]),
                "reservados": int(r[5]),
                "disponibles": int(r[6]),
                "actualizado_en": _ensure_utc(r[7]),
            }
            for r in rows
        }

    def get_active_guardia(
        self, hospital_ids: list[int], especialidades: list[str]
    ) -> dict[int, set[str]]:
        if not hospital_ids or not especialidades:
            return {}
        try:
            with self._clients.pg_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """SELECT DISTINCT hospital_id, especialidad_codigo
                       FROM personal_guardia
                       WHERE hospital_id = ANY(%s)
                         AND especialidad_codigo = ANY(%s)
                         AND presente = TRUE
                         AND now() BETWEEN turno_inicio AND turno_fin""",
                    (list(hospital_ids), list(especialidades)),
                )
                rows = cur.fetchall()
                cur.close()
        except Exception as exc:
            raise RelationalUnavailableError(f"Error consultando personal de guardia: {exc}") from exc

        guardia: dict[int, set[str]] = {hid: set() for hid in hospital_ids}
        for hid, esp in rows:
            guardia.setdefault(hid, set()).add(esp)
        return guardia

    def _expire_overdue_in_conn(self, conn: pg.Connection) -> int:
        """Regla R2 (D01): expira reservas activas vencidas con FOR UPDATE SKIP LOCKED."""
        cur = conn.cursor()
        cur.execute(
            """SELECT reserva_id, traslado_id, recurso_id, cantidad
               FROM reservas_recurso
               WHERE estado = 'activa' AND expira_en < now()
               FOR UPDATE SKIP LOCKED"""
        )
        expired = cur.fetchall()
        for reserva_id, traslado_id, recurso_id, cantidad in expired:
            cur.execute(
                """UPDATE reservas_recurso
                   SET estado = 'expirada', cerrada_en = now()
                   WHERE reserva_id = %s AND estado = 'activa'""",
                (reserva_id,),
            )
            cur.execute(
                """UPDATE recursos_hospitalarios
                   SET reservados = GREATEST(reservados - %s, 0)
                   WHERE recurso_id = %s""",
                (cantidad, recurso_id),
            )
            cur.execute(
                """UPDATE traslados
                   SET estado = 'cancelado', actualizado_en = now()
                   WHERE traslado_id = %s
                     AND estado IN ('propuesto', 'reservado')
                     AND NOT EXISTS (
                         SELECT 1 FROM reservas_recurso r2
                         WHERE r2.traslado_id = %s AND r2.estado IN ('activa', 'confirmada')
                     )""",
                (traslado_id, traslado_id),
            )
        cur.close()
        return len(expired)

    def expire_overdue_reservations(self) -> int:
        try:
            with self._clients.pg_connection() as conn:
                count = self._expire_overdue_in_conn(conn)
                conn.commit()
                return count
        except Exception as exc:
            raise RelationalUnavailableError(f"Error expirando reservas vencidas: {exc}") from exc

    def reserve_resource_atomic(
        self,
        *,
        hospital_id: int,
        tipo_recurso: str,
        frap_id: str,
        protocolo_codigo: str,
        eta_min: float,
        eta_margen_min: float,
        estado_via: str,
        solicitado_por: int,
        ambulancia_id: int | None,
        ttl_minutos: int,
        cantidad: int = 1,
    ) -> dict[str, Any] | None:
        """Regla R1 (D01): reserva atómica con bloqueo de fila SELECT ... FOR UPDATE.

        Devuelve los datos de traslado y reserva si se concreta, o None si ya no hay disponibilidad.
        """
        traslado_id = str(uuid.uuid4())
        reserva_id = str(uuid.uuid4())
        safe_eta = max(float(eta_min), 1.0)
        safe_margin = max(float(eta_margen_min), 0.0)

        try:
            with self._clients.pg_connection() as conn:
                cur = conn.cursor()
                try:
                    # Expiración perezosa antes de bloquear el recurso
                    self._expire_overdue_in_conn(conn)

                    # Bloqueo exclusivo de fila para evitar doble reserva concurrente (R-02)
                    cur.execute(
                        """SELECT recurso_id, total, ocupados, reservados, disponibles, actualizado_en
                           FROM recursos_hospitalarios
                           WHERE hospital_id = %s AND tipo_recurso = %s
                           FOR UPDATE""",
                        (hospital_id, tipo_recurso),
                    )
                    row = cur.fetchone()
                    if row is None:
                        conn.rollback()
                        return None

                    recurso_id, _total, _ocupados, _reservados, disponibles, actualizado_en = row
                    if int(disponibles) < cantidad:
                        conn.rollback()
                        return None

                    cur.execute(
                        """UPDATE recursos_hospitalarios
                           SET reservados = reservados + %s
                           WHERE recurso_id = %s
                           RETURNING disponibles, actualizado_en""",
                        (cantidad, recurso_id),
                    )
                    updated = cur.fetchone()
                    disponibles_despues = int(updated[0])
                    data_vintage = _ensure_utc(updated[1] or actualizado_en)

                    cur.execute(
                        """INSERT INTO traslados (
                               traslado_id, frap_id, hospital_destino_id, ambulancia_id,
                               protocolo_codigo, estado, eta_min, eta_margen_min, estado_via,
                               data_vintage, solicitado_por
                           ) VALUES (%s, %s, %s, %s, %s, 'reservado', %s, %s, %s, %s, %s)""",
                        (
                            traslado_id,
                            frap_id,
                            hospital_id,
                            ambulancia_id,
                            protocolo_codigo,
                            safe_eta,
                            safe_margin,
                            estado_via,
                            data_vintage,
                            solicitado_por,
                        ),
                    )

                    cur.execute(
                        """INSERT INTO reservas_recurso (
                               reserva_id, traslado_id, recurso_id, cantidad, estado, creada_en, expira_en
                           ) VALUES (
                               %s, %s, %s, %s, 'activa', now(), now() + (%s * interval '1 minute')
                           )
                           RETURNING creada_en, expira_en""",
                        (reserva_id, traslado_id, recurso_id, cantidad, ttl_minutos),
                    )
                    creada_en, expira_en = cur.fetchone()
                    conn.commit()
                    return {
                        "reserva_id": reserva_id,
                        "traslado_id": traslado_id,
                        "recurso_id": recurso_id,
                        "tipo_recurso": tipo_recurso,
                        "cantidad": cantidad,
                        "estado": "activa",
                        "creada_en": _ensure_utc(creada_en),
                        "expira_en": _ensure_utc(expira_en),
                        "ttl_minutos": ttl_minutos,
                        "disponibles_antes": int(disponibles),
                        "disponibles_despues": disponibles_despues,
                        "data_vintage": data_vintage,
                    }
                except pg.DatabaseError as exc:
                    conn.rollback()
                    state = _sqlstate(exc)
                    if state == "23514":
                        # CHECK disponibles >= 0: tratar como agotamiento de capacidad
                        return None
                    if state == "23505":
                        raise CapacityConflictError(
                            f"El FRAP '{frap_id}' ya cuenta con un traslado vigente."
                        ) from exc
                    raise RelationalUnavailableError(f"Error transaccional en PostgreSQL: {exc}") from exc
                finally:
                    cur.close()
        except (CapacityConflictError, RelationalUnavailableError):
            raise
        except Exception as exc:
            raise RelationalUnavailableError(f"PostgreSQL no disponible durante reserva: {exc}") from exc

    def compensate_release_reservation(self, reserva_id: str, traslado_id: str) -> bool:
        """Compensación síncrona si falla actualizar MongoDB tras confirmar en PostgreSQL."""
        try:
            with self._clients.pg_connection() as conn:
                cur = conn.cursor()
                try:
                    cur.execute(
                        """SELECT recurso_id, cantidad, estado
                           FROM reservas_recurso
                           WHERE reserva_id = %s
                           FOR UPDATE""",
                        (reserva_id,),
                    )
                    row = cur.fetchone()
                    if row and row[2] in ("activa", "confirmada"):
                        recurso_id, cantidad, _ = row
                        cur.execute(
                            """UPDATE reservas_recurso
                               SET estado = 'liberada', cerrada_en = now()
                               WHERE reserva_id = %s""",
                            (reserva_id,),
                        )
                        cur.execute(
                            """UPDATE recursos_hospitalarios
                               SET reservados = GREATEST(reservados - %s, 0)
                               WHERE recurso_id = %s""",
                            (cantidad, recurso_id),
                        )
                    cur.execute(
                        """UPDATE traslados
                           SET estado = 'cancelado', actualizado_en = now()
                           WHERE traslado_id = %s""",
                        (traslado_id,),
                    )
                    conn.commit()
                    return True
                except Exception:
                    conn.rollback()
                    return False
                finally:
                    cur.close()
        except Exception:
            return False

    def get_hospital_capacity(self, hospital_id: int) -> dict[str, Any]:
        try:
            with self._clients.pg_connection() as conn:
                self._expire_overdue_in_conn(conn)
                conn.commit()
                cur = conn.cursor()
                cur.execute(
                    "SELECT hospital_id, nombre FROM hospitales WHERE hospital_id = %s",
                    (hospital_id,),
                )
                hosp = cur.fetchone()
                if hosp is None:
                    cur.close()
                    raise NotFoundError(f"Hospital {hospital_id} no encontrado.")
                cur.execute(
                    """SELECT recurso_id, tipo_recurso, total, ocupados, reservados, disponibles, actualizado_en
                       FROM recursos_hospitalarios
                       WHERE hospital_id = %s
                       ORDER BY tipo_recurso""",
                    (hospital_id,),
                )
                rows = cur.fetchall()
                cur.close()
        except NotFoundError:
            raise
        except Exception as exc:
            raise RelationalUnavailableError(f"Error consultando capacidad del hospital {hospital_id}: {exc}") from exc

        return {
            "hospital_id": hosp[0],
            "nombre": hosp[1],
            "recursos": [
                {
                    "recurso_id": r[0],
                    "tipo_recurso": r[1],
                    "total": int(r[2]),
                    "ocupados": int(r[3]),
                    "reservados": int(r[4]),
                    "disponibles": int(r[5]),
                    "actualizado_en": _ensure_utc(r[6]),
                }
                for r in rows
            ],
        }

    def update_hospital_capacity(
        self,
        *,
        hospital_id: int,
        tipo_recurso: str,
        total: int,
        ocupados: int,
        actualizado_por: int,
    ) -> dict[str, Any]:
        """Regla R5 (D01): el Jefe de Urgencias actualiza total/ocupados; CHECK protege disponibles >= 0."""
        try:
            with self._clients.pg_connection() as conn:
                cur = conn.cursor()
                try:
                    cur.execute(
                        """UPDATE recursos_hospitalarios
                           SET total = %s,
                               ocupados = %s,
                               actualizado_en = now(),
                               actualizado_por = %s
                           WHERE hospital_id = %s AND tipo_recurso = %s
                           RETURNING recurso_id, tipo_recurso, total, ocupados, reservados, disponibles, actualizado_en""",
                        (total, ocupados, actualizado_por, hospital_id, tipo_recurso),
                    )
                    row = cur.fetchone()
                    if row is None:
                        conn.rollback()
                        raise NotFoundError(
                            f"No existe el recurso '{tipo_recurso}' para el hospital {hospital_id}."
                        )
                    conn.commit()
                    return {
                        "recurso_id": row[0],
                        "tipo_recurso": row[1],
                        "total": int(row[2]),
                        "ocupados": int(row[3]),
                        "reservados": int(row[4]),
                        "disponibles": int(row[5]),
                        "actualizado_en": _ensure_utc(row[6]),
                    }
                except pg.DatabaseError as exc:
                    conn.rollback()
                    if _sqlstate(exc) == "23514":
                        raise CapacityConflictError(
                            "Actualización rechazada: total - ocupados - reservados no puede ser negativo (CHECK disponibles >= 0)."
                        ) from exc
                    raise RelationalUnavailableError(f"Error actualizando capacidad: {exc}") from exc
                finally:
                    cur.close()
        except (NotFoundError, CapacityConflictError, RelationalUnavailableError):
            raise
        except Exception as exc:
            raise RelationalUnavailableError(f"PostgreSQL no disponible al actualizar capacidad: {exc}") from exc

    def confirm_reservation(self, reserva_id: str) -> dict[str, Any]:
        """Regla R3 (D01): el Jefe de Urgencias confirma la reserva (deja de expirar por TTL)."""
        try:
            with self._clients.pg_connection() as conn:
                cur = conn.cursor()
                try:
                    cur.execute(
                        """SELECT reserva_id, traslado_id, estado
                           FROM reservas_recurso
                           WHERE reserva_id = %s
                           FOR UPDATE""",
                        (reserva_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        conn.rollback()
                        raise NotFoundError(f"Reserva '{reserva_id}' no encontrada.")
                    _, traslado_id, estado_actual = row
                    if estado_actual not in ("activa", "confirmada"):
                        conn.rollback()
                        raise CapacityConflictError(
                            f"No se puede confirmar la reserva en estado '{estado_actual}'."
                        )
                    cur.execute(
                        """UPDATE reservas_recurso
                           SET estado = 'confirmada'
                           WHERE reserva_id = %s""",
                        (reserva_id,),
                    )
                    cur.execute(
                        """UPDATE traslados
                           SET estado = 'confirmado', actualizado_en = now()
                           WHERE traslado_id = %s""",
                        (traslado_id,),
                    )
                    conn.commit()
                    return {
                        "reserva_id": str(reserva_id),
                        "traslado_id": str(traslado_id),
                        "estado_reserva": "confirmada",
                        "estado_traslado": "confirmado",
                        "cerrada_en": None,
                    }
                except (NotFoundError, CapacityConflictError):
                    raise
                except Exception as exc:
                    conn.rollback()
                    raise RelationalUnavailableError(f"Error confirmando reserva: {exc}") from exc
                finally:
                    cur.close()
        except (NotFoundError, CapacityConflictError, RelationalUnavailableError):
            raise
        except Exception as exc:
            raise RelationalUnavailableError(f"PostgreSQL no disponible al confirmar reserva: {exc}") from exc

    def get_traslado_by_frap_id(self, frap_id: str) -> dict[str, Any] | None:
        try:
            with self._clients.pg_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """SELECT t.traslado_id, t.hospital_destino_id, h.nombre, t.ambulancia_id,
                              t.protocolo_codigo, t.estado, t.eta_min, t.eta_margen_min,
                              t.estado_via, t.data_vintage, t.creado_en, t.actualizado_en
                       FROM traslados t
                       JOIN hospitales h ON h.hospital_id = t.hospital_destino_id
                       WHERE t.frap_id = %s
                       ORDER BY t.creado_en DESC
                       LIMIT 1""",
                    (frap_id,),
                )
                row = cur.fetchone()
                if row is None:
                    cur.close()
                    return None
                traslado_id = row[0]
                cur.execute(
                    """SELECT r.reserva_id, r.recurso_id, rh.tipo_recurso, r.cantidad,
                              r.estado, r.creada_en, r.expira_en, r.cerrada_en
                       FROM reservas_recurso r
                       JOIN recursos_hospitalarios rh ON rh.recurso_id = r.recurso_id
                       WHERE r.traslado_id = %s
                       ORDER BY r.creada_en DESC""",
                    (traslado_id,),
                )
                res_rows = cur.fetchall()
                cur.close()
        except Exception as exc:
            raise RelationalUnavailableError(f"Error consultando traslado del FRAP {frap_id}: {exc}") from exc

        return {
            "traslado_id": str(row[0]),
            "hospital_destino_id": int(row[1]),
            "hospital_destino_nombre": row[2],
            "ambulancia_id": row[3],
            "protocolo_codigo": row[4],
            "estado": row[5],
            "eta_min": float(row[6]) if row[6] is not None else None,
            "eta_margen_min": float(row[7]) if row[7] is not None else None,
            "estado_via": row[8],
            "data_vintage": _ensure_utc(row[9]),
            "creado_en": _ensure_utc(row[10]),
            "actualizado_en": _ensure_utc(row[11]),
            "reservas": [
                {
                    "reserva_id": str(rr[0]),
                    "recurso_id": int(rr[1]),
                    "tipo_recurso": rr[2],
                    "cantidad": int(rr[3]),
                    "estado": rr[4],
                    "creada_en": _ensure_utc(rr[5]),
                    "expira_en": _ensure_utc(rr[6]),
                    "cerrada_en": _ensure_utc(rr[7]),
                }
                for rr in res_rows
            ],
        }

    def get_user_by_username(self, nombre_usuario: str) -> dict[str, Any] | None:
        try:
            with self._clients.pg_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """SELECT u.usuario_id, u.nombre_usuario, u.password_hash, u.rol,
                              u.hospital_id, u.activo, h.nombre
                       FROM usuarios u
                       LEFT JOIN hospitales h ON h.hospital_id = u.hospital_id
                       WHERE u.nombre_usuario = %s""",
                    (nombre_usuario,),
                )
                row = cur.fetchone()
                cur.close()
        except Exception as exc:
            raise RelationalUnavailableError(f"Error consultando usuario en PostgreSQL: {exc}") from exc

        if row is None:
            return None
        return {
            "usuario_id": int(row[0]),
            "nombre_usuario": row[1],
            "password_hash": row[2],
            "rol": str(row[3]).upper(),
            "hospital_id": int(row[4]) if row[4] is not None else None,
            "activo": bool(row[5]),
            "hospital_nombre": row[6],
        }

    def get_user_by_id(self, usuario_id: int) -> dict[str, Any] | None:
        try:
            with self._clients.pg_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """SELECT u.usuario_id, u.nombre_usuario, u.rol, u.hospital_id, u.activo, h.nombre
                       FROM usuarios u
                       LEFT JOIN hospitales h ON h.hospital_id = u.hospital_id
                       WHERE u.usuario_id = %s""",
                    (usuario_id,),
                )
                row = cur.fetchone()
                cur.close()
        except Exception as exc:
            raise RelationalUnavailableError(f"Error consultando perfil de usuario: {exc}") from exc

        if row is None:
            return None
        return {
            "usuario_id": int(row[0]),
            "nombre_usuario": row[1],
            "rol": str(row[2]).upper(),
            "hospital_id": int(row[3]) if row[3] is not None else None,
            "activo": bool(row[4]),
            "hospital_nombre": row[5],
        }

    def get_reservas_by_hospital(self, hospital_id: int) -> list[dict[str, Any]]:
        try:
            with self._clients.pg_connection() as conn:
                self._expire_overdue_in_conn(conn)
                conn.commit()
                cur = conn.cursor()
                cur.execute(
                    """SELECT r.reserva_id, r.traslado_id, t.frap_id, r.recurso_id,
                              rh.tipo_recurso, r.cantidad, r.estado, t.estado,
                              t.protocolo_codigo, t.eta_min, t.eta_margen_min,
                              r.creada_en, r.expira_en, r.cerrada_en
                       FROM reservas_recurso r
                       JOIN recursos_hospitalarios rh ON rh.recurso_id = r.recurso_id
                       JOIN traslados t ON t.traslado_id = r.traslado_id
                       WHERE rh.hospital_id = %s
                       ORDER BY r.creada_en DESC
                       LIMIT 50""",
                    (hospital_id,),
                )
                rows = cur.fetchall()
                cur.close()
        except Exception as exc:
            raise RelationalUnavailableError(f"Error consultando reservas del hospital {hospital_id}: {exc}") from exc

        return [
            {
                "reserva_id": str(r[0]),
                "traslado_id": str(r[1]),
                "frap_id": r[2].strip(),
                "recurso_id": int(r[3]),
                "tipo_recurso": r[4],
                "cantidad": int(r[5]),
                "estado_reserva": r[6],
                "estado_traslado": r[7],
                "protocolo_codigo": r[8],
                "eta_min": float(r[9]) if r[9] is not None else None,
                "eta_margen_min": float(r[10]) if r[10] is not None else None,
                "creada_en": _ensure_utc(r[11]),
                "expira_en": _ensure_utc(r[12]),
                "cerrada_en": _ensure_utc(r[13]),
            }
            for r in rows
        ]
