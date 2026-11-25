-- Datos 100% sintéticos y reproducibles (Etapa B). Sin PHI. Capacidades inventadas; topología de referencia (A-05).
-- Orden: hospitales → usuarios → recursos → ambulancias → personal_guardia → traslados → reservas.

INSERT INTO hospitales (hospital_id, clave, nombre, municipio, nivel_atencion, latitud, longitud) VALUES
 (1, 'HOSP-01', 'Hospital General "Dr. Rafael Pascacio Gamboa"',        'Tuxtla Gutiérrez',           3, 16.753000, -93.115000),
 (2, 'HOSP-02', 'Hospital de Especialidades "Vida Mejor"',              'Tuxtla Gutiérrez',           3, 16.760000, -93.098000),
 (3, 'HOSP-03', 'IMSS Hospital General de Zona, Tuxtla',                'Tuxtla Gutiérrez',           2, 16.745000, -93.125000),
 (4, 'HOSP-04', 'ISSSTE Hospital General, Tuxtla',                      'Tuxtla Gutiérrez',           2, 16.768000, -93.110000),
 (5, 'HOSP-05', 'Hospital General "Hospital de las Culturas"',          'San Cristóbal de Las Casas', 2, 16.735000, -92.640000),
 (6, 'HOSP-06', 'IMSS Hospital General de Zona, San Cristóbal',         'San Cristóbal de Las Casas', 2, 16.742000, -92.630000),
 (7, 'HOSP-07', 'Hospital General "Dr. Belisario Domínguez"',           'Comitán de Domínguez',       2, 16.250000, -92.135000),
 (8, 'HOSP-08', 'IMSS Hospital General de Zona, Comitán',               'Comitán de Domínguez',       2, 16.255000, -92.128000);

INSERT INTO usuarios (usuario_id, nombre_usuario, password_hash, rol, hospital_id) VALUES
 (1,  'crum_sintetico_01',  'pbkdf2_sha256$260000$a1000000000000000000000000000001$67220ac3804072520d92940b193965047ff56e9667d293ee778f8c867569ffa6', 'crum',           NULL),
 (2,  'paramedico_sint_01', 'pbkdf2_sha256$260000$a2000000000000000000000000000002$8f8349cd259631969adea4620b597d6f5f2b427efde58b1a9e0eca7e7bc25ce9', 'paramedico',     NULL),
 (3,  'paramedico_sint_02', 'pbkdf2_sha256$260000$a3000000000000000000000000000003$00426047c2c425b66fbeb97c81ae2e3ed2e3f3c868967a1191875aafbb1d1e9c', 'paramedico',     NULL),
 (4,  'jefe_urg_h1', 'pbkdf2_sha256$260000$b0000000000000000000000000000001$71785e06b31f183302f037449220bed7bdb9d88df43e47db0c6a9b6fb5ce0f27', 'jefe_urgencias', 1),
 (5,  'jefe_urg_h2', 'pbkdf2_sha256$260000$b0000000000000000000000000000002$7bc8d159351f363a235d1de338a32546c23e2a6d4e90ca6e9343fb42d51ccbac', 'jefe_urgencias', 2),
 (6,  'jefe_urg_h3', 'pbkdf2_sha256$260000$b0000000000000000000000000000003$45cf1492b7a54653490bc999259ab75c0af82e6d2a46f5ddabfffa8c01f44a7a', 'jefe_urgencias', 3),
 (7,  'jefe_urg_h4', 'pbkdf2_sha256$260000$b0000000000000000000000000000004$c97e0cda627fb36c90efaedf2b89efb09472497429234d0e86d92f4c74b9cece', 'jefe_urgencias', 4),
 (8,  'jefe_urg_h5', 'pbkdf2_sha256$260000$b0000000000000000000000000000005$5a00cec0b3e83b54a83a7138fcd92d6d4daa93c486ffa726aee2524b27e56cdc', 'jefe_urgencias', 5),
 (9,  'jefe_urg_h6', 'pbkdf2_sha256$260000$b0000000000000000000000000000006$106ad48dfc9d24605822f29a14fc6ce6ad232bd27c6454c635e0797fa1a8d3ed', 'jefe_urgencias', 6),
 (10, 'jefe_urg_h7', 'pbkdf2_sha256$260000$b0000000000000000000000000000007$d9b069720227d4661049f7dd8c35c56c3c7eea11e3257d980a84bd32fbd6ef18', 'jefe_urgencias', 7),
 (11, 'jefe_urg_h8', 'pbkdf2_sha256$260000$b0000000000000000000000000000008$a36341c826a6a3691a90bd8609b1728d264977cae887e49fe8a734a8302e89d6', 'jefe_urgencias', 8);

