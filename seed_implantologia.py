"""Seed idempotente: catálogo de tratamientos de IMPLANTOLOGÍA (Clinica SELEDENT).

Uso:
    python seed_implantologia.py

- Vincula los 4 tratamientos a la especialidad "Implantología".
- Hace upsert por (id_especialidad, nombre): re-ejecutarlo no duplica.
- El campo `codigo` se deja NULL (no lo usa la UI).
"""
import unicodedata

from db import get_connection


def _norm(texto):
    texto = (texto or "").strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


ESPECIALIDAD = "Implantología"
CANDIDATOS_ESPECIALIDAD = ["implantologia"]

TRATAMIENTOS = [
    {
        "nombre": "Implante Unitario",
        "descripcion": "Reemplazo de un solo diente mediante un implante y una corona independiente. No desgasta los dientes vecinos.",
        "precio": 1200.00, "adelanto": 300.00, "duracion": 60,
    },
    {
        "nombre": "Puente sobre Implantes",
        "descripcion": "Reposición de varias piezas seguidas mediante un puente fijo anclado a implantes, sin desgastar dientes sanos.",
        "precio": 2800.00, "adelanto": 700.00, "duracion": 90,
    },
    {
        "nombre": "Prótesis Híbrida (All-on-4 / All-on-6)",
        "descripcion": "Rehabilitación completa de una arcada sobre 4 o 6 implantes estratégicamente colocados. Dentadura fija que no se mueve.",
        "precio": 6500.00, "adelanto": 1500.00, "duracion": 120,
    },
    {
        "nombre": "Sobredentadura sobre Implantes",
        "descripcion": "Prótesis completa sujeta a los implantes con sistema de anclaje (retech o barras). Estable y removible para una fácil limpieza.",
        "precio": 3500.00, "adelanto": 800.00, "duracion": 90,
    },
]


def _resolver_especialidad(cur):
    cur.execute("SELECT id, nombre FROM especialidades")
    filas = cur.fetchall()
    candidatos = [_norm(c) for c in CANDIDATOS_ESPECIALIDAD]

    for f in filas:
        if _norm(f["nombre"]) in candidatos:
            return f["id"]

    for f in filas:
        nf = _norm(f["nombre"])
        for c in candidatos:
            if c and (c in nf or nf in c):
                return f["id"]

    disponibles = ", ".join(str(f["nombre"]) for f in filas)
    raise SystemExit(
        f"No se encontró la especialidad '{ESPECIALIDAD}'. Disponibles: {disponibles}"
    )


def _asegurar_columnas(cur):
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS precio_base NUMERIC(10,2)")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS adelanto NUMERIC(10,2)")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS duracion_minutos INTEGER")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE")


def main():
    conn = get_connection()
    cur = conn.cursor()
    _asegurar_columnas(cur)

    esp_id = _resolver_especialidad(cur)
    print(f"Especialidad '{ESPECIALIDAD}' -> id={esp_id}\n")

    insertados = actualizados = 0
    for t in TRATAMIENTOS:
        cur.execute(
            "SELECT id_tratamiento FROM tratamientos "
            "WHERE id_especialidad = %s AND lower(nombre) = lower(%s)",
            (esp_id, t["nombre"]),
        )
        existente = cur.fetchone()
        if existente:
            cur.execute(
                "UPDATE tratamientos SET descripcion=%s, precio_base=%s, "
                "adelanto=%s, duracion_minutos=%s, activo=TRUE "
                "WHERE id_tratamiento=%s",
                (t["descripcion"], t["precio"], t["adelanto"],
                 t["duracion"], existente["id_tratamiento"]),
            )
            actualizados += 1
            print(f"  ~ Actualizado: {t['nombre']}")
        else:
            cur.execute(
                "INSERT INTO tratamientos (id_especialidad, nombre, descripcion, "
                "precio_base, adelanto, duracion_minutos, activo) "
                "VALUES (%s, %s, %s, %s, %s, %s, TRUE)",
                (esp_id, t["nombre"], t["descripcion"], t["precio"],
                 t["adelanto"], t["duracion"]),
            )
            insertados += 1
            print(f"  + Insertado: {t['nombre']}")

    conn.commit()

    cur.execute(
        "SELECT nombre, precio_base, adelanto, duracion_minutos, activo, codigo "
        "FROM tratamientos WHERE id_especialidad = %s "
        "ORDER BY precio_base",
        (esp_id,),
    )
    print("\n--- Catálogo Implantología ---")
    for r in cur.fetchall():
        print(
            f"  {r['nombre']} | S/ {r['precio_base']} | adelanto S/ {r['adelanto']} | "
            f"{r['duracion_minutos']} min | activo={r['activo']} | codigo={r['codigo']}"
        )

    conn.close()
    print(f"\nListo. Insertados: {insertados} | Actualizados: {actualizados}")


if __name__ == "__main__":
    main()
