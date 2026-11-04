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
--   3. Agrega las columnas del historial de restauración.
--
-- NOTA: las eliminaciones antiguas (anteriores a este módulo) NO se
-- recuperan. Solo existía el registro de auditoría ("cita #N") y esos
-- registros no tienen paciente ni montos, así que se descartaron para
-- no mostrar filas vacías en el filtro "Eliminadas".
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
    eliminada_en TIMESTAMP DEFAULT NOW(),
    restaurada_en TIMESTAMP,
    restaurada_por INT
);

-- 1b. Columnas de historial de restauración (para tablas ya existentes)
ALTER TABLE citas_eliminadas ADD COLUMN IF NOT EXISTS restaurada_en TIMESTAMP;
ALTER TABLE citas_eliminadas ADD COLUMN IF NOT EXISTS restaurada_por INT;

-- 2. Índice para ordenar el listado por fecha de eliminación
CREATE INDEX IF NOT EXISTS idx_citas_eliminadas_fecha
    ON citas_eliminadas(eliminada_en DESC);

-- 3. (Sin backfill) Las eliminaciones antiguas no se recuperan.

COMMIT;

-- ============================================================
-- VERIFICACION (ejecutar aparte si se desea):
--   SELECT COUNT(*) FROM citas_eliminadas;
--   SELECT cita_id, eliminada_en FROM citas_eliminadas ORDER BY eliminada_en DESC LIMIT 10;
-- ============================================================
