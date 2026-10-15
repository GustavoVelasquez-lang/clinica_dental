"""Seed idempotente: catálogo de tratamientos de ESTÉTICA DENTAL (Clinica SELEDENT).

Uso:
    python seed_estetica.py

- Vincula los tratamientos a la especialidad "Estética Dental".
- Hace upsert por (id_especialidad, nombre): re-ejecutarlo no duplica.
- Si un tratamiento ya existe (p. ej. "Blanqueamiento Dental LED"), lo actualiza.
"""
import unicodedata

from db import get_connection


def _norm(texto):
    texto = (texto or "").strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


ESPECIALIDAD = "Estética Dental"
CANDIDATOS_ESPECIALIDAD = ["estetica dental"]

TRATAMIENTOS = [
    {
        "nombre": "Diseño de Sonrisa Digital (DSD)",
        "descripcion": "Planificación digital en 3D mediante fotos y videos para simular tu nueva sonrisa antes de empezar.",
        "precio": 150.00, "adelanto": 50.00, "duracion": 45,
    },
    {
        "nombre": "Carillas de Resina (Composite)",
        "descripcion": "Láminas estéticas modeladas directamente sobre el diente en una sesión para corregir manchas o pequeños espacios.",
        "precio": 180.00, "adelanto": 50.00, "duracion": 60,
    },
    {
        "nombre": "Carillas de Porcelana o Cerámica",
        "descripcion": "Finísimas láminas de laboratorio de alta resistencia y brillo natural idéntico al esmalte.",
        "precio": 900.00, "adelanto": 200.00, "duracion": 60,
    },
    {
        "nombre": "Blanqueamiento Dental LED",
        "descripcion": "Aclarado profesional del tono dental en consultorio mediante geles activados por luz LED.",
        "precio": 250.00, "adelanto": 50.00, "duracion": 60,
    },
    {
        "nombre": "Gingivoplastia (Contorneo de Encías)",
        "descripcion": "Microcirugía estética para corregir la sonrisa gingival y dar mayor simetría a los dientes.",
        "precio": 350.00, "adelanto": 100.00, "duracion": 45,
    },
    {
        "nombre": "Corona de Zirconio o Disilicato de Litio",
        "descripcion": "Prótesis fija libre de metal de alta estética para dientes severamente dañados o con endodoncia.",
        "precio": 700.00, "adelanto": 150.00, "duracion": 60,
    },
]


def _norm_candidatos():
    return [_norm(c) for c in CANDIDATOS_ESPECIALIDAD]


def _resolver_especialidad(cur):
    """Devuelve el id de 'Estética Dental' (coincidencia normalizada)."""
    cur.execute("SELECT id, nombre FROM especialidades")
    filas = cur.fetchall()
    candidatos = _norm_candidatos()

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
        f"No se encontró la especialidad 'Estética Dental'. Disponibles: {disponibles}"
    )


def _asegurar_columnas(cur):
    """Garantiza (idempotente) las columnas usadas por el seed."""
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS precio_base NUMERIC(10,2)")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS adelanto NUMERIC(10,2)")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS duracion_minutos INTEGER")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE")


def main():
    conn = get_connection()
    cur = conn.cursor()
    _asegurar_columnas(cur)

    esp_id = _resolver_especialidad(cur)
    print(f"Especialidad 'Estética Dental' -> id={esp_id}\n")

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

    # Verificación: lo mismo que muestra el catálogo público.
    cur.execute(
        "SELECT id_tratamiento, nombre, precio_base, adelanto, duracion_minutos "
        "FROM tratamientos WHERE id_especialidad = %s AND COALESCE(activo, TRUE) = TRUE "
        "ORDER BY nombre",
        (esp_id,),
    )
    catalogo = cur.fetchall()
    conn.close()

    print("\nCatálogo de 'Estética Dental' activo:")
    for t in catalogo:
        print(
            f"  - {t['nombre']} | S/ {t['precio_base']} | "
            f"adelanto S/ {t['adelanto']} | {t['duracion_minutos']} min"
        )

    print(
        f"\nListo. Insertados: {insertados} | Actualizados: {actualizados} "
        f"| Total activos: {len(catalogo)}"
    )


if __name__ == "__main__":
    main()
