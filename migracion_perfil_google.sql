-- ============================================================
-- Migración: perfil de paciente y login con Google
-- Agrega teléfono y la bandera perfil_completo a usuarios.
-- Idempotente (seguro re-ejecutar).
-- ============================================================

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telefono VARCHAR(30);

-- Perfil completo por defecto para no bloquear cuentas existentes.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS perfil_completo BOOLEAN DEFAULT TRUE;

UPDATE usuarios SET perfil_completo = TRUE WHERE perfil_completo IS NULL;
