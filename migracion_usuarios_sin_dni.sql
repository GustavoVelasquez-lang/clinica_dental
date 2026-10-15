-- ============================================================
-- Migración: registro de usuarios sin DNI (login por correo)
-- Hace opcionales tipo_documento y numero_documento.
-- ============================================================

ALTER TABLE usuarios ALTER COLUMN tipo_documento DROP NOT NULL;
ALTER TABLE usuarios ALTER COLUMN numero_documento DROP NOT NULL;
