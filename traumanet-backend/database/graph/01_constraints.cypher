// Restricciones e índices del grafo (idempotentes). Neo4j Community: solo unicidad de nodos.
CREATE CONSTRAINT hospital_id_unico IF NOT EXISTS FOR (h:Hospital) REQUIRE h.hospital_id IS UNIQUE;
CREATE CONSTRAINT especialidad_codigo_unico IF NOT EXISTS FOR (e:Especialidad) REQUIRE e.codigo IS UNIQUE;
CREATE CONSTRAINT equipo_codigo_unico IF NOT EXISTS FOR (q:EquipoBiomedico) REQUIRE q.codigo IS UNIQUE;
CREATE CONSTRAINT protocolo_codigo_unico IF NOT EXISTS FOR (p:ProtocoloTrauma) REQUIRE p.codigo IS UNIQUE;
