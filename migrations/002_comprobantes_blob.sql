-- 002_comprobantes_blob.sql
-- Guarda el comprobante (voucher) de pago dentro de la base de datos para que
-- sea accesible desde cualquier instancia (Supabase compartido / Render) y no
-- dependa del disco local efímero del servidor.
--
-- voucher_data: contenido binario de la imagen (JPG/PNG)
-- voucher_mime: tipo MIME de la imagen (image/jpeg | image/png)

ALTER TABLE citas ADD COLUMN IF NOT EXISTS voucher_data BYTEA;
ALTER TABLE citas ADD COLUMN IF NOT EXISTS voucher_mime TEXT;
