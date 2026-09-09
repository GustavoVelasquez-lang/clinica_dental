-- ─────────────────────────────────────────────────
-- Migración: Crear tabla de recordatorios
-- ─────────────────────────────────────────────────
-- Ejecutar en phpMyAdmin o consola MySQL:
--   SOURCE migracion_recordatorios.sql
-- O copiar y pegar en la pestaña SQL de sele_dent
-- ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS recordatorios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cita_id INT NOT NULL,
    dias_antes INT NOT NULL COMMENT '3, 2 o 1 dia(s) antes de la cita',
    enviado DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cita_id) REFERENCES citas(id) ON DELETE CASCADE,
    UNIQUE KEY unique_recordatorio (cita_id, dias_antes)
);
