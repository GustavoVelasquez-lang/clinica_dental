"""Seed idempotente: catálogo de tratamientos de ORTODONCIA (Clinica SELEDENT).

Uso:
    python seed_ortodoncia.py

- Vincula los 5 tratamientos a la especialidad "Ortodoncia".
- Hace upsert por (id_especialidad, nombre): re-ejecutarlo no duplica.
- Desactiva el tratamiento genérico "Instalación de Brackets" (soft delete),
  ahora reemplazado por las opciones específicas de brackets.
"""
import unicodedata

from db import get_connection


def _norm(texto):
    texto = (texto or "").strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


ESPECIALIDAD = "Ortodoncia"

TRATAMIENTOS = [
    {
        "nombre": "Ortodoncia Interceptiva / Preventiva (Niños)",
        "descripcion": "Guía del crecimiento maxilar y corrección de hábitos en niños de 6 a 12 años.",
        "precio": 500.00, "adelanto": 80.00, "duracion": 45,
    },
    {
        "nombre": "Brackets Metálicos Tradicionales",
        "descripcion": "Corrección de alineación dental mediante aparatología fija de alta resistencia.",
        "precio": 800.00, "adelanto": 100.00, "duracion": 60,
    },
    {
        "nombre": "Brackets Estéticos (Zafiro / Cerámica)",
        "descripcion": "Brackets discretos del color del diente o transparentes de cristal de zafiro.",
        "precio": 1500.00, "adelanto": 150.00, "duracion": 60,
    },
    {
        "nombre": "Brackets Autoligados",
        "descripcion": "Sistema con clip de baja fricción que acelera el movimiento dental sin ligas.",
        "precio": 1800.00, "adelanto": 200.00, "duracion": 60,
    },
    {
        "nombre": "Alineadores Transparentes (Ortodoncia Invisible)",
        "descripcion": "Férulas invisibles y removibles a la medida para una ortodoncia estético-cómoda.",
        "precio": 3500.00, "adelanto": 300.00, "duracion": 45,
    },
]

# Genérico que queda reemplazado por las opciones específicas.
DESACTIVAR = ["Instalación de Brackets"]


def _resolver_especialidad(cur):
    cur.execute("SELECT id, nombre FROM especialidades")
    filas = cur.fetchall()
    for f in filas:
        if _norm(f["nombre"]) == _norm(ESPECIALIDAD):
            return f["id"]
    disponibles = ", ".join(str(f["nombre"]) for f in filas)
    raise SystemExit(
        f"No se encontró la especialidad '{ESPECIALIDAD}'. Disponibles: {disponibles}"
    )


def main():
    conn = get_connection()
    cur = conn.cursor()

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

    for nombre in DESACTIVAR:
        cur.execute(
            "UPDATE tratamientos SET activo=FALSE "
            "WHERE id_especialidad = %s AND lower(nombre) = lower(%s)",
            (esp_id, nombre),
        )
        if cur.rowcount:
            print(f"  - Desactivado (oculto del selector): {nombre}")

    conn.commit()
    conn.close()
    print(f"\nListo. Insertados: {insertados} | Actualizados: {actualizados}")


if __name__ == "__main__":
    main()
