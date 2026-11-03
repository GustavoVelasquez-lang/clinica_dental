-- ============================================================
-- Citas eliminadas (soft delete desde el panel admin)
-- Clinica SELEDENT
-- ============================================================
-- El botón "tacho rojo" de Admin → Citas ahora guarda una copia
-- de la cita en `citas_eliminadas` antes de borrarla de `citas`,
-- y el filtro "Eliminadas" lee de esta tabla.
--
-- Este script:
--   1. Crea la tabla `citas_eliminadas` (idempotente).
--   2. Crea un índice por fecha de eliminación.
--   3. Reconstruye (backfill) las eliminaciones antiguas usando la
--      tabla `auditoria` (accion = 'eliminar_cita', detalle = 'cita #N').
--      Solo se recupera el ID y la fecha; el resto queda en NULL porque
--      la fila original ya no existe.
-- ============================================================

BEGIN;

-- 1. Tabla
CREATE TABLE IF NOT EXISTS citas_eliminadas (
    id SERIAL PRIMARY KEY,
    cita_id INT NOT NULL,
    paciente VARCHAR(200),
    correo VARCHAR(150),
    especialidad VARCHAR(120),
    tratamiento VARCHAR(200),
    tipo_atencion VARCHAR(80),
    fecha DATE,
    hora TIME,
    monto_total NUMERIC(10,2),
    adelanto NUMERIC(10,2),
    estado VARCHAR(30),
    estado_pago VARCHAR(40),
    eliminada_por INT,
    eliminada_en TIMESTAMP DEFAULT NOW()
);

-- 2. Índice para ordenar el listado por fecha de eliminación
CREATE INDEX IF NOT EXISTS idx_citas_eliminadas_fecha
    ON citas_eliminadas(eliminada_en DESC);

-- 3. Backfill desde auditoría
--    DISTINCT ON conserva solo la última eliminación registrada por cita.
--    NOT EXISTS evita duplicar las que ya guardó el código nuevo.
INSERT INTO citas_eliminadas (cita_id, eliminada_por, eliminada_en)
SELECT a.cita_id, a.usuario_id, a.created_at
FROM (
    SELECT DISTINCT ON (NULLIF(regexp_replace(detalle, '\D', '', 'g'), '')::int)
           NULLIF(regexp_replace(detalle, '\D', '', 'g'), '')::int AS cita_id,
           usuario_id,
           created_at
    FROM auditoria
    WHERE accion = 'eliminar_cita'
      AND detalle ~ 'cita #[0-9]+'
    ORDER BY NULLIF(regexp_replace(detalle, '\D', '', 'g'), '')::int,
             created_at DESC
) AS a
WHERE a.cita_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM citas c WHERE c.id = a.cita_id
  )
  AND NOT EXISTS (
      SELECT 1 FROM citas_eliminadas ce WHERE ce.cita_id = a.cita_id
  );

COMMIT;

-- ============================================================
-- VERIFICACION (ejecutar aparte si se desea):
--   SELECT COUNT(*) FROM citas_eliminadas;
--   SELECT cita_id, eliminada_en FROM citas_eliminadas ORDER BY eliminada_en DESC LIMIT 10;
-- ============================================================
