"""Rellena (una sola vez) la fecha de nacimiento de los pacientes que no la
tienen, con valores aleatorios plausibles dentro del rango 1950-2010.

Uso:
    python seed_fechas_nacimiento.py

Es idempotente: solo actualiza filas de usuarios con rol 'paciente' cuyo
`fenacimiento` es NULL. Los usuarios que ya tienen fecha no se tocan.
"""
import random
import sys
from datetime import date

from db import get_connection

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Rango de fechas plausibles (años).
ANIO_MIN = 1950
ANIO_MAX = 2010

INICIO = date(ANIO_MIN, 1, 1).toordinal()
FIN = date(ANIO_MAX, 12, 31).toordinal()


def _fecha_aleatoria():
    return date.fromordinal(random.randint(INICIO, FIN))


def main():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT u.id, u.nombre, u.apepaterno, u.apematerno, u.numero_documento
        FROM usuarios u
        LEFT JOIN roles r ON u.id_rol = r.id
        WHERE r.nombre = 'paciente' AND u.fenacimiento IS NULL
        ORDER BY u.id
    """)
    pendientes = cur.fetchall()

    if not pendientes:
        print("No hay pacientes sin fecha de nacimiento. Nada que hacer.")
        cur.close()
        conn.close()
        return

    print(f"Pacientes sin fecha: {len(pendientes)}")
    for fila in pendientes:
        fecha = _fecha_aleatoria()
        cur.execute(
            "UPDATE usuarios SET fenacimiento = %s WHERE id = %s AND fenacimiento IS NULL",
            (fecha, fila["id"]),
        )
        print(f"  - id {fila['id']:>3} {fila['nombre']} -> {fecha.isoformat()}")

    conn.commit()
    print(f"✅ Actualizados {len(pendientes)} pacientes.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
