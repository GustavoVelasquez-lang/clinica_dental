"""Seed idempotente: catálogo de tratamientos de PERIODONCIA (Clinica SELEDENT).

Uso:
    python seed_periodoncia.py

- Vincula los 6 tratamientos a la especialidad "Periodoncia".
- Busca el id_especialidad dinámicamente por nombre (sin crear la especialidad).
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


ESPECIALIDAD = "Periodoncia"
CANDIDATOS_ESPECIALIDAD = ["periodoncia"]

TRATAMIENTOS = [
    {
        "nombre": "Profilaxis Dental Profunda",
        "descripcion": "Limpieza profesional especializada para eliminar la placa bacteriana y el sarro superficial por encima de la línea de la encía.",
        "precio": 90.00, "adelanto": 30.00, "duracion": 30,
    },
    {
        "nombre": "Raspado y Alisado Radicular (Curetaje)",
        "descripcion": "Limpieza profunda de sarro y bacterias debajo de la encía dentro de las bolsas periodontales, alisando la raíz para favorecer su re-adherencia.",
        "precio": 200.00, "adelanto": 50.00, "duracion": 60,
    },
    {
        "nombre": "Cirugía de Colgajo Periodontal",
        "descripcion": "Levantamiento temporal de la encía para acceder a raíces profundas, limpiar infección avanzada y suturar el tejido en su posición correcta.",
        "precio": 550.00, "adelanto": 150.00, "duracion": 60,
    },
    {
        "nombre": "Injerto de Tejido Blando (Cirugía Plástica Periodontal)",
        "descripcion": "Colocación de tejido del paladar para cubrir raíces expuestas por recesión gingival, reduciendo sensibilidad y mejorando la estética.",
        "precio": 700.00, "adelanto": 200.00, "duracion": 60,
    },
    {
        "nombre": "Injertos Óseos y Regeneración Tisular Guiada (RTG)",
        "descripcion": "Uso de materiales biológicos y membranas para rellenar defectos óseos y estimular la regeneración de tejidos de soporte perdidos.",
        "precio": 950.00, "adelanto": 300.00, "duracion": 90,
    },
    {
        "nombre": "Mantenimiento Periodontal",
        "descripcion": "Sesión de control y limpieza periódica programada (cada 3 a 6 meses) para supervisar la salud de las encías y evitar recaídas.",
        "precio": 100.00, "adelanto": 30.00, "duracion": 30,
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
    print("\n--- Catálogo Periodoncia ---")
    for r in cur.fetchall():
        print(
            f"  {r['nombre']} | S/ {r['precio_base']} | adelanto S/ {r['adelanto']} | "
            f"{r['duracion_minutos']} min | activo={r['activo']} | codigo={r['codigo']}"
        )

    conn.close()
    print(f"\nListo. Insertados: {insertados} | Actualizados: {actualizados}")


if __name__ == "__main__":
    main()
