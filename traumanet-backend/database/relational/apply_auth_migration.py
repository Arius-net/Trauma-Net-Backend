"""Migración idempotente en vivo para agregar password_hash a `usuarios` (D-0005 / Q-05).

Permite actualizar una instancia PostgreSQL ya inicializada sin borrar el volumen.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import pg_connect  # noqa: E402

SEED_HASHES = {
    "crum_sintetico_01":  "pbkdf2_sha256$260000$a1000000000000000000000000000001$67220ac3804072520d92940b193965047ff56e9667d293ee778f8c867569ffa6",
    "paramedico_sint_01": "pbkdf2_sha256$260000$a2000000000000000000000000000002$8f8349cd259631969adea4620b597d6f5f2b427efde58b1a9e0eca7e7bc25ce9",
    "paramedico_sint_02": "pbkdf2_sha256$260000$a3000000000000000000000000000003$00426047c2c425b66fbeb97c81ae2e3ed2e3f3c868967a1191875aafbb1d1e9c",
    "jefe_urg_h1": "pbkdf2_sha256$260000$b0000000000000000000000000000001$71785e06b31f183302f037449220bed7bdb9d88df43e47db0c6a9b6fb5ce0f27",
    "jefe_urg_h2": "pbkdf2_sha256$260000$b0000000000000000000000000000002$7bc8d159351f363a235d1de338a32546c23e2a6d4e90ca6e9343fb42d51ccbac",
    "jefe_urg_h3": "pbkdf2_sha256$260000$b0000000000000000000000000000003$45cf1492b7a54653490bc999259ab75c0af82e6d2a46f5ddabfffa8c01f44a7a",
    "jefe_urg_h4": "pbkdf2_sha256$260000$b0000000000000000000000000000004$c97e0cda627fb36c90efaedf2b89efb09472497429234d0e86d92f4c74b9cece",
    "jefe_urg_h5": "pbkdf2_sha256$260000$b0000000000000000000000000000005$5a00cec0b3e83b54a83a7138fcd92d6d4daa93c486ffa726aee2524b27e56cdc",
    "jefe_urg_h6": "pbkdf2_sha256$260000$b0000000000000000000000000000006$106ad48dfc9d24605822f29a14fc6ce6ad232bd27c6454c635e0797fa1a8d3ed",
    "jefe_urg_h7": "pbkdf2_sha256$260000$b0000000000000000000000000000007$d9b069720227d4661049f7dd8c35c56c3c7eea11e3257d980a84bd32fbd6ef18",
    "jefe_urg_h8": "pbkdf2_sha256$260000$b0000000000000000000000000000008$a36341c826a6a3691a90bd8609b1728d264977cae887e49fe8a734a8302e89d6",
}


def main() -> None:
    with pg_connect() as conn:
        cur = conn.cursor()
        cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)")
        for username, digest in SEED_HASHES.items():
            cur.execute(
                "UPDATE usuarios SET password_hash = %s WHERE nombre_usuario = %s",
                (digest, username),
            )
        cur.execute("ALTER TABLE usuarios ALTER COLUMN password_hash SET NOT NULL")
        conn.commit()
        cur.execute("SELECT count(*) FROM usuarios WHERE password_hash LIKE 'pbkdf2_sha256$%'")
        n = cur.fetchone()[0]
        cur.close()
    print(f"[pg] migración auth aplicada: {n} usuarios con password_hash PBKDF2-SHA256")


if __name__ == "__main__":
    main()