-- recurso_id = hospital_id*10 + (1 cama_uci | 2 quirofano | 3 sala_choque)
-- 'reservados' coincide con las reservas vivas sembradas más abajo (recurso 12 y 21).
INSERT INTO recursos_hospitalarios (recurso_id, hospital_id, tipo_recurso, total, ocupados, reservados, actualizado_por) VALUES
 (11, 1, 'cama_uci',    12, 9, 0, 4), (12, 1, 'quirofano', 4, 2, 1, 4), (13, 1, 'sala_choque', 3, 1, 0, 4),
 (21, 2, 'cama_uci',     8, 6, 1, 5), (22, 2, 'quirofano', 3, 1, 0, 5), (23, 2, 'sala_choque', 2, 1, 0, 5),
 (31, 3, 'cama_uci',     6, 4, 0, 6), (32, 3, 'quirofano', 2, 1, 0, 6), (33, 3, 'sala_choque', 2, 0, 0, 6),
 (41, 4, 'cama_uci',     4, 4, 0, 7), (42, 4, 'quirofano', 2, 2, 0, 7), (43, 4, 'sala_choque', 1, 0, 0, 7),
 (51, 5, 'cama_uci',     5, 3, 0, 8), (52, 5, 'quirofano', 2, 0, 0, 8), (53, 5, 'sala_choque', 2, 1, 0, 8),
 (61, 6, 'cama_uci',     2, 1, 0, 9), (62, 6, 'quirofano', 1, 1, 0, 9), (63, 6, 'sala_choque', 1, 0, 0, 9),
 (71, 7, 'cama_uci',     3, 2, 0, 10), (72, 7, 'quirofano', 2, 0, 0, 10), (73, 7, 'sala_choque', 1, 0, 0, 10),
 (81, 8, 'cama_uci',     2, 0, 0, 11), (82, 8, 'quirofano', 1, 0, 0, 11), (83, 8, 'sala_choque', 1, 0, 0, 11);

INSERT INTO ambulancias (ambulancia_id, clave, tipo, base_hospital_id, estado) VALUES
 (1,  'AMB-01', 'avanzada', 1, 'en_servicio'),
 (2,  'AMB-02', 'basica',   2, 'disponible'),
 (3,  'AMB-03', 'avanzada', 2, 'en_servicio'),
 (4,  'AMB-04', 'basica',   3, 'disponible'),
 (5,  'AMB-05', 'avanzada', 4, 'disponible'),
 (6,  'AMB-06', 'basica',   5, 'disponible'),
 (7,  'AMB-07', 'avanzada', 6, 'disponible'),
 (8,  'AMB-08', 'basica',   7, 'disponible'),
 (9,  'AMB-09', 'avanzada', 8, 'fuera_servicio'),
 (10, 'AMB-10', 'basica',   1, 'disponible'),
 (11, 'AMB-11', 'avanzada', 5, 'disponible'),
 (12, 'AMB-12', 'basica',   7, 'disponible');

-- Guardia vigente (ventana sintética de 365 días para evitar caducidad en demos). Neurocirugía de HOSP-02 sin presencia: escenario de descarte.
INSERT INTO personal_guardia (personal_id, hospital_id, alias_sintetico, especialidad_codigo, turno_inicio, turno_fin, presente)
SELECT row_number() OVER (ORDER BY g.hospital_id, g.especialidad_codigo),
       g.hospital_id,
       'GUARDIA-H' || g.hospital_id || '-' || left(g.especialidad_codigo, 6),
       g.especialidad_codigo,
       now() - interval '4 hours',
       now() + interval '365 days',
       NOT (g.hospital_id = 2 AND g.especialidad_codigo = 'NEUROCIRUGIA')
FROM (VALUES
  (1,'CIRUGIA_TRAUMA'),(2,'CIRUGIA_TRAUMA'),(3,'CIRUGIA_TRAUMA'),(4,'CIRUGIA_TRAUMA'),(5,'CIRUGIA_TRAUMA'),(6,'CIRUGIA_TRAUMA'),(7,'CIRUGIA_TRAUMA'),
  (1,'ANESTESIOLOGIA'),(2,'ANESTESIOLOGIA'),(3,'ANESTESIOLOGIA'),(4,'ANESTESIOLOGIA'),(5,'ANESTESIOLOGIA'),(6,'ANESTESIOLOGIA'),(7,'ANESTESIOLOGIA'),(8,'ANESTESIOLOGIA'),
  (1,'MEDICINA_CRITICA'),(2,'MEDICINA_CRITICA'),(3,'MEDICINA_CRITICA'),(4,'MEDICINA_CRITICA'),(5,'MEDICINA_CRITICA'),
  (1,'NEUROCIRUGIA'),(2,'NEUROCIRUGIA'),
  (1,'CARDIOLOGIA_INTERVENCIONISTA'),(2,'CARDIOLOGIA_INTERVENCIONISTA'),(3,'CARDIOLOGIA_INTERVENCIONISTA'),
  (1,'TOXICOLOGIA'),(3,'TOXICOLOGIA'),(5,'TOXICOLOGIA'),
  (1,'CIRUGIA_PLASTICA')
) AS g(hospital_id, especialidad_codigo);

-- Traslados de ejemplo; frap_id = _id determinista de los FRAP sembrados en Mongo (65f0 + 20 dígitos).
INSERT INTO traslados (traslado_id, frap_id, hospital_destino_id, ambulancia_id, protocolo_codigo, estado,
                       eta_min, eta_margen_min, estado_via, data_vintage, solicitado_por) VALUES
 ('a0000000-0000-4000-8000-000000000001', '65f000000000000000000001', 1, 1, 'PT-POLITRAUMA', 'reservado',
   18.0, 5.0, 'normal', now() - interval '2 minutes', 2),
 ('a0000000-0000-4000-8000-000000000002', '65f000000000000000000002', 2, 3, 'PT-IAM', 'confirmado',
   12.0, 4.0, 'normal', now() - interval '5 minutes', 3);

INSERT INTO reservas_recurso (reserva_id, traslado_id, recurso_id, cantidad, estado, creada_en, expira_en) VALUES
 ('b0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000001', 12, 1, 'activa',
   now(), now() + interval '15 minutes'),
 ('b0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000002', 21, 1, 'confirmada',
   now() - interval '3 minutes', now() + interval '12 minutes');
