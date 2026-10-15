-- ============================================================
-- Migración: atención de urgencias / dolor agudo
-- Agrega la prioridad de atención a las citas. Las urgencias se
-- registran con 'Atención Prioritaria' (mostrada como
-- "Pendiente de Atención Prioritaria"), manteniendo estado='pendiente'.
-- Idempotente (seguro re-ejecutar).
-- ============================================================

ALTER TABLE citas ADD COLUMN IF NOT EXISTS prioridad VARCHAR(30) DEFAULT 'Normal';

-- Normaliza filas antiguas sin prioridad.
UPDATE citas SET prioridad = 'Normal' WHERE prioridad IS NULL;
