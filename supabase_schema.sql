-- ============================================================
-- BASE DE DATOS - SELE DENT
-- SISTEMA DE GESTIÓN DE CLÍNICA ODONTOLÓGICA
-- POSTGRESQL + KPIs
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ============================================================
-- 1. TABLA ROLES
-- ============================================================

CREATE TABLE IF NOT EXISTS roles (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(30) UNIQUE NOT NULL,
    estado VARCHAR(10) DEFAULT 'activo'
        CHECK (estado IN ('activo', 'inactivo'))
);


-- ============================================================
-- 2. TABLA ESPECIALIDADES
-- ============================================================

CREATE TABLE IF NOT EXISTS especialidades (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    -- NUEVO: monto de adelanto por defecto para citas de esta especialidad
    adelanto NUMERIC(10,2) DEFAULT 0
        CHECK (adelanto >= 0),
    estado VARCHAR(10) DEFAULT 'activo'
        CHECK (estado IN ('activo', 'inactivo'))
);

-- Compatibilidad con tablas ya creadas (columna nueva)
ALTER TABLE especialidades ADD COLUMN IF NOT EXISTS adelanto NUMERIC(10,2) DEFAULT 0
    CHECK (adelanto >= 0);


-- ============================================================
-- 3. TABLA USUARIOS
-- ============================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    tipo_documento VARCHAR(20)
        CHECK (tipo_documento IN ('DNI', 'C.E.', 'Pasaporte')),

    numero_documento VARCHAR(20) UNIQUE,

    nombre VARCHAR(100) NOT NULL,

    apepaterno VARCHAR(100),

    apematerno VARCHAR(100),

    fenacimiento DATE,

    correo VARCHAR(255) NOT NULL UNIQUE,

    contrasenia VARCHAR(255) NOT NULL,

    telefono VARCHAR(30),

    perfil_completo BOOLEAN DEFAULT TRUE,

    estado VARCHAR(10) DEFAULT 'ACTIVO'
        CHECK (estado IN ('ACTIVO', 'INACTIVO')),

    fecha_registro TIMESTAMP DEFAULT now(),

    id_rol INT REFERENCES roles(id)
);


-- ============================================================
-- 4. TABLA CITAS
-- ============================================================

CREATE TABLE IF NOT EXISTS citas (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    paciente_id INT NOT NULL
        REFERENCES usuarios(id)
        ON DELETE CASCADE,

    odontologo_id INT
        REFERENCES usuarios(id)
        ON DELETE SET NULL,

    especialidad_id INT NOT NULL
        REFERENCES especialidades(id)
        ON DELETE CASCADE,

    fecha DATE NOT NULL,

    hora TIME NOT NULL,

    comprobante VARCHAR(255),

    estado VARCHAR(20) DEFAULT 'pendiente'
        CHECK (
            estado IN (
                'pendiente',
                'confirmada',
                'cancelada',
                'atendida'
            )
        ),

    adelanto NUMERIC(10,2) DEFAULT 0.00,

    -- NUEVO: total a cobrar de la cita (precio del tratamiento). El saldo
    -- restante se calcula: monto_total - SUM(pagos válidos de la cita).
    monto_total NUMERIC(10,2),

    estado_pago VARCHAR(30) DEFAULT 'pendiente'
        CHECK (
            estado_pago IN (
                'pendiente',
                'adelanto',
                'pagado',
                'rechazado',
                'pendiente_verificacion',
                'pagado_total'
            )
        ),

    -- NUEVO: pago por Yape directo (voucher + N° de operación)
    metodo_pago VARCHAR(30),
    nro_operacion VARCHAR(50),
    voucher_url TEXT,

    -- NUEVO: modalidad elegida por el paciente en la pantalla de pago
    -- ('adelanto' = solo reserva; 'completo' = tratamiento completo)
    modalidad_pago VARCHAR(20),

    observaciones TEXT,

    -- NUEVO: tipo de atención solicitada
    tipo_atencion VARCHAR(100),

    -- NUEVO: permite medir cuándo fue creada la cita
    fecha_creacion TIMESTAMP DEFAULT now(),

    -- NUEVO: permite medir cuándo fue atendida
    fecha_atencion TIMESTAMP,

    -- NUEVO: permite analizar motivos de cancelación
    motivo_cancelacion TEXT,

    -- NUEVO: sede donde se atenderá la cita
    sede VARCHAR(150) DEFAULT 'Sede Principal - El Tambo, Huancayo',

    -- NUEVO: prioridad de atención (urgencias => 'Atención Prioritaria')
    prioridad VARCHAR(30) DEFAULT 'Normal',

    UNIQUE (odontologo_id, fecha, hora)
);


