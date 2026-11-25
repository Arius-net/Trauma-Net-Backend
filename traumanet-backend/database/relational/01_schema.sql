-- D01 · Modelo relacional lógico de TraumaNet (PROPUESTA, estado: under_review)
-- Dialecto de referencia: SQL estándar con extensiones PostgreSQL (columna generada, índice parcial,
-- UUID). Sujeto a aprobación de D02. NO es un script de implementación (eso es D03, Etapa B).
-- Todos los datos que se carguen serán sintéticos. Sin credenciales ni PHI.

CREATE TABLE hospitales (
    hospital_id      INTEGER      PRIMARY KEY,            -- fuente de verdad; se replica en Grafo (R-03)
    clave            VARCHAR(20)  NOT NULL UNIQUE,
    nombre           VARCHAR(150) NOT NULL,
    municipio        VARCHAR(80)  NOT NULL,
    nivel_atencion   SMALLINT     NOT NULL CHECK (nivel_atencion IN (2, 3)),
    latitud          NUMERIC(9,6) NOT NULL CHECK (latitud  BETWEEN -90  AND 90),
    longitud         NUMERIC(9,6) NOT NULL CHECK (longitud BETWEEN -180 AND 180),
    activo           BOOLEAN      NOT NULL DEFAULT TRUE,
    sync_estado      VARCHAR(20)  NOT NULL DEFAULT 'synced'
                     CHECK (sync_estado IN ('synced', 'sync_pending')),   -- DATA_CONTEXT §3
    creado_en        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE usuarios (
    usuario_id       INTEGER      PRIMARY KEY,
    nombre_usuario   VARCHAR(50)  NOT NULL UNIQUE,         -- sintético
    password_hash    VARCHAR(255) NOT NULL,                -- PBKDF2-SHA256 (D-0005 / Q-05)
    rol              VARCHAR(20)  NOT NULL
                     CHECK (rol IN ('crum', 'paramedico', 'jefe_urgencias')),
    hospital_id      INTEGER      REFERENCES hospitales (hospital_id),
    activo           BOOLEAN      NOT NULL DEFAULT TRUE,
    CHECK ((rol = 'jefe_urgencias') = (hospital_id IS NOT NULL))  -- jefe ligado a 1 hospital; los demás no
);

CREATE TABLE recursos_hospitalarios (
    recurso_id       INTEGER      PRIMARY KEY,
    hospital_id      INTEGER      NOT NULL REFERENCES hospitales (hospital_id),
    tipo_recurso     VARCHAR(20)  NOT NULL
                     CHECK (tipo_recurso IN ('cama_uci', 'quirofano', 'sala_choque')),
    total            INTEGER      NOT NULL CHECK (total >= 0),
    ocupados         INTEGER      NOT NULL DEFAULT 0 CHECK (ocupados >= 0),    -- lo fija el Jefe de Urgencias
    reservados       INTEGER      NOT NULL DEFAULT 0 CHECK (reservados >= 0),  -- lo mantiene el servicio (reservas activas)
    disponibles      INTEGER      GENERATED ALWAYS AS (total - ocupados - reservados) STORED,
    actualizado_en   TIMESTAMPTZ  NOT NULL DEFAULT now(),                      -- base de data_vintage
    actualizado_por  INTEGER      REFERENCES usuarios (usuario_id),
    UNIQUE (hospital_id, tipo_recurso),
    CONSTRAINT ck_disponibles_no_negativos CHECK (disponibles >= 0)            -- barrera final contra sobre-reserva
);

CREATE TABLE ambulancias (
    ambulancia_id    INTEGER      PRIMARY KEY,
    clave            VARCHAR(20)  NOT NULL UNIQUE,
    tipo             VARCHAR(10)  NOT NULL CHECK (tipo IN ('basica', 'avanzada')),
    base_hospital_id INTEGER      NOT NULL REFERENCES hospitales (hospital_id),
    estado           VARCHAR(20)  NOT NULL DEFAULT 'disponible'
                     CHECK (estado IN ('disponible', 'en_servicio', 'fuera_servicio')),
    actualizado_en   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE personal_guardia (
    personal_id      INTEGER      PRIMARY KEY,
    hospital_id      INTEGER      NOT NULL REFERENCES hospitales (hospital_id),
    alias_sintetico  VARCHAR(50)  NOT NULL,                -- nunca nombres reales
    especialidad_codigo VARCHAR(40) NOT NULL,              -- código del nodo Especialidad (Grafo); referencia, no FK
    turno_inicio     TIMESTAMPTZ  NOT NULL,
    turno_fin        TIMESTAMPTZ  NOT NULL,
    presente         BOOLEAN      NOT NULL DEFAULT TRUE,
    CHECK (turno_fin > turno_inicio)
);
CREATE INDEX ix_guardia_hosp_esp_turno ON personal_guardia (hospital_id, especialidad_codigo, turno_inicio, turno_fin);

CREATE TABLE traslados (
    traslado_id      UUID         PRIMARY KEY,
    frap_id          CHAR(24)     NOT NULL,                -- ObjectId (hex) del FRAP en Documental; sin FK física
    hospital_destino_id INTEGER   NOT NULL REFERENCES hospitales (hospital_id),
    ambulancia_id    INTEGER      REFERENCES ambulancias (ambulancia_id),
    protocolo_codigo VARCHAR(40)  NOT NULL,                -- código de ProtocoloTrauma (Grafo)
    estado           VARCHAR(20)  NOT NULL
                     CHECK (estado IN ('propuesto', 'reservado', 'confirmado', 'en_ruta',
                                       'recibido', 'cancelado')),
    eta_min          NUMERIC(6,1) CHECK (eta_min > 0),
    eta_margen_min   NUMERIC(6,1) CHECK (eta_margen_min >= 0),   -- incertidumbre de ruta
    estado_via       VARCHAR(10)  CHECK (estado_via IN ('normal', 'demora', 'bloqueo')),
    data_vintage     TIMESTAMPTZ  NOT NULL,                -- antigüedad del inventario usado para decidir
    solicitado_por   INTEGER      NOT NULL REFERENCES usuarios (usuario_id),
    creado_en        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    actualizado_en   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
-- Un FRAP no puede tener dos traslados vigentes (idempotencia ante reintentos).
CREATE UNIQUE INDEX ux_traslado_frap_vigente ON traslados (frap_id) WHERE estado <> 'cancelado';
CREATE INDEX ix_traslados_destino_estado ON traslados (hospital_destino_id, estado);

CREATE TABLE reservas_recurso (
    reserva_id       UUID         PRIMARY KEY,
    traslado_id      UUID         NOT NULL REFERENCES traslados (traslado_id),
    recurso_id       INTEGER      NOT NULL REFERENCES recursos_hospitalarios (recurso_id),
    cantidad         INTEGER      NOT NULL DEFAULT 1 CHECK (cantidad > 0),
    estado           VARCHAR(20)  NOT NULL DEFAULT 'activa'
                     CHECK (estado IN ('activa', 'confirmada', 'consumida', 'liberada', 'expirada')),
    creada_en        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expira_en        TIMESTAMPTZ  NOT NULL,                -- TTL: creada_en + RESERVA_TTL_MIN (config)
    cerrada_en       TIMESTAMPTZ,
    CHECK (expira_en > creada_en),
    CHECK ((estado IN ('activa', 'confirmada')) = (cerrada_en IS NULL))
);
CREATE UNIQUE INDEX ux_reserva_viva_por_traslado_recurso
    ON reservas_recurso (traslado_id, recurso_id) WHERE estado IN ('activa', 'confirmada');
CREATE INDEX ix_reservas_expiracion ON reservas_recurso (expira_en) WHERE estado = 'activa';

/* REGLAS TRANSACCIONALES (se implementan en servicios/repositorios en Etapa C):
   R1 Reservar  : BEGIN; SELECT ... FROM recursos_hospitalarios WHERE recurso_id=$1 FOR UPDATE;
                  si disponibles >= cantidad -> UPDATE reservados = reservados + cantidad;
                  INSERT traslado + reserva (expira_en = now() + ttl); COMMIT. Si no -> ROLLBACK.
   R2 Expirar   : (a) perezosa dentro de R1 y (b) barrido periódico idempotente:
                  UPDATE reservas SET estado='expirada', cerrada_en=now()
                    WHERE estado='activa' AND expira_en < now()  (FOR UPDATE SKIP LOCKED)
                  y por cada una: reservados = reservados - cantidad; traslado -> 'cancelado' si no hay otra reserva viva.
   R3 Confirmar : el Jefe de Urgencias pasa la reserva a 'confirmada' (ya no expira por TTL).
   R4 Liberar   : cancelación -> 'liberada'; recepción del paciente -> 'consumida'
                  (reservados - cantidad, ocupados + cantidad, en la misma transacción).
   R5 Capacidad : el Jefe actualiza total/ocupados; si total - ocupados - reservados < 0 el CHECK rechaza (HTTP 409). */
