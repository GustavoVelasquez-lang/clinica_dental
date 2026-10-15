-- ============================================================
-- Migración: pago por Yape directo con validación manual por voucher
--
-- 1) Datos del voucher en la cita: método, N° de operación y URL.
-- 2) Nuevo estado de pago 'pendiente_verificacion' (voucher recibido,
--    a la espera de que el administrador lo valide).
--
-- Idempotente (seguro re-ejecutar).
-- ============================================================

-- 1) Columnas del pago manual por Yape
ALTER TABLE citas ADD COLUMN IF NOT EXISTS metodo_pago VARCHAR(30);
ALTER TABLE citas ADD COLUMN IF NOT EXISTS nro_operacion VARCHAR(50);
ALTER TABLE citas ADD COLUMN IF NOT EXISTS voucher_url TEXT;

-- 2) Reemplaza el CHECK de estado_pago para admitir 'pendiente_verificacion'.
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
            'rechazado', 'pendiente_verificacion'
        ));
END $$;

-- 3) 'pendiente_verificacion' (22 chars) excede VARCHAR(20): ampliar la columna.
ALTER TABLE citas ALTER COLUMN estado_pago TYPE VARCHAR(30);