-- Compatibilidad con tablas ya creadas (columnas nuevas)
ALTER TABLE citas ADD COLUMN IF NOT EXISTS tipo_atencion VARCHAR(100);
ALTER TABLE citas ADD COLUMN IF NOT EXISTS fecha_creacion TIMESTAMP DEFAULT now();
ALTER TABLE citas ADD COLUMN IF NOT EXISTS fecha_atencion TIMESTAMP;
ALTER TABLE citas ADD COLUMN IF NOT EXISTS motivo_cancelacion TEXT;
ALTER TABLE citas ADD COLUMN IF NOT EXISTS sede VARCHAR(150) DEFAULT 'Sede Principal - El Tambo, Huancayo';
ALTER TABLE citas ADD COLUMN IF NOT EXISTS prioridad VARCHAR(30) DEFAULT 'Normal';

-- NUEVO: pago por Yape directo (voucher + N° de operación)
ALTER TABLE citas ADD COLUMN IF NOT EXISTS metodo_pago VARCHAR(30);
ALTER TABLE citas ADD COLUMN IF NOT EXISTS nro_operacion VARCHAR(50);
ALTER TABLE citas ADD COLUMN IF NOT EXISTS voucher_url TEXT;

-- NUEVO: total a cobrar de la cita (cobro del saldo en caja)
ALTER TABLE citas ADD COLUMN IF NOT EXISTS monto_total NUMERIC(10,2);

-- NUEVO: modalidad de pago elegida por el paciente en la pantalla de pago
ALTER TABLE citas ADD COLUMN IF NOT EXISTS modalidad_pago VARCHAR(20);

-- 'pendiente_verificacion' (22 chars) excede VARCHAR(20): ampliar la columna.
ALTER TABLE citas ALTER COLUMN estado_pago TYPE VARCHAR(30);

-- Reemplaza el CHECK de estado_pago para admitir 'pendiente_verificacion'.
DO $$
DECLARE c record;
BEGIN
    FOR c IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'citas'::regclass AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%estado_pago%'
    LOOP
        EXECUTE format('ALTER TABLE citas DROP CONSTRAINT %I', c.conname);
    END LOOP;
    ALTER TABLE citas ADD CONSTRAINT citas_estado_pago_check
        CHECK (estado_pago IN (
            'pendiente', 'adelanto', 'pagado',
            'rechazado', 'pendiente_verificacion',
            'pagado_total'
        ));
END $$;


-- ============================================================
-- 4b. DEPENDIENTES / FAMILIARES A CARGO DEL TITULAR
-- ============================================================

CREATE TABLE IF NOT EXISTS dependientes (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    titular_id INT NOT NULL
        REFERENCES usuarios(id)
        ON DELETE CASCADE,

    dni VARCHAR(20),

    nombres VARCHAR(100) NOT NULL,

    apellidos VARCHAR(100) NOT NULL,

    fenacimiento DATE,

    parentesco VARCHAR(30),

    observaciones TEXT,

    fecha_registro TIMESTAMP DEFAULT now()
);

-- Citas: a quién corresponde la cita (NULL = titular de la cuenta).
ALTER TABLE citas ADD COLUMN IF NOT EXISTS dependiente_id INT
    REFERENCES dependientes(id)
    ON DELETE SET NULL;


-- ============================================================
-- 5. RECORDATORIOS
-- ============================================================

CREATE TABLE IF NOT EXISTS recordatorios (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cita_id INT NOT NULL
        REFERENCES citas(id)
        ON DELETE CASCADE,

    dias_antes INT NOT NULL,

    enviado TIMESTAMP DEFAULT now(),

    CONSTRAINT unique_recordatorio
        UNIQUE (cita_id, dias_antes)
);


-- ============================================================
-- 6. PAGOS
-- ============================================================

CREATE TABLE IF NOT EXISTS pagos (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    id_cita INT NOT NULL
        REFERENCES citas(id)
        ON DELETE CASCADE,

    monto NUMERIC(10,2) NOT NULL
        CHECK (monto >= 0),

    tipo VARCHAR(20) NOT NULL
        CHECK (tipo IN ('adelanto', 'completo')),

    fecha TIMESTAMP DEFAULT now(),

    id_metodo_pago INT,

    estado VARCHAR(10) DEFAULT 'valido'
        CHECK (estado IN ('valido', 'anulado')),

    -- NUEVO: pago en línea (pasarela Culqi)
    gateway VARCHAR(20),
    transaccion_id VARCHAR(120),
    payload TEXT
);

-- Compatibilidad con tablas ya creadas (columnas nuevas)
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS id_metodo_pago INT;
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS estado VARCHAR(10) DEFAULT 'valido'
    CHECK (estado IN ('valido', 'anulado'));
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS gateway VARCHAR(20);
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS transaccion_id VARCHAR(120);
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS payload TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_pagos_transaccion ON pagos (transaccion_id);


-- ============================================================
-- 7. MÉTODOS DE PAGO
-- ============================================================

CREATE TABLE IF NOT EXISTS metodos_pago (
    id_metodo_pago INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    nombre VARCHAR(50) UNIQUE NOT NULL
);


-- ============================================================
-- 8. AGREGAR FK DE MÉTODO DE PAGO
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_pagos_metodo'
    ) THEN

        ALTER TABLE pagos
        ADD CONSTRAINT fk_pagos_metodo
        FOREIGN KEY (id_metodo_pago)
        REFERENCES metodos_pago(id_metodo_pago);

    END IF;
