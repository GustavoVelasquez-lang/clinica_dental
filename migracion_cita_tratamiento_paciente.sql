-- ============================================================
-- Migración: agregar paciente_id a cita_tratamiento
--
-- Añade la referencia directa al paciente que agendó ese
-- tratamiento (útil para reportes sin JOIN con citas).
-- ============================================================

ALTER TABLE cita_tratamiento
ADD COLUMN IF NOT EXISTS paciente_id INT;

UPDATE cita_tratamiento ct
SET paciente_id = c.paciente_id
FROM citas c
WHERE c.id = ct.id_cita
  AND ct.paciente_id IS NULL;

DO $$
BEGIN
  IF NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'cita_tratamiento_paciente_id_fkey'
  ) THEN
      ALTER TABLE cita_tratamiento
        ADD CONSTRAINT cita_tratamiento_paciente_id_fkey
        FOREIGN KEY (paciente_id) REFERENCES usuarios(id);
  END IF;
END $$;
