-- ============================================================
-- Migración: cobro del saldo restante en caja (admin)
--
-- 1) `citas.monto_total`: total a cobrar de la cita (precio del
--    tratamiento). Si no se guarda, se calcula desde
--    `cita_tratamiento.precio_aplicado`.
-- 2) `monto_restante` NO se guarda: se calcula como
--    monto_total - SUM(pagos válidos de la cita).
-- 3) Nuevo estado de pago 'pagado_total': la cita está pagada en su
--    totalidad (adelanto + cobros en caja).
-- 4) Backfill del total para las citas antiguas.
--
-- Idempotente (seguro re-ejecutar). También se aplica automáticamente
-- al arrancar la app (ver `_asegurar_esquema_perfil` en app.py).
-- ============================================================

-- 1) Total a cobrar de la cita
ALTER TABLE citas ADD COLUMN IF NOT EXISTS monto_total NUMERIC(10,2)
    CHECK (monto_total >= 0);

-- 4) Backfill: total desde el precio del tratamiento asociado
UPDATE citas c
SET monto_total = sub.total
FROM (
    SELECT ct.id_cita, SUM(ct.precio_aplicado) AS total
    FROM cita_tratamiento ct
    GROUP BY ct.id_cita
) sub
WHERE sub.id_cita = c.id AND c.monto_total IS NULL;

-- 3) Reemplaza el CHECK de estado_pago para admitir 'pagado_total'.
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

-- Los cobros en caja se registran en la tabla `pagos` existente:
--   tipo      = 'adelanto' (cobro parcial) | 'completo' (saldo cerrado)
--   gateway   = 'efectivo' | 'pos_tarjeta' | 'yape_presencial'
--   estado    = 'valido'
-- La ruta en la app es POST /admin/citas/<id>/registrar-pago-caja.
