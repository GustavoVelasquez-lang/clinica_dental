-- =====================================================
--  CLÍNICA SELEDENT · Esquema PostgreSQL para Supabase
--  Pegar en: Supabase Dashboard → SQL Editor → New query
-- =====================================================

-- Extensión uuid (opcional, por defecto suele estar activa)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------
-- TABLAS (orden según dependencias)
-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS roles (
    id     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(30) UNIQUE,
    estado VARCHAR(10) DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo'))
);

CREATE TABLE IF NOT EXISTS especialidades (
    id          INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre      VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    estado      VARCHAR(10) DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo'))
);

CREATE TABLE IF NOT EXISTS usuarios (
    id              INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo_documento  VARCHAR(20) NOT NULL CHECK (tipo_documento IN ('DNI', 'C.E.', 'Pasaporte')),
    numero_documento VARCHAR(20) NOT NULL UNIQUE,
    nombre          VARCHAR(100) NOT NULL,
    apepaterno      VARCHAR(100),
    apematerno      VARCHAR(100),
    fenacimiento    DATE,
    correo          VARCHAR(255) NOT NULL UNIQUE,
    contrasenia     VARCHAR(255) NOT NULL,
    estado          VARCHAR(10) DEFAULT 'ACTIVO' CHECK (estado IN ('ACTIVO', 'INACTIVO')),
    fecha_registro  TIMESTAMP DEFAULT now(),
    id_rol          INT REFERENCES roles (id)
);

CREATE TABLE IF NOT EXISTS citas (
    id             INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    paciente_id    INT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    odontologo_id  INT REFERENCES usuarios (id) ON DELETE SET NULL,
    especialidad_id INT NOT NULL REFERENCES especialidades (id) ON DELETE CASCADE,
    fecha          DATE NOT NULL,
    hora           TIME NOT NULL,
    comprobante    VARCHAR(255),
    estado         VARCHAR(20) DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'confirmada', 'cancelada', 'atendida')),
    adelanto       NUMERIC(10,2) DEFAULT 0.00,
    estado_pago    VARCHAR(20) DEFAULT 'pendiente' CHECK (estado_pago IN ('pendiente', 'adelanto', 'pagado')),
    observaciones  TEXT,
    UNIQUE (odontologo_id, fecha, hora)
);

CREATE TABLE IF NOT EXISTS recordatorios (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cita_id    INT NOT NULL REFERENCES citas (id) ON DELETE CASCADE,
    dias_antes INT NOT NULL,
    enviado    TIMESTAMP DEFAULT now(),
    CONSTRAINT unique_recordatorio UNIQUE (cita_id, dias_antes)
);

CREATE TABLE IF NOT EXISTS pagos (
    id      INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cita INT NOT NULL REFERENCES citas (id) ON DELETE CASCADE,
    monto   NUMERIC(10,2) NOT NULL,
    tipo    VARCHAR(20) NOT NULL CHECK (tipo IN ('adelanto', 'completo')),
    fecha   TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS metodos_pago (
    id_metodo_pago INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre         VARCHAR(50) UNIQUE
);

CREATE TABLE IF NOT EXISTS comprobantes_pago (
    id             INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_pago        INT NOT NULL REFERENCES pagos (id),
    codigo         VARCHAR(50) UNIQUE,
    paciente_id    INT REFERENCES usuarios (id),
    monto          NUMERIC(10,2),
    estado         VARCHAR(10) DEFAULT 'valido' CHECK (estado IN ('valido', 'anulado')),
    fecha          TIMESTAMP DEFAULT now(),
    id_metodo_pago INT REFERENCES metodos_pago (id_metodo_pago)
);

CREATE TABLE IF NOT EXISTS tratamientos (
    id_tratamiento  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_especialidad INT NOT NULL REFERENCES especialidades (id) ON DELETE CASCADE,
    nombre          VARCHAR(100) NOT NULL,
    descripcion     TEXT,
    precio_base     NUMERIC(10,2),
    UNIQUE (nombre, id_especialidad)
);

CREATE TABLE IF NOT EXISTS historial_clinico (
    id                   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    paciente_id          INT NOT NULL REFERENCES usuarios (id),
    odontologo_id        INT REFERENCES usuarios (id),
    cita_id              INT REFERENCES citas (id),
    fecha                TIMESTAMP DEFAULT now(),
    motivo_consulta      TEXT,
    diagnostico          TEXT,
    plan_tratamiento     TEXT,
    tratamiento_realizado TEXT,
    odontograma          TEXT,
    alergias             TEXT,
    enfermedades         TEXT,
    observaciones        TEXT
);

CREATE TABLE IF NOT EXISTS horarios (
    id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    odontologo_id INT REFERENCES usuarios (id),
    dia_semana    VARCHAR(20) CHECK (dia_semana IN ('Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes')),
    hora_inicio   TIME,
    hora_fin      TIME,
    UNIQUE (odontologo_id, dia_semana, hora_inicio)
);

CREATE TABLE IF NOT EXISTS cita_tratamiento (
    id             INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cita        INT NOT NULL REFERENCES citas (id) ON DELETE CASCADE,
    id_tratamiento INT NOT NULL REFERENCES tratamientos (id_tratamiento) ON DELETE CASCADE,
    precio_aplicado NUMERIC(10,2)
);

CREATE TABLE IF NOT EXISTS odontologo_especialidad (
    id             INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    odontologo_id  INT REFERENCES usuarios (id),
    especialidad_id INT REFERENCES especialidades (id),
    estado         VARCHAR(10) DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo'))
);

-- -----------------------------------------------------
-- DATOS REFERENCIALES
-- -----------------------------------------------------

INSERT INTO roles (nombre) VALUES
    ('admin'),
    ('paciente')
ON CONFLICT DO NOTHING;

INSERT INTO especialidades (nombre, estado) VALUES
    ('Ortodoncia', 'activo'),
    ('Endodoncia', 'activo'),
    ('Odontología General', 'activo'),
    ('Cirugía Oral', 'activo'),
    ('Implantología', 'activo'),
    ('Periodoncia', 'activo'),
    ('Estética Dental', 'activo')
ON CONFLICT (nombre) DO NOTHING;

INSERT INTO metodos_pago (nombre) VALUES
    ('Yape'),
    ('Efectivo')
ON CONFLICT DO NOTHING;

-- Admin inicial (contraseña: Admin123! — cámbiala al primer ingreso)
INSERT INTO usuarios (
    tipo_documento, numero_documento, nombre, apepaterno, apematerno,
    correo, contrasenia, estado, id_rol
) VALUES (
    'DNI', '60008335', 'GUSTAVO JAVIER', NULL, NULL,
    'gustavo.gitvc14@gmail.com',
    '$2b$12$pPmYOC14af3f4iJNan/xt.pfBAVM4UVsSa1pePb9zNYgrac5BKFp6',
    'ACTIVO', 1
)
ON CONFLICT DO NOTHING;