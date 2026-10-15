-- ============================================================
-- Migración: datos de pago/ejecución en cita_tratamiento
--
-- Agrega a la tabla puente cita_tratamiento:
--   1) precio_aplicado  -> precio_base del tratamiento al agendar.
--   2) fecha_ejecucion  -> cuándo se registra el tratamiento.
--   3) comprobante_pago -> imagen del comprobante de pago (ruta).
--
-- Idempotente (seguro re-ejecutar).
-- ============================================================

ALTER TABLE cita_tratamiento ADD COLUMN IF NOT EXISTS precio_aplicado NUMERIC(10,2)
    CHECK (precio_aplicado >= 0);

ALTER TABLE cita_tratamiento ADD COLUMN IF NOT EXISTS fecha_ejecucion TIMESTAMP;

ALTER TABLE cita_tratamiento ADD COLUMN IF NOT EXISTS comprobante_pago VARCHAR(255);