END $$;


-- ============================================================
-- 9. COMPROBANTES DE PAGO
-- ============================================================

CREATE TABLE IF NOT EXISTS comprobantes_pago (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    id_pago INT NOT NULL
        REFERENCES pagos(id),

    codigo VARCHAR(50) UNIQUE,

    paciente_id INT
        REFERENCES usuarios(id),

    monto NUMERIC(10,2),

    estado VARCHAR(10) DEFAULT 'valido'
        CHECK (estado IN ('valido', 'anulado')),

    fecha TIMESTAMP DEFAULT now(),

    id_metodo_pago INT
        REFERENCES metodos_pago(id_metodo_pago)
);


-- ============================================================
-- 10. TRATAMIENTOS
-- ============================================================

CREATE TABLE IF NOT EXISTS tratamientos (
    id_tratamiento INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    id_especialidad INT NOT NULL
        REFERENCES especialidades(id)
        ON DELETE CASCADE,

    nombre VARCHAR(100) NOT NULL,

    descripcion TEXT,

    precio_base NUMERIC(10,2)
        CHECK (precio_base >= 0),

    -- NUEVO: adelanto específico del tratamiento (si es NULL, usa el de la especialidad)
    adelanto NUMERIC(10,2)
        CHECK (adelanto >= 0),

    UNIQUE (nombre, id_especialidad)
);

-- Compatibilidad con tablas ya creadas (columna nueva)
ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS adelanto NUMERIC(10,2)
    CHECK (adelanto >= 0);


-- ============================================================
-- 11. HISTORIAL CLÍNICO
-- ============================================================

CREATE TABLE IF NOT EXISTS historial_clinico (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    paciente_id INT NOT NULL
        REFERENCES usuarios(id),

    odontologo_id INT
        REFERENCES usuarios(id),

    cita_id INT
        REFERENCES citas(id),

    fecha TIMESTAMP DEFAULT now(),

    motivo_consulta TEXT,

    diagnostico TEXT,

    plan_tratamiento TEXT,

    tratamiento_realizado TEXT,

    odontograma TEXT,

    alergias TEXT,

    enfermedades TEXT,

    observaciones TEXT
);


-- ============================================================
-- 12. HORARIOS
-- ============================================================

CREATE TABLE IF NOT EXISTS horarios (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    odontologo_id INT
        REFERENCES usuarios(id),

    dia_semana VARCHAR(20)
        CHECK (
            dia_semana IN (
                'Lunes',
                'Martes',
                'Miercoles',
                'Jueves',
                'Viernes'
            )
        ),

    hora_inicio TIME,

    hora_fin TIME,

    UNIQUE (
        odontologo_id,
        dia_semana,
        hora_inicio
    )
);


-- ============================================================
-- 13. CITA - TRATAMIENTO
-- ============================================================

CREATE TABLE IF NOT EXISTS cita_tratamiento (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    id_cita INT NOT NULL
        REFERENCES citas(id)
        ON DELETE CASCADE,

    id_tratamiento INT NOT NULL
        REFERENCES tratamientos(id_tratamiento)
        ON DELETE CASCADE,

    precio_aplicado NUMERIC(10,2)
        CHECK (precio_aplicado >= 0),

    -- NUEVO: fecha en que se registra/ejecuta el tratamiento
    fecha_ejecucion TIMESTAMP,

    -- NUEVO: imagen del comprobante de pago (ruta relativa)
    comprobante_pago VARCHAR(255),

    -- NUEVO: paciente que agendó este tratamiento (FK directa)
    paciente_id INT REFERENCES usuarios(id)
);

-- Compatibilidad con tablas ya creadas (columnas nuevas)
ALTER TABLE cita_tratamiento ADD COLUMN IF NOT EXISTS fecha_ejecucion TIMESTAMP;
ALTER TABLE cita_tratamiento ADD COLUMN IF NOT EXISTS comprobante_pago VARCHAR(255);
ALTER TABLE cita_tratamiento ADD COLUMN IF NOT EXISTS paciente_id INT;
ALTER TABLE cita_tratamiento ADD CONSTRAINT cita_tratamiento_paciente_id_fkey
  FOREIGN KEY (paciente_id) REFERENCES usuarios(id);


-- ============================================================
-- 14. ODONTÓLOGO - ESPECIALIDAD
-- ============================================================

CREATE TABLE IF NOT EXISTS odontologo_especialidad (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    odontologo_id INT
        REFERENCES usuarios(id),

    especialidad_id INT
        REFERENCES especialidades(id),

    estado VARCHAR(10) DEFAULT 'activo'
        CHECK (estado IN ('activo', 'inactivo')),

    UNIQUE (
        odontologo_id,
        especialidad_id
    )
);


-- ============================================================
-- 15. INVENTARIO
-- ============================================================

