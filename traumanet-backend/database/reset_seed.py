"""Restaura las tres bases de datos (PostgreSQL, MongoDB, Neo4j) al estado semilla sintético limpio.

Uso:
  .venv\\Scripts\\python 08_APPLICATION/database/reset_seed.py
"""
import subprocess
import sys
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DB_DIR))
from common import pg_connect  # noqa: E402


def reset_postgres() -> None:
    seed_sql = (DB_DIR / "relational" / "02_seed.sql").read_text(encoding="utf-8")
    with pg_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "TRUNCATE TABLE reservas_recurso, traslados, personal_guardia, ambulancias, "
            "recursos_hospitalarios, usuarios, hospitales CASCADE"
        )
        # pg8000 ejecuta sentencias individuales; separar por ';' fuera de comentarios
        cleaned_lines = [ln for ln in seed_sql.splitlines() if not ln.strip().startswith("--")]
        statements = [s.strip() for s in "\n".join(cleaned_lines).split(";") if s.strip()]
        for stmt in statements:
            cur.execute(stmt)
        conn.commit()
        cur.close()
    print("[pg] tablas restauradas con 02_seed.sql (incluye hashes PBKDF2-SHA256)")


def main() -> int:
    reset_postgres()
    for script in [DB_DIR / "document" / "init_fraps.py", DB_DIR / "graph" / "init_graph.py"]:
        res = subprocess.run([sys.executable, str(script)], check=False)
        if res.returncode != 0:
            return res.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
