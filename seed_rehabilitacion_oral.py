"""Seed idempotente: catálogo de tratamientos de REHABILITACIÓN ORAL (Clinica SELEDENT).

Uso:
    python seed_rehabilitacion_oral.py

- Busca el id_especialidad de "Rehabilitación Oral" por nombre y lo crea si no existe.
- Vincula los 8 tratamientos a esa especialidad.
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


ESPECIALIDAD = "Rehabilitación Oral"
CANDIDATOS_ESPECIALIDAD = ["rehabilitacion oral"]
DESCRIPCION_ESPECIALIDAD = "Restauración de la función y estética dental con coronas, puentes y prótesis."

TRATAMIENTOS = [
    {
        "nombre": "Corona Dental (Circonio / Porcelana / Metal-Porcelana)",
        "descripcion": "Funda a medida que recubre un diente muy destruido o debilitado para devolverle su forma, fuerza y apariencia estética.",
        "precio": 450.00, "adelanto": 100.00, "duracion": 60,
    },
    {
        "nombre": "Puente Dental Fijo (por unidad o pieza)",
        "descripcion": "Estructura fija que se apoya en los dientes vecinos sanos para cubrir el espacio de uno o más dientes ausentes.",
        "precio": 400.00, "adelanto": 100.00, "duracion": 60,
    },
    {
        "nombre": "Carillas de Porcelana / Resina (Veneers)",
        "descripcion": "Láminas estéticas adheridas a la parte frontal de los dientes para corregir la forma, color, tamaño y alineación.",
        "precio": 500.00, "adelanto": 120.00, "duracion": 60,
    },
    {
        "nombre": "Incrustación Dental (Inlay / Onlay / Overlay)",
        "descripcion": "Restauración rígida a medida para cavidades o destrucciones extensas donde una resina convencional no es suficiente.",
        "precio": 300.00, "adelanto": 80.00, "duracion": 45,
    },
    {
        "nombre": "Prótesis Parcial Removible (Metálica / Flexible / Acrílica)",
        "descripcion": "Aparato removible para reemplazar varios dientes perdidos, sujetándose a las piezas dentales mediante retenedores estéticos o metálicos.",
        "precio": 450.00, "adelanto": 100.00, "duracion": 45,
    },
    {
        "nombre": "Prótesis Total / Dentadura Completa (por arcada)",
        "descripcion": "Rehabilitación acrílica completa diseñada para pacientes que han perdido la totalidad de sus dientes en una o ambas arcadas.",
        "precio": 600.00, "adelanto": 150.00, "duracion": 60,
    },
    {
        "nombre": "Diseño de Sonrisa Digital (Smile Design) y Rehabilitación Integral",
        "descripcion": "Planificación digital y clínica personalizada para transformar la estética y funcionalidad de la dentadura mediante carillas, coronas y alineación.",
        "precio": 250.00, "adelanto": 50.00, "duracion": 45,
    },
    {
        "nombre": "Férula Miorelajante / Placa Neuromiorrelajante (Anti-Bruxismo)",
        "descripcion": "Aparato de acrílico rígido a medida para proteger los dientes del desgaste nocturno, relajar los músculos masticatorios y aliviar la ATM.",
        "precio": 280.00, "adelanto": 70.00, "duracion": 45,
    },
]


def _resolver_especialidad(cur):
    """Devuelve el id de la especialidad, creándola si no existe."""
    cur.execute("SELECT id, nombre FROM especialidades")
    filas = cur.fetchall()
    candidatos = [_norm(c) for c in CANDIDATOS_ESPECIALIDAD]

    for f in filas:
        if _norm(f["nombre"]) in candidatos:
            return f["id"], False

    for f in filas:
        nf = _norm(f["nombre"])
        for c in candidatos:
            if c and (c in nf or nf in c):
                return f["id"], False

    cur.execute(
        "INSERT INTO especialidades (nombre, descripcion, estado, adelanto) "
        "VALUES (%s, %s, 'activo', 0) RETURNING id",
        (ESPECIALIDAD, DESCRIPCION_ESPECIALIDAD),
    )
    return cur.fetchone()["id"], True


def _asegurar_columnas(cur):
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS precio_base NUMERIC(10,2)")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS adelanto NUMERIC(10,2)")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS duracion_minutos INTEGER")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE")


def main():
    conn = get_connection()
    cur = conn.cursor()
    _asegurar_columnas(cur)

    esp_id, creada = _resolver_especialidad(cur)
    print(f"Especialidad '{ESPECIALIDAD}' -> id={esp_id}"
          f"{' (creada)' if creada else ''}\n")

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
    print("\n--- Catálogo Rehabilitación Oral ---")
    for r in cur.fetchall():
        print(
            f"  {r['nombre']} | S/ {r['precio_base']} | adelanto S/ {r['adelanto']} | "
            f"{r['duracion_minutos']} min | activo={r['activo']} | codigo={r['codigo']}"
        )

    conn.close()
    print(f"\nListo. Insertados: {insertados} | Actualizados: {actualizados}")


if __name__ == "__main__":
    main()
