-- ============================================================
-- Migración: descripciones específicas + nuevas especialidades
-- Puebla/actualiza descripcion y agrega Odontopediatría,
-- Rehabilitación Oral, Radiología e Imagen 3D y Urgencias
-- Odontológicas. Idempotente (seguro re-ejecutar).
-- ============================================================

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
ON CONFLICT (nombre) DO UPDATE
    SET descripcion = EXCLUDED.descripcion;
