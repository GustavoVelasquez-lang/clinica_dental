-- ============================================================
-- Migración: gestión de familiares (dependientes) desde el panel
--
-- La tabla `dependientes` ya existía para el módulo del paciente
-- (/familiares). Se reutiliza tal cual para que el ADMIN gestione
-- los familiares de cada titular desde /admin/pacientes.
--
-- Se agregan dos columnas de compatibilidad que pudieran faltar en
-- instalaciones previas. Las citas agendadas "para un familiar" ya
-- se vinculan mediante citas.dependiente_id.
-- ============================================================

ALTER TABLE dependientes
ADD COLUMN IF NOT EXISTS parentesco VARCHAR(30);

ALTER TABLE dependientes
ADD COLUMN IF NOT EXISTS observaciones TEXT;

-- Citas: a quién corresponde la cita (NULL = titular de la cuenta).
ALTER TABLE citas ADD COLUMN IF NOT EXISTS dependiente_id INT
    REFERENCES dependientes(id)
    ON DELETE SET NULL;
