import os
import time
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

_MAX_INTENTOS = 4
_ESPERA_BASE = 1.5  # segundos entre reintentos (backoff cuadrático)


def _es_error_transitorio(e):
    """Detecta fallos recuperables del pooler/Supabase (no de credenciales)."""
    texto = str(e).lower()
    return any(señal in texto for señal in (
        "enotfound",                 # pooler sin el tenant (caída transitoria)
        "temporarily unavailable",
        "connection refused",
        "connection timed out",
        "timeout expired",
        "no route to host",
        "server closed the connection",
        "ssl connection has been closed",
    ))


def _crear_conexion():
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return psycopg2.connect(url, sslmode="require", cursor_factory=RealDictCursor)


def get_connection():
    """Abre conexión a PostgreSQL con reintentos automáticos.

    El pooler de Supabase sufre caídas transitorias de ~minutos
    (FATAL: ENOTFOUND tenant/user ... not found). En lugar de lanzar
    el error de inmediato, se reintenta con backoff exponencial
    (2s, 8s, 18s, 32s...) hasta un máximo, y solo entonces falla.
    """
    for intento in range(1, _MAX_INTENTOS + 1):
        try:
            return _crear_conexion()
        except psycopg2.OperationalError as e:
            if intento >= _MAX_INTENTOS or not _es_error_transitorio(e):
                raise
            espera = min(_ESPERA_BASE * (intento ** 2), 15)
            time.sleep(espera)
    raise psycopg2.OperationalError("No se pudo conectar a la base de datos")