CREATE TABLE IF NOT EXISTS inventario (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    nombre VARCHAR(150) NOT NULL,

    categoria VARCHAR(50),

    cantidad INT DEFAULT 0
        CHECK (cantidad >= 0),

    stock_minimo INT DEFAULT 0
        CHECK (stock_minimo >= 0),

    precio_compra NUMERIC(10,2)
        CHECK (precio_compra >= 0),

    proveedor VARCHAR(100),

    fecha_actualizacion TIMESTAMP DEFAULT now()
);


-- ============================================================
-- 16. TABLA DE METAS DE KPIs
-- ============================================================

CREATE TABLE IF NOT EXISTS metas_kpi (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    objetivo VARCHAR(150) NOT NULL UNIQUE,

    nombre_kpi VARCHAR(100) NOT NULL,

    descripcion TEXT,

    meta NUMERIC(10,2) NOT NULL,

    unidad VARCHAR(30),

    estado VARCHAR(10) DEFAULT 'activo'
        CHECK (estado IN ('activo', 'inactivo')),

    fecha_registro TIMESTAMP DEFAULT now()
);

-- Compatibilidad con tablas ya creadas (columna nueva)
ALTER TABLE metas_kpi ADD COLUMN IF NOT EXISTS objetivo VARCHAR(150);
ALTER TABLE metas_kpi ADD COLUMN IF NOT EXISTS nombre_kpi VARCHAR(100);
UPDATE metas_kpi SET nombre_kpi = 'KPI del objetivo' WHERE nombre_kpi IS NULL;


-- ============================================================
-- 17. TABLA DE MENSAJES DE CONTACTO
-- ============================================================

CREATE TABLE IF NOT EXISTS mensajes_contacto (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    nombre VARCHAR(120) NOT NULL,

    email VARCHAR(150) NOT NULL,

    telefono VARCHAR(30),

    asunto VARCHAR(60) NOT NULL
        CHECK (asunto IN (
            'Consulta general',
            'Agendamiento de citas',
            'Presupuesto/Tratamientos',
            'Reclamaciones'
        )),

    mensaje TEXT NOT NULL,

    fecha_envio TIMESTAMP DEFAULT now(),

    leido BOOLEAN DEFAULT FALSE
);

-- Indice para el panel: mensajes nuevos primero y luego por fecha
CREATE INDEX IF NOT EXISTS idx_mensajes_contacto_leido
    ON mensajes_contacto (leido, fecha_envio DESC);


-- ============================================================
-- 17b. TABLA CODIGOS_RECUPERACION
--      Codigos de un solo uso enviados por correo para
--      restablecer la contrasena.
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


-- ============================================================
-- 18. DATOS REFERENCIALES
-- ============================================================

INSERT INTO roles (nombre)
VALUES
    ('admin'),
    ('odontologo'),
    ('dentista'),
    ('paciente')
ON CONFLICT (nombre) DO NOTHING;


INSERT INTO especialidades (nombre, descripcion, estado)
VALUES
    ('Ortodoncia', 'Alineamos tus dientes con brackets y alineadores para lograr una sonrisa armoniosa.', 'activo'),
    ('Endodoncia', 'Tratamiento de conductos que salva piezas dentales infectadas o muy dañadas.', 'activo'),
    ('Odontología General', 'Prevención, diagnóstico y tratamiento integral de tu salud bucal.', 'activo'),
    ('Cirugía Oral', 'Extracciones y procedimientos quirúrgicos de la cavidad oral con máxima seguridad.', 'activo'),
    ('Implantología', 'Reemplazamos piezas dentales perdidas con implantes de titanio de alta durabilidad.', 'activo'),
    ('Periodoncia', 'Cuidamos tus encías y los tejidos que sostienen firmemente tus dientes.', 'activo'),
    ('Estética Dental', 'Mejoramos tu sonrisa con blanqueamiento, carillas y diseños personalizados.', 'activo'),
    ('Odontopediatría', 'Atención dental especializada para niños y adolescentes, con un trato cercano y sin miedo.', 'activo'),
    ('Rehabilitación Oral', 'Restauración de la función y estética mediante coronas y prótesis a medida.', 'activo'),
    ('Radiología e Imagen 3D', 'Tomografías y escaneo intraoral de alta precisión para un diagnóstico exacto.', 'activo'),
    ('Urgencias Odontológicas', 'Atención rápida ante dolores agudos y traumatismos dentales.', 'activo')
ON CONFLICT (nombre) DO NOTHING;


INSERT INTO metodos_pago (nombre)
VALUES
    ('Yape'),
    ('Efectivo')
ON CONFLICT (nombre) DO NOTHING;


-- ============================================================
-- 18. USUARIO ADMINISTRADOR
-- ============================================================

INSERT INTO usuarios (
    tipo_documento,
    numero_documento,
    nombre,
    apepaterno,
    apematerno,
    correo,
    contrasenia,
    estado,
    id_rol
)
SELECT
    'DNI',
    '60008335',
    'GUSTAVO JAVIER',
    NULL,
    NULL,
    'gustavo.gitvc14@gmail.com',
    '$2b$12$pPmYOC14af3f4iJNan/xt.pfBAVM4UVsSa1pePb9zNYgrac5BKFp6',
    'ACTIVO',
    r.id
