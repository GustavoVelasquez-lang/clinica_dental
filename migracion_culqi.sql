-- ============================================================
-- Migración: pago del adelanto en línea con Culqi
--
-- 1) Adelanto configurable por especialidad y por tratamiento.
--    El adelanto del tratamiento (si está definido) tiene
--    prioridad sobre el de la especialidad.
-- 2) Columnas en pagos para registrar transacciones de la pasarela.
--
-- Idempotente (seguro re-ejecutar).
-- ============================================================

-- 1) Adelanto por especialidad (monto por defecto de la cita)
ALTER TABLE especialidades ADD COLUMN IF NOT EXISTS adelanto NUMERIC(10,2) DEFAULT 0
    CHECK (adelanto >= 0);

-- 2) Adelanto específico del tratamiento (si es NULL, usa el de la especialidad)
ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS adelanto NUMERIC(10,2)
    CHECK (adelanto >= 0);

-- 3) Datos de la pasarela en pagos
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS gateway VARCHAR(20);
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS transaccion_id VARCHAR(120);
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS payload TEXT;

-- Idempotencia del webhook: evita registrar dos veces el mismo cargo.
CREATE UNIQUE INDEX IF NOT EXISTS idx_pagos_transaccion ON pagos (transaccion_id);

-- Normaliza adelantos nulos en especialidades.
UPDATE especialidades SET adelanto = 0 WHERE adelanto IS NULL;
