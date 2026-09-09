# AGENTS.md

## Proyecto
Clínica Dental: sistema web Flask + PostgreSQL (Supabase) para gestión de citas,
pagos con validación de comprobantes y recordatorios por email vía Gmail API.

## Comandos
- Instalar dependencias: `pip install -r requirements.txt`
- Ejecutar app (dev): `python app.py`
- Crear token Gmail (una sola vez): `python gmail_auth.py`
- Enviar recordatorios manualmente: `python recordatorios.py`
- No hay linter ni typecheck configurado en el repo.

## Cómo correr/verificar
- La app se levanta en `http://localhost:5000` (Flask dev server con `debug=True`).
- La BD es PostgreSQL remota (Supabase) vía `DATABASE_URL` en `.env`.

## Stack y estructura
- Flask (Flask, Flask-Bcrypt, Authlib, Flask-APScheduler), psycopg2.
- `db.py` — conexión PostgreSQL (`get_connection`, retorna dicts).
- `app.py` — rutas, auth (login con bloqueo por IP, registro, Google OAuth),
  citas, pagos, panel admin, scheduler diario a las 08:00.
- `email_utils.py` — envío de correos Gmail API (recordatorios, comprobantes).
- `recordatorios.py` — script de recordatorios T-3/T-2/T-1 con dedupe en tabla `recordatorios`.
- `gmail_auth.py` — genera `gmail_token.json` (gitignored).
- `templates/` — Jinja2 (base.html y base_admin.html como layouts).
- `static/` — CSS, JS e imágenes.

## Archivos sensibles (no commitear)
- `.env`, `client_secret.json`, `gmail_token.json`, `static/comprobantes/`
  (verificar `.gitignore` antes de cualquier commit).

## Convenciones
- Código y mensajes en español.
- Acceso a BD siempre con `RealDictCursor` (resultados como dicts, `c["columna"]`).
- Cierre de conexión `conn.close()` tras su uso.
- Rutas protegidas con `@login_required` (paciente) y `@admin_required` (admin).
- Uso de `flash()` para feedback al usuario (`danger`/`success`).
- Mensajes/emojis de UI siguen el estilo existente (✅ ❌ ⚠️).