FROM roles r
WHERE r.nombre = 'admin'
AND NOT EXISTS (
    SELECT 1
    FROM usuarios
    WHERE numero_documento = '60008335'
);


-- ============================================================
-- 19. METAS DE KPIs
-- ============================================================

INSERT INTO metas_kpi
(objetivo, nombre_kpi, descripcion, meta, unidad)
VALUES

(
    'Garantizar la asistencia de los pacientes',
    'Tasa de asistencia',
    'Citas atendidas respecto a las citas finalizadas (atendidas + canceladas)',
    90,
    '%'
),

(
    'Minimizar la pérdida de agenda por cancelaciones',
    'Tasa de cancelación',
    'Citas canceladas respecto al total de citas programadas',
    10,
    '%'
),

(
    'Maximizar la confirmación de las reservas',
    'Tasa de conversión',
    'Citas confirmadas respecto al total de citas solicitadas',
    60,
    '%'
),

(
    'Aumentar la rentabilidad por cita atendida',
    'Ticket promedio',
    'Ingresos generados divididos entre las citas con pago',
    120,
    'soles'
),

(
    'Incrementar el valor económico de cada paciente',
    'Ingreso por paciente',
    'Ingresos totales divididos entre los pacientes activos',
    250,
    'soles'
),

(
    'Crecer la cartera de pacientes',
    'Tasa de nuevos pacientes',
    'Pacientes nuevos del mes respecto al total de pacientes activos',
    10,
    '%'
)

ON CONFLICT (objetivo) DO NOTHING;


-- ============================================================
-- 20. ÍNDICES PARA MEJORAR LOS KPIs
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_citas_fecha
ON citas(fecha);

CREATE INDEX IF NOT EXISTS idx_citas_estado
ON citas(estado);

CREATE INDEX IF NOT EXISTS idx_citas_paciente
ON citas(paciente_id);

CREATE INDEX IF NOT EXISTS idx_citas_odontologo
ON citas(odontologo_id);

CREATE INDEX IF NOT EXISTS idx_pagos_fecha
ON pagos(fecha);

CREATE INDEX IF NOT EXISTS idx_pagos_estado
ON pagos(estado);

CREATE INDEX IF NOT EXISTS idx_usuarios_rol
ON usuarios(id_rol);

CREATE INDEX IF NOT EXISTS idx_usuarios_fecha_registro
ON usuarios(fecha_registro);

CREATE INDEX IF NOT EXISTS idx_inventario_stock
ON inventario(cantidad, stock_minimo);


-- ============================================================
-- 21. VISTA KPI: CITAS
-- ============================================================

CREATE OR REPLACE VIEW vista_kpi_citas AS
SELECT
    COUNT(*) AS total_citas,

    COUNT(*) FILTER (
        WHERE estado = 'pendiente'
    ) AS citas_pendientes,

    COUNT(*) FILTER (
        WHERE estado = 'confirmada'
    ) AS citas_confirmadas,

    COUNT(*) FILTER (
        WHERE estado = 'atendida'
    ) AS citas_atendidas,

    COUNT(*) FILTER (
        WHERE estado = 'cancelada'
    ) AS citas_canceladas,

    ROUND(
        COUNT(*) FILTER (
            WHERE estado = 'atendida'
        ) * 100.0
        /
        NULLIF(
            COUNT(*) FILTER (
                WHERE estado IN ('atendida', 'cancelada')
            ),
            0
        ),
        2
    ) AS porcentaje_asistencia

FROM citas;


-- ============================================================
-- 22. VISTA KPI: PACIENTES
-- ============================================================

CREATE OR REPLACE VIEW vista_kpi_pacientes AS
SELECT

    COUNT(*) FILTER (
        WHERE r.nombre = 'paciente'
        AND u.estado = 'ACTIVO'
    ) AS total_pacientes,

    COUNT(*) FILTER (
        WHERE r.nombre = 'paciente'
        AND u.estado = 'ACTIVO'
        AND u.fecha_registro >= date_trunc('month', CURRENT_DATE)
        AND u.fecha_registro <
            date_trunc('month', CURRENT_DATE)
            + INTERVAL '1 month'
    ) AS nuevos_pacientes_mes

FROM usuarios u
JOIN roles r
    ON u.id_rol = r.id;


-- ============================================================
-- 23. VISTA KPI: INGRESOS
-- ============================================================

CREATE OR REPLACE VIEW vista_kpi_ingresos AS
SELECT

    COALESCE(
        SUM(monto) FILTER (
            WHERE estado = 'valido'
        ),
        0
    ) AS ingresos_totales,

    COALESCE(
        SUM(monto) FILTER (
            WHERE estado = 'valido'
            AND fecha >= date_trunc('month', CURRENT_DATE)
            AND fecha <
                date_trunc('month', CURRENT_DATE)
                + INTERVAL '1 month'
        ),
        0
    ) AS ingresos_mes,

    COALESCE(
        SUM(monto) FILTER (
            WHERE estado = 'valido'
            AND tipo = 'adelanto'
        ),
        0
    ) AS total_adelantos,

    COALESCE(
        SUM(monto) FILTER (
            WHERE estado = 'valido'
            AND tipo = 'completo'
        ),
        0
    ) AS pagos_completos

