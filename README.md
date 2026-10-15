# Clínica Dental — Sistema Web (Flask + PostgreSQL/Supabase)

Proyecto academico: gestion de citas, pagos con validacion de comprobantes,
recordatorios por email y panel de administracion con KPIs por objetivo.

## Requisitos

- Python 3.10 o superior instalado (marcar "Add Python to PATH" al instalar).
- Solo Windows es requerido; funciona igual en la laptop donde se ejecuta.

## Puesta en marcha (una sola vez)

Abre una terminal (PowerShell o CMD) dentro de la carpeta del proyecto:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Todo correcto si en la consola aparece algo como:

```
* Running on http://127.0.0.1:5000
```

Abre el navegador en: http://localhost:5000

> Si `pip install` tarda, es normal (descarga dependencias). Espera a que termine.

## Accesos de prueba

| Rol | Documento | Clave |
|---|---|---|
| Administrador | `60008335` | `Gustavo-2007@` |
| Paciente | crear una cuenta en "Registrarse" (se guarda en la BD compartida) |

### Panel del administrador

Entra con el usuario admin y se redirige a `/admin/dashboard`.
Desde el menu lateral: citas, pacientes, facturacion, inventario, reportes y
**KPIs** (un KPI único por objetivo, con su fórmula matemática).

## Configuracion (el proyecto YA trae su BD conectada)

- La conexión a la base de datos vive en `.env` (`DATABASE_URL` apunta a una
  PostgreSQL en la nube, Supabase). No se borra ningún archivo.
- `.env.example` es solo la plantilla con las variables sin valores.

### Si no envía correos (recordatorios)

La app funciona y agenda citas sin hacer nada extra. El envío de correos exige
una cuenta Gmail autorizada; en esta entrega se omitió el token por seguridad.
Para activarlo en un futuro: crea un proyecto en Google Cloud, habilita la Gmail
API y ejecuta `python gmail_auth.py` (la app soporta enviar recordatorios, pero
no es requisito para la visualización del proyecto).

## Notas para la revisión

- Base de datos: PostgreSQL (Supabase) mediante `db.py`.
- La estructura completa (tablas, vistas KPI, índices) está en `supabase_schema.sql`.
- Script de recordatorios manual: `python recordatorios.py`.