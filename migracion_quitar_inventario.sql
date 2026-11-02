-- ============================================================
-- Eliminar el módulo de INVENTARIO (no se utiliza)
-- Clinica SELEDENT
-- ============================================================
-- Orden:
--   1. Eliminar las vistas que dependen de la tabla `inventario`.
--   2. Recrear `vista_kpis_dashboard` sin las columnas de inventario.
--   3. Eliminar la tabla `inventario`.
-- ============================================================

BEGIN;

-- 1. Vistas dependientes de inventario
DROP VIEW IF EXISTS vista_kpis_dashboard;
DROP VIEW IF EXISTS vista_kpi_inventario;
DROP VIEW IF EXISTS vista_stock_bajo;

-- 2. Vista principal del dashboard SIN KPIs de inventario
CREATE VIEW vista_kpis_dashboard AS
SELECT
    (SELECT COUNT(*) FROM citas) AS total_citas,

    (SELECT COUNT(*) FROM citas WHERE estado = 'pendiente') AS citas_pendientes,
    (SELECT COUNT(*) FROM citas WHERE estado = 'confirmada') AS citas_confirmadas,
    (SELECT COUNT(*) FROM citas WHERE estado = 'atendida') AS citas_atendidas,
    (SELECT COUNT(*) FROM citas WHERE estado = 'cancelada') AS citas_canceladas,

    (SELECT ROUND(
        COUNT(*) FILTER (WHERE estado = 'atendida')::numeric * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE estado IN ('atendida', 'cancelada')), 0)::numeric,
        2
    ) FROM citas) AS porcentaje_asistencia,

    (SELECT COUNT(*)
       FROM usuarios u
       JOIN roles r ON u.id_rol = r.id
      WHERE r.nombre = 'paciente' AND u.estado = 'ACTIVO') AS total_pacientes,

    (SELECT COUNT(*)
       FROM usuarios u
       JOIN roles r ON u.id_rol = r.id
      WHERE r.nombre = 'paciente' AND u.estado = 'ACTIVO'
        AND u.fecha_registro >= date_trunc('month', CURRENT_DATE)
        AND u.fecha_registro < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month') AS nuevos_pacientes_mes,

    (SELECT COALESCE(SUM(monto), 0)
       FROM pagos
      WHERE estado = 'valido') AS ingresos_totales,

    (SELECT COALESCE(SUM(monto), 0)
       FROM pagos
      WHERE estado = 'valido'
        AND fecha >= date_trunc('month', CURRENT_DATE)
        AND fecha < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month') AS ingresos_mes,

    (SELECT COALESCE(SUM(monto), 0)
       FROM pagos
      WHERE estado = 'valido' AND tipo = 'adelanto') AS adelantos_totales,

    (SELECT COUNT(*)
       FROM cita_tratamiento ct
       JOIN citas c ON ct.id_cita = c.id
      WHERE c.estado = 'atendida') AS tratamientos_realizados;

-- 3. Tabla de inventario
DROP TABLE IF EXISTS inventario;

COMMIT;

-- ============================================================
-- VERIFICACION (ejecutar aparte si se desea):
--   SELECT to_regclass('public.inventario');  -- debe ser NULL
--   SELECT * FROM vista_kpis_dashboard;
-- ============================================================
