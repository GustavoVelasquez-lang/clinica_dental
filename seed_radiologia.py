"""Seed idempotente: catálogo de tratamientos de RADIOLOGÍA (Clinica SELEDENT).

Uso:
    python seed_radiologia.py

- Vincula los 7 tratamientos a la especialidad "Radiología".
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


ESPECIALIDAD = "Radiología"
CANDIDATOS_ESPECIALIDAD = ["radiologia", "diagnostico por imagenes", "radiologia e imagen 3d"]

TRATAMIENTOS = [
    {
        "nombre": "Angioplastia y Colocación de Stent",
        "descripcion": "Apertura de arterias obstruidas mediante balón y colocación de malla metálica (stent) guiada por fluoroscopia o tomografía.",
        "precio": 1500.00, "adelanto": 400.00, "duracion": 60,
    },
    {
        "nombre": "Embolización Vascular (Aneurismas / Miomas)",
        "descripcion": "Oclusión selectiva de vasos sanguíneos con coils o sustancias embolizantes para tratar aneurismas o reducir miomas.",
        "precio": 1800.00, "adelanto": 500.00, "duracion": 90,
    },
    {
        "nombre": "Quimioembolización",
        "descripcion": "Inyección directa de quimioterapia y agentes oclusivos en las arterias que nutren lesiones tumorales.",
        "precio": 2200.00, "adelanto": 600.00, "duracion": 90,
    },
    {
        "nombre": "Drenaje Percutáneo de Abscesos y Colecciones",
        "descripcion": "Evacuación guiada por ecografía o tomografía de colecciones infectadas mediante catéter percutáneo.",
        "precio": 450.00, "adelanto": 120.00, "duracion": 45,
    },
    {
        "nombre": "Infiltración y Bloqueo del Dolor Guiado por Imágenes",
        "descripcion": "Inyección precisa de antiinflamatorios y analgésicos en articulaciones o columna vertebral para el alivio del dolor crónico.",
        "precio": 250.00, "adelanto": 60.00, "duracion": 30,
    },
    {
        "nombre": "Ablación por Radiofrecuencia / Microondas",
        "descripcion": "Destrucción térmica localizada de tumores mediante aguja especial guiada por imágenes tomográficas o ecográficas.",
        "precio": 1600.00, "adelanto": 450.00, "duracion": 60,
    },
    {
        "nombre": "Radioterapia de Haz Externo / Braquiterapia",
        "descripcion": "Planificación y aplicación de radiación ionizante milimétrica dirigida para tratamiento de tumores o colocación de fuentes radiactivas internas.",
        "precio": 2000.00, "adelanto": 500.00, "duracion": 60,
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
    print("\n--- Catálogo Radiología ---")
    for r in cur.fetchall():
        print(
            f"  {r['nombre']} | S/ {r['precio_base']} | adelanto S/ {r['adelanto']} | "
            f"{r['duracion_minutos']} min | activo={r['activo']} | codigo={r['codigo']}"
        )

    conn.close()
    print(f"\nListo. Insertados: {insertados} | Actualizados: {actualizados}")


if __name__ == "__main__":
    main()
