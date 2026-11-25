# Backend de TraumaNet (FastAPI — D05)

API modular en capas que coordina **PostgreSQL 16.6** (`pg8000`), **MongoDB 7.0.15** y **Neo4j 5.26.0 Community** para la **Decisión 1** (asignación inicial y reserva atómica), la **Decisión 2** (derivación en cascada) y autenticación formal **JWT Bearer** (`D-0005` / `Q-05`).

## Estructura por capas
- `app/routers/`: contratos HTTP REST con Pydantic y OpenAPI (`/docs`).
- `app/services/`: autenticación JWT, orquestación multiparadigma y política de fallos parciales (`sin_asignacion` / compensación).
- `app/repositories/relational/`, `document/`, `graph/`: acceso aislado por paradigma con consultas 100% parametrizadas.
- `app/core/`: configuración vía `.env` (incl. `JWT_SECRET_KEY` y `FRONTEND_URL` para CORS), clientes de BD, excepciones y seguridad JWT (`PBKDF2-SHA256`).

## Arranque local
```powershell
.venv\Scripts\pip install -r 08_APPLICATION/backend/requirements.txt
.venv\Scripts\python 08_APPLICATION/database/relational/apply_auth_migration.py   # solo si el volumen PG ya existía
.venv\Scripts\uvicorn app.main:app --app-dir 08_APPLICATION/backend --host 127.0.0.1 --port 8000 --reload
```

## Endpoints principales (`/api/v1`)
- `GET /health` — conectividad a PostgreSQL, MongoDB y Neo4j (público).
- `POST /auth/login` y `GET /auth/me` — emisión y validación de JWT Bearer contra `usuarios` de PostgreSQL.
- `POST /dispatch/evaluate-and-assign` (`PARAMEDICO`, `CRUM`) — flujo estrella de la Decisión 1.
- `GET /network/hospitals` — red hospitalaria integrada (Neo4j + PostgreSQL).
- `GET /network/cascade` (`CRUM`, `JEFE_URGENCIAS`) — derivación en cascada ante saturación.
- `PATCH /network/tramos/{tramo_id}` (`CRUM`) — cambio de `estado_via` (`normal`/`demora`/`bloqueo`).
- `GET` / `PUT /hospitals/{hospital_id}/capacity` y `GET /hospitals/{hospital_id}/reservas` (`JEFE_URGENCIAS`, `CRUM`).
- `POST /reservas/{reserva_id}/confirm` y `POST /reservas/expire-overdue` — confirmación y expiración TTL.
- `GET /expedientes` y `GET /expedientes/{frap_id}` — expediente FRAP completo (MongoDB + PostgreSQL).
