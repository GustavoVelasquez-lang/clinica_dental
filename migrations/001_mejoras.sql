-- ════════════════════════════════════════════════════════════
-- Migracion: Mejoras de seguridad, features y Google Calendar
-- Ejecutar en la BD PostgreSQL (Supabase)
-- ════════════════════════════════════════════════════════════

-- Tabla de auditoria
CREATE TABLE IF NOT EXISTS auditoria (
    id SERIAL PRIMARY KEY,
    usuario_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
    accion VARCHAR(100) NOT NULL,
    detalle TEXT,
    ip VARCHAR(45),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Columnas nuevas en citas
ALTER TABLE citas ADD COLUMN IF NOT EXISTS odontologo_id INT REFERENCES usuarios(id) ON DELETE SET NULL;
ALTER TABLE citas ADD COLUMN IF NOT EXISTS mensaje TEXT;
ALTER TABLE citas ADD COLUMN IF NOT EXISTS diagnostico TEXT;
ALTER TABLE citas ADD COLUMN IF NOT EXISTS observaciones TEXT;
ALTER TABLE citas ADD COLUMN IF NOT EXISTS google_event_id VARCHAR(255);

-- Tabla horarios (si no existe)
CREATE TABLE IF NOT EXISTS horarios (
    id SERIAL PRIMARY KEY,
    odontologo_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    dia_semana INT NOT NULL CHECK (dia_semana >= 0 AND dia_semana <= 6),
    hora_inicio TIME NOT NULL,
    hora_fin TIME NOT NULL,
    UNIQUE (odontologo_id, dia_semana, hora_inicio)
);

-- Tabla historial clinico (si no existe)
CREATE TABLE IF NOT EXISTS historial_clinico (
    id SERIAL PRIMARY KEY,
    paciente_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    cita_id INT REFERENCES citas(id) ON DELETE SET NULL,
    fecha TIMESTAMP DEFAULT NOW(),
    diagnostico TEXT NOT NULL,
    observaciones TEXT,
    tratamiento TEXT
);

-- Tabla odontologo_especialidad (si no existe)
CREATE TABLE IF NOT EXISTS odontologo_especialidad (
    odontologo_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    especialidad_id INT NOT NULL REFERENCES especialidades(id) ON DELETE CASCADE,
    PRIMARY KEY (odontologo_id, especialidad_id)
);

-- Tabla recordatorios (si no existe)
CREATE TABLE IF NOT EXISTS recordatorios (
    id SERIAL PRIMARY KEY,
    cita_id INT NOT NULL REFERENCES citas(id) ON DELETE CASCADE,
    dias_antes INT NOT NULL,
    enviado TIMESTAMP DEFAULT now(),
    CONSTRAINT unique_recordatorio UNIQUE (cita_id, dias_antes)
);

-- Rol 3 para odontologos (si no existe)
INSERT INTO roles (id, nombre) VALUES (3, 'odontologo')
ON CONFLICT (id) DO NOTHING;

-- Columna estado en especialidades (si no existe)
ALTER TABLE especialidades ADD COLUMN IF NOT EXISTS estado VARCHAR(20) DEFAULT 'activo';

-- Indices para performance
CREATE INDEX IF NOT EXISTS idx_citas_fecha ON citas(fecha);
CREATE INDEX IF NOT EXISTS idx_citas_estado ON citas(estado);
CREATE INDEX IF NOT EXISTS idx_citas_paciente ON citas(paciente_id);
CREATE INDEX IF NOT EXISTS idx_citas_odontologo ON citas(odontologo_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria(created_at);
CREATE INDEX IF NOT EXISTS idx_usuarios_documento ON usuarios(numero_documento);