FROM pagos;


-- ============================================================
-- 24. VISTA KPI: INVENTARIO
-- ============================================================

CREATE OR REPLACE VIEW vista_kpi_inventario AS
SELECT

    COUNT(*) AS total_productos,

    COUNT(*) FILTER (
        WHERE cantidad <= stock_minimo
    ) AS productos_stock_bajo,

    COUNT(*) FILTER (
        WHERE cantidad = 0
    ) AS productos_sin_stock,

    COALESCE(
        SUM(cantidad * precio_compra),
        0
    ) AS valor_inventario

FROM inventario;


-- ============================================================
-- 25. VISTA KPI: TRATAMIENTOS
-- ============================================================

CREATE OR REPLACE VIEW vista_kpi_tratamientos AS
SELECT

    COUNT(*) AS total_tratamientos,

    COUNT(*) FILTER (
        WHERE c.estado = 'atendida'
    ) AS tratamientos_realizados,

    COALESCE(
        SUM(ct.precio_aplicado)
        FILTER (
            WHERE c.estado = 'atendida'
        ),
        0
    ) AS ingresos_tratamientos

FROM cita_tratamiento ct
JOIN citas c
    ON ct.id_cita = c.id;


-- ============================================================
-- 26. VISTA: TRATAMIENTOS MÁS SOLICITADOS
-- ============================================================

CREATE OR REPLACE VIEW vista_tratamientos_mas_solicitados AS
SELECT

    t.id_tratamiento,

    t.nombre AS tratamiento,

    e.nombre AS especialidad,

    COUNT(ct.id) AS cantidad_solicitudes,

    COALESCE(
        SUM(ct.precio_aplicado),
        0
    ) AS ingresos

FROM cita_tratamiento ct

JOIN tratamientos t
    ON ct.id_tratamiento = t.id_tratamiento

JOIN especialidades e
    ON t.id_especialidad = e.id

GROUP BY
    t.id_tratamiento,
    t.nombre,
    e.nombre

ORDER BY cantidad_solicitudes DESC;


-- ============================================================
-- 27. VISTA: CITAS POR ODONTÓLOGO
-- ============================================================

CREATE OR REPLACE VIEW vista_citas_odontologo AS
SELECT

    u.id AS odontologo_id,

    CONCAT(
        u.nombre,
        ' ',
        COALESCE(u.apepaterno, ''),
        ' ',
        COALESCE(u.apematerno, '')
    ) AS odontologo,

    COUNT(c.id) AS total_citas,

    COUNT(c.id) FILTER (
        WHERE c.estado = 'atendida'
    ) AS citas_atendidas,

    COUNT(c.id) FILTER (
        WHERE c.estado = 'cancelada'
    ) AS citas_canceladas

FROM usuarios u

LEFT JOIN citas c
    ON u.id = c.odontologo_id

JOIN roles r
    ON u.id_rol = r.id

WHERE r.nombre IN ('odontologo', 'dentista')

GROUP BY
    u.id,
    u.nombre,
    u.apepaterno,
    u.apematerno

ORDER BY total_citas DESC;


-- ============================================================
-- 28. VISTA: INGRESOS POR ESPECIALIDAD
-- ============================================================

CREATE OR REPLACE VIEW vista_ingresos_especialidad AS
SELECT

    e.id AS especialidad_id,

    e.nombre AS especialidad,

    COUNT(DISTINCT c.id) AS cantidad_citas,

    COALESCE(
        SUM(ct.precio_aplicado),
        0
    ) AS ingresos

FROM especialidades e

LEFT JOIN tratamientos t
    ON e.id = t.id_especialidad

LEFT JOIN cita_tratamiento ct
    ON t.id_tratamiento = ct.id_tratamiento

LEFT JOIN citas c
    ON ct.id_cita = c.id

GROUP BY
    e.id,
    e.nombre

ORDER BY ingresos DESC;


-- ============================================================
-- 29. VISTA: INVENTARIO CON STOCK BAJO
-- ============================================================

CREATE OR REPLACE VIEW vista_stock_bajo AS
SELECT

    id,

    nombre,

    categoria,

    cantidad,

    stock_minimo,

    proveedor,

    precio_compra,

    fecha_actualizacion

FROM inventario

WHERE cantidad <= stock_minimo

ORDER BY cantidad ASC;


-- ============================================================
-- 30. VISTA PRINCIPAL DEL DASHBOARD
-- ============================================================

