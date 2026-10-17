"""Seed idempotente: catálogo de tratamientos de ODONTOPEDIATRÍA (Clinica SELEDENT).

Uso:
    python seed_odontopediatria.py

- Busca el id_especialidad de "Odontopediatría" por nombre y lo crea si no existe.
- Vincula los 7 tratamientos a esa especialidad.
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


ESPECIALIDAD = "Odontopediatría"
CANDIDATOS_ESPECIALIDAD = ["odontopediatria"]
DESCRIPCION_ESPECIALIDAD = "Odontología para niños: prevención y tratamiento de la salud bucal infantil."

TRATAMIENTOS = [
    {
        "nombre": "Profilaxis Infantil y Aplicación de Flúor",
        "descripcion": "Limpieza dental para niños, enseñanza de cepillado y aplicación de barniz/gel de flúor para fortalecer el esmalte contra las caries.",
        "precio": 70.00, "adelanto": 20.00, "duracion": 30,
    },
    {
        "nombre": "Sellantes de Fosas y Fisuras (por pieza)",
        "descripcion": "Recubrimiento protector de resina en los surcos profundos de molares para evitar la acumulación de placa y la formación de caries.",
        "precio": 50.00, "adelanto": 15.00, "duracion": 20,
    },
    {
        "nombre": "Obturación Pediátrica (Cura y Resina)",
        "descripcion": "Eliminación de caries en dientes temporales o permanentes jóvenes y restauración estética con resina del color del diente.",
        "precio": 80.00, "adelanto": 20.00, "duracion": 30,
    },
    {
        "nombre": "Corona Pediátrica (Acero Inoxidable / Estética)",
        "descripcion": "Colocación de funda o corona infantil para proteger y restaurar la función de un diente temporal con gran destrucción.",
        "precio": 180.00, "adelanto": 50.00, "duracion": 45,
    },
    {
        "nombre": "Pulpotomía / Pulpectomía (Endodoncia Infantil)",
        "descripcion": "Tratamiento del nervio en dientes de leche afectados por caries profundas para prevenir dolor, infecciones y extracciones prematuras.",
        "precio": 120.00, "adelanto": 30.00, "duracion": 45,
    },
    {
        "nombre": "Mantenedor de Espacio (Fijo o Removible)",
        "descripcion": "Aparato diseñado para conservar la brecha de un diente de leche perdido prematuramente y permitir la correcta erupción del definitivo.",
        "precio": 250.00, "adelanto": 70.00, "duracion": 45,
    },
    {
        "nombre": "Atención Infantil con Sedación Consciente (Óxido Nitroso)",
        "descripcion": "Manejo de conducta y relajación con gas de la risa para pacientes pediátricos temerosos o ansiosos durante el procedimiento.",
        "precio": 200.00, "adelanto": 50.00, "duracion": 45,
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
    print("\n--- Catálogo Odontopediatría ---")
    for r in cur.fetchall():
        print(
            f"  {r['nombre']} | S/ {r['precio_base']} | adelanto S/ {r['adelanto']} | "
            f"{r['duracion_minutos']} min | activo={r['activo']} | codigo={r['codigo']}"
        )

    conn.close()
    print(f"\nListo. Insertados: {insertados} | Actualizados: {actualizados}")


if __name__ == "__main__":
    main()
