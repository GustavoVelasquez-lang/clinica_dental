"""Seed idempotente: catálogo de tratamientos de CIRUGÍA ORAL (Clinica SELEDENT).

Uso:
    python seed_cirugia_oral.py

- Vincula los 7 tratamientos a la especialidad "Cirugía Oral".
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


ESPECIALIDAD = "Cirugía Oral"
CANDIDATOS_ESPECIALIDAD = ["cirugia oral"]

TRATAMIENTOS = [
    {
        "nombre": "Extracción de Muela del Juicio (Tercer Molar)",
        "descripcion": "Procedimiento para extraer molares retenidos, impactados en el hueso o que causan dolor e infecciones.",
        "precio": 250.00, "adelanto": 50.00, "duracion": 45,
    },
    {
        "nombre": "Extracción Dental Compleja / Exodoncia",
        "descripcion": "Retirada de dientes destruidos por caries profundas, fracturados, supernumerarios o por indicación ortodóntica.",
        "precio": 150.00, "adelanto": 40.00, "duracion": 40,
    },
    {
        "nombre": "Injerto Óseos y Elevación de Seno Maxilar",
        "descripcion": "Regeneración del volumen de hueso perdido en los maxilares para permitir la colocación segura de implantes.",
        "precio": 900.00, "adelanto": 250.00, "duracion": 60,
    },
    {
        "nombre": "Apicectomía (Cirugía Endodóntica)",
        "descripcion": "Eliminación quirúrgica de la punta de la raíz dental y del tejido infectado tras el fallo de una endodoncia previa.",
        "precio": 600.00, "adelanto": 150.00, "duracion": 60,
    },
    {
        "nombre": "Frenectomía (Labial o Lingual)",
        "descripcion": "Reubicación o corte de frenillos que afectan el habla, la movilidad de la lengua o generan separación dental.",
        "precio": 200.00, "adelanto": 50.00, "duracion": 30,
    },
    {
        "nombre": "Biopsia Bukal y Análisis Patológico",
        "descripcion": "Toma de muestra de tejido bucal en encía, lengua o mejilla para estudio histopatológico en laboratorio.",
        "precio": 300.00, "adelanto": 80.00, "duracion": 30,
    },
    {
        "nombre": "Drenaje de Absceso y Enucleación de Quiste Maxilar",
        "descripcion": "Apertura y descontaminación de infecciones agudas, o remoción quirúrgica de sacos quísticos en los maxilares.",
        "precio": 350.00, "adelanto": 100.00, "duracion": 45,
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
    print("\n--- Catálogo Cirugía Oral ---")
    for r in cur.fetchall():
        print(
            f"  {r['nombre']} | S/ {r['precio_base']} | adelanto S/ {r['adelanto']} | "
            f"{r['duracion_minutos']} min | activo={r['activo']} | codigo={r['codigo']}"
        )

    conn.close()
    print(f"\nListo. Insertados: {insertados} | Actualizados: {actualizados}")


if __name__ == "__main__":
    main()