CREATE OR REPLACE VIEW vista_kpis_dashboard AS
SELECT

    -- CITAS
    (
        SELECT COUNT(*)
        FROM citas
    ) AS total_citas,

    (
        SELECT COUNT(*)
        FROM citas
        WHERE estado = 'pendiente'
    ) AS citas_pendientes,

    (
        SELECT COUNT(*)
        FROM citas
        WHERE estado = 'confirmada'
    ) AS citas_confirmadas,

    (
        SELECT COUNT(*)
        FROM citas
        WHERE estado = 'atendida'
    ) AS citas_atendidas,

    (
        SELECT COUNT(*)
        FROM citas
        WHERE estado = 'cancelada'
    ) AS citas_canceladas,

    (
        SELECT ROUND(
            COUNT(*) FILTER (
                WHERE estado = 'atendida'
            ) * 100.0
            /
            NULLIF(
                COUNT(*) FILTER (
                    WHERE estado IN ('atendida', 'cancelada')
                ),
                0
            ),
            2
        )
        FROM citas
    ) AS porcentaje_asistencia,


    -- PACIENTES
    (
        SELECT COUNT(*)
        FROM usuarios u
        JOIN roles r
            ON u.id_rol = r.id
        WHERE r.nombre = 'paciente'
        AND u.estado = 'ACTIVO'
    ) AS total_pacientes,


    (
        SELECT COUNT(*)
        FROM usuarios u
        JOIN roles r
            ON u.id_rol = r.id
        WHERE r.nombre = 'paciente'
        AND u.estado = 'ACTIVO'
        AND u.fecha_registro >= date_trunc(
            'month',
            CURRENT_DATE
        )
        AND u.fecha_registro <
            date_trunc(
                'month',
                CURRENT_DATE
            ) + INTERVAL '1 month'
    ) AS nuevos_pacientes_mes,


    -- INGRESOS
    (
        SELECT COALESCE(
            SUM(monto),
            0
        )
        FROM pagos
        WHERE estado = 'valido'
    ) AS ingresos_totales,


    (
        SELECT COALESCE(
            SUM(monto),
            0
        )
        FROM pagos
        WHERE estado = 'valido'
        AND fecha >= date_trunc(
            'month',
            CURRENT_DATE
        )
        AND fecha <
            date_trunc(
                'month',
                CURRENT_DATE
            ) + INTERVAL '1 month'
    ) AS ingresos_mes,


    (
        SELECT COALESCE(
            SUM(monto),
            0
        )
        FROM pagos
        WHERE estado = 'valido'
        AND tipo = 'adelanto'
    ) AS adelantos_totales,


    -- TRATAMIENTOS
    (
        SELECT COUNT(*)
        FROM cita_tratamiento ct
        JOIN citas c
            ON ct.id_cita = c.id
        WHERE c.estado = 'atendida'
    ) AS tratamientos_realizados,


    -- INVENTARIO
    (
        SELECT COUNT(*)
        FROM inventario
    ) AS total_productos,


    (
        SELECT COUNT(*)
        FROM inventario
        WHERE cantidad <= stock_minimo
    ) AS productos_stock_bajo,


    (
        SELECT COUNT(*)
        FROM inventario
        WHERE cantidad = 0
    ) AS productos_sin_stock;


-- ============================================================
-- 31. KPI MENSUAL DE CITAS
-- ============================================================

CREATE OR REPLACE VIEW vista_kpi_citas_mensual AS
SELECT

    DATE_TRUNC(
        'month',
        fecha
    )::DATE AS mes,

    COUNT(*) AS total_citas,

    COUNT(*) FILTER (
        WHERE estado = 'atendida'
    ) AS atendidas,

    COUNT(*) FILTER (
        WHERE estado = 'cancelada'
    ) AS canceladas,

    COUNT(*) FILTER (
        WHERE estado = 'pendiente'
    ) AS pendientes,

    COUNT(*) FILTER (
        WHERE estado = 'confirmada'
    ) AS confirmadas

FROM citas

GROUP BY DATE_TRUNC(
    'month',
    fecha
)

ORDER BY mes;


-- ============================================================
-- 32. KPI MENSUAL DE INGRESOS
-- ============================================================

CREATE OR REPLACE VIEW vista_kpi_ingresos_mensual AS
SELECT

    DATE_TRUNC(
        'month',
        fecha
    )::DATE AS mes,

    COALESCE(
        SUM(monto) FILTER (
            WHERE estado = 'valido'
        ),
        0
    ) AS ingresos,

    COALESCE(
        SUM(monto) FILTER (
            WHERE estado = 'valido'
            AND tipo = 'adelanto'
        ),
        0
    ) AS adelantos,

    COALESCE(
        SUM(monto) FILTER (
            WHERE estado = 'valido'
            AND tipo = 'completo'
        ),
        0
    ) AS pagos_completos

FROM pagos

GROUP BY DATE_TRUNC(
    'month',
    fecha
)

ORDER BY mes;


-- ============================================================
-- 33. KPI MENSUAL DE PACIENTES
-- ============================================================

CREATE OR REPLACE VIEW vista_kpi_pacientes_mensual AS
SELECT

    DATE_TRUNC(
        'month',
        u.fecha_registro
    )::DATE AS mes,

    COUNT(*) AS nuevos_pacientes

FROM usuarios u

JOIN roles r
    ON u.id_rol = r.id

WHERE r.nombre = 'paciente'

