-- ============================================================
--  Migracion: recuperacion de contrasena con codigo por correo
--  Crea la tabla codigos_recuperacion.
-- ============================================================

CREATE TABLE IF NOT EXISTS codigos_recuperacion (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    correo VARCHAR(255) NOT NULL,

    codigo VARCHAR(6) NOT NULL,

    expira TIMESTAMP NOT NULL,

    usado BOOLEAN DEFAULT FALSE,

    fecha_creacion TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_codigos_recuperacion_correo
    ON codigos_recuperacion(correo);
