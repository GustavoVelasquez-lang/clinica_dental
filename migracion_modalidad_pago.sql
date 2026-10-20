-- ============================================================
-- Migración: modalidad de pago elegida por el paciente
--
-- El paciente, en la pantalla de pago, puede elegir entre:
--   * 'adelanto'  → paga solo el adelanto (reserva) y el saldo
--                   restante lo cancela presencialmente en caja.
--   * 'completo'  → paga el tratamiento completo por Yape/Culqi.
--
-- Se guarda en `citas.modalidad_pago`. Al validar el comprobante el
-- admin la usa para decidir el estado final:
--   'adelanto' → estado_pago = 'pagado'
--   'completo' → estado_pago = 'pagado_total'
--
-- Idempotente (seguro re-ejecutar). También se aplica automáticamente
-- al arrancar la app (ver `_asegurar_esquema_perfil` en app.py).
-- ============================================================

ALTER TABLE citas ADD COLUMN IF NOT EXISTS modalidad_pago VARCHAR(20);

-- Opcional: limitar los valores admitidos en instalaciones nuevas.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'citas'::regclass
          AND conname = 'citas_modalidad_pago_check'
    ) THEN
        ALTER TABLE citas ADD CONSTRAINT citas_modalidad_pago_check
            CHECK (modalidad_pago IS NULL OR modalidad_pago IN ('adelanto', 'completo'));
    END IF;
END $$;

-- Los pagos validados (Yape manual / Culqi / caja) se registran en `pagos`:
--   tipo = 'adelanto' | 'completo'
--   gateway = 'yape_manual' | 'culqi' | 'efectivo' | 'pos_tarjeta' | 'yape_presencial'
