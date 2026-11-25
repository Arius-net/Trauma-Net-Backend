# TraumaNet Backend & Persistencia (FastAPI + PostgreSQL + MongoDB + Neo4j)

Repositorio independiente del backend y la capa de persistencia multiparadigma de **TraumaNet** (Despacho de Emergencias y Derivación Interhospitalaria en el corredor Tuxtla Gutiérrez – San Cristóbal – Comitán).

> **Principio rector:** TraumaNet apoya la decisión; no decide. Toda la operación utiliza datos sintéticos (sin PHI ni credenciales en el repositorio).

## Arranque desde cero

```powershell
copy .env.example .env            # completar contraseñas (Neo4j >= 8 caracteres) y JWT_SECRET_KEY
docker compose up -d --wait       # levanta PostgreSQL 16.6, MongoDB 7.0.15 y Neo4j 5.26.0 Community

python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

.venv\Scripts\python database/document/init_fraps.py
.venv\Scripts\python database/graph/init_graph.py
.venv\Scripts\python database/verify_stage_b.py       # 19/19 OK
.venv\Scripts\pytest                                  # 15/15 PASSED
```

## Ejecutar la API REST (`http://127.0.0.1:8000`)

```powershell
.venv\Scripts\uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```
- OpenAPI interactivo: `http://127.0.0.1:8000/docs`
- Restaurar semilla limpia: `.venv\Scripts\python database/reset_seed.py`

## Estructura
- `docker-compose.yml` y `.env.example`
- `database/`: esquemas, semillas sintéticas y utilidades (`relational/`, `document/`, `graph/`, `reset_seed.py`, `verify_stage_b.py`)
- `backend/`: API FastAPI en capas (`routers/`, `services/`, `repositories/{relational,document,graph}/`, `schemas/`, `core/`)
- `tests/`: suite Pytest (conectividad, JWT, integridad, concurrencia, fallo parcial y E2E)