GROUP BY DATE_TRUNC(
    'month',
    u.fecha_registro
)

ORDER BY mes;


-- ============================================================
-- 34. VISTA KPI: FÓRMULAS MATEMÁTICAS
-- ============================================================

CREATE OR REPLACE VIEW vista_kpi_formulas AS
SELECT

    -- Cinéticas base
    (SELECT COUNT(*) FROM citas) AS total_citas,

    (SELECT COUNT(*) FROM citas WHERE estado = 'atendida') AS atendidas,

    (SELECT COUNT(*) FROM citas WHERE estado = 'cancelada') AS canceladas,

    (SELECT COUNT(*) FROM citas WHERE estado = 'confirmada') AS confirmadas,

    (SELECT COUNT(DISTINCT id_cita) FROM pagos WHERE estado = 'valido') AS citas_pagadas,

    (SELECT COUNT(*) FROM usuarios u JOIN roles r ON u.id_rol = r.id
     WHERE r.nombre = 'paciente' AND u.estado = 'ACTIVO') AS pacientes_activos,

    (SELECT COUNT(*) FROM usuarios u JOIN roles r ON u.id_rol = r.id
     WHERE r.nombre = 'paciente' AND u.estado = 'ACTIVO'
     AND u.fecha_registro >= date_trunc('month', CURRENT_DATE)
     AND u.fecha_registro < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month') AS nuevos_pacientes_mes,

    (SELECT COALESCE(SUM(monto),0) FROM pagos WHERE estado = 'valido') AS ingresos_totales,

    -- Fórmulas
    ROUND(
        (SELECT COUNT(*) FROM citas WHERE estado = 'atendida') * 100.0
        / NULLIF((SELECT COUNT(*) FROM citas WHERE estado IN ('atendida','cancelada')), 0),
        2
    ) AS tasa_asistencia,

    ROUND(
        (SELECT COUNT(*) FROM citas WHERE estado = 'cancelada') * 100.0
        / NULLIF((SELECT COUNT(*) FROM citas), 0),
        2
    ) AS tasa_cancelacion,

    ROUND(
        (SELECT COUNT(*) FROM citas WHERE estado = 'confirmada') * 100.0
        / NULLIF((SELECT COUNT(*) FROM citas), 0),
        2
    ) AS tasa_conversion,

    ROUND(
        (SELECT COALESCE(SUM(monto),0) FROM pagos WHERE estado = 'valido')
        / NULLIF((SELECT COUNT(DISTINCT id_cita) FROM pagos WHERE estado = 'valido'), 0),
        2
    ) AS ticket_promedio,

    ROUND(
        (SELECT COALESCE(SUM(monto),0) FROM pagos WHERE estado = 'valido')
        / NULLIF((SELECT COUNT(*) FROM usuarios u JOIN roles r ON u.id_rol = r.id
                  WHERE r.nombre = 'paciente' AND u.estado = 'ACTIVO'), 0),
        2
    ) AS ingreso_por_paciente,

    ROUND(
        (SELECT COUNT(*) FROM usuarios u JOIN roles r ON u.id_rol = r.id
         WHERE r.nombre = 'paciente' AND u.estado = 'ACTIVO'
         AND u.fecha_registro >= date_trunc('month', CURRENT_DATE)
         AND u.fecha_registro < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month') * 100.0
        / NULLIF((SELECT COUNT(*) FROM usuarios u JOIN roles r ON u.id_rol = r.id
                  WHERE r.nombre = 'paciente' AND u.estado = 'ACTIVO'), 0),
        2
    ) AS tasa_nuevos_pacientes;


-- ============================================================
-- 35. CONSULTAS PARA EL DASHBOARD (referencia)
-- ============================================================

-- KPIs PRINCIPALES:        SELECT * FROM vista_kpis_dashboard;
-- KPIs DE CITAS:           SELECT * FROM vista_kpi_citas;
-- KPIs DE PACIENTES:       SELECT * FROM vista_kpi_pacientes;
-- KPIs DE INGRESOS:        SELECT * FROM vista_kpi_ingresos;
-- KPIs DE TRATAMIENTOS:    SELECT * FROM vista_kpi_tratamientos;
-- KPIs DE INVENTARIO:      SELECT * FROM vista_kpi_inventario;
-- TRATAMIENTOS MÁS SOLICITADOS: SELECT * FROM vista_tratamientos_mas_solicitados;
-- CITAS POR ODONTÓLOGO:    SELECT * FROM vista_citas_odontologo;
-- INGRESOS POR ESPECIALIDAD: SELECT * FROM vista_ingresos_especialidad;
-- PRODUCTOS CON STOCK BAJO: SELECT * FROM vista_stock_bajo;
-- EVOLUCIÓN MENSUAL DE CITAS:  SELECT * FROM vista_kpi_citas_mensual;
-- EVOLUCIÓN MENSUAL DE INGRESOS: SELECT * FROM vista_kpi_ingresos_mensual;
-- EVOLUCIÓN MENSUAL DE PACIENTES: SELECT * FROM vista_kpi_pacientes_mensual;