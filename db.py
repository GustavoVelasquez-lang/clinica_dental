import os
import logging
from contextlib import contextmanager
from urllib.parse import urlparse, parse_qs

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_connection_pool = None


def _get_pool():
    global _connection_pool
    if _connection_pool is None:
        url = os.getenv("DATABASE_URL", "")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if "sslmode=" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=url,
            sslmode="require",
            cursor_factory=RealDictCursor,
        )
        logger.info("Pool de conexiones PostgreSQL creado (min=2, max=10)")
    return _connection_pool


def get_connection():
    return _get_pool().getconn()


def release_connection(conn):
    try:
        _get_pool().putconn(conn)
    except Exception:
        logger.warning("Error al devolver conexion al pool")


@contextmanager
def db_connection():
    conn = get_connection()
    try:
        yield conn
    finally:
        release_connection(conn)
