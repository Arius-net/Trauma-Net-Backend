# Bases de datos de TraumaNet (Etapa B)

Motores (D-0003): PostgreSQL 16.6 · MongoDB 7.0.15 · Neo4j 5.26.0 Community. Datos 100 % sintéticos.

## Arranque desde cero
```powershell
copy .env.example .env            # editar los tres *_PASSWORD (Neo4j: mínimo 8 caracteres)
docker compose down -v            # solo si se quiere reiniciar de cero
docker compose up -d --wait       # PostgreSQL carga relational/*.sql automáticamente (volumen vacío)
python -m venv .venv ; .venv\Scripts\pip install -r 08_APPLICATION/database/requirements.txt
.venv\Scripts\python 08_APPLICATION/database/document/init_fraps.py
.venv\Scripts\python 08_APPLICATION/database/graph/init_graph.py     # lee hospitales de PostgreSQL
.venv\Scripts\python 08_APPLICATION/database/verify_stage_b.py
```

| Carpeta | Contenido |
| :--- | :--- |
| `relational/` | `01_schema.sql` (copia de D01), `02_seed.sql` (8 hospitales, recursos, ambulancias, guardia, 2 traslados con reservas) |
| `document/` | `fraps_schema.json` (copia de D01) convertido a `$jsonSchema` por `init_fraps.py`, que recrea `fraps` y carga 8 FRAP (4 perfiles) |
| `graph/` | `01_constraints.cypher` y `init_graph.py` (nodos, relaciones y 56 aristas `CONECTADO_CON` generadas con la regla de D01) |

Consistencia: PostgreSQL es la fuente de `hospital_id`/`nombre`; el grafo los lee de ahí. Los `_id` de los FRAP semilla (`65f0…01`, `…02`) coinciden con `traslados.frap_id`.
Escenarios sembrados: HOSP-02 con **1 cama UCI libre** (prueba de concurrencia), HOSP-04 sin UCI libre, neurocirugía de HOSP-02 sin presencia en guardia.
Seguridad: `.env` está en `.gitignore`; los puertos se publican solo en `127.0.0.1`; las consultas Cypher son estáticas con parámetros.
