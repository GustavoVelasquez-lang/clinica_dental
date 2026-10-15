"""Seed idempotente: catálogo de tratamientos de ENDODONCIA (Clínica SELEDENT).

Uso:
    python seed_endodoncia.py

- Vincula los tratamientos a la especialidad "Endodoncia".
- Hace upsert por (id_especialidad, nombre): re-ejecutarlo no duplica.
- Desactiva el tratamiento genérico "Tratamiento de Conducto (Endodoncia)"
  (soft delete), ahora reemplazado por las opciones específicas por número
  de raíces y los procedimientos asociados.
"""
import unicodedata

from db import get_connection


def _norm(texto):
    """Normaliza a minúsculas sin acentos para comparar nombres."""
    texto = (texto or "").strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


ESPECIALIDAD = "Endodoncia"
CANDIDATOS_ESPECIALIDAD = ["endodoncia"]

TRATAMIENTOS = [
    {
        "nombre": "Endodoncia Unirradicular (Incisivos/Caninos)",
        "descripcion": "Tratamiento de conducto estándar en dientes de una sola raíz. Desinfección y sellado biocompatible.",
        "precio": 180.00, "adelanto": 50.00, "duracion": 45,
    },
    {
        "nombre": "Endodoncia Birradicular (Premolares)",
        "descripcion": "Tratamiento de conducto especializado en piezas de dos raíces para eliminar bacterias e inflamación.",
        "precio": 250.00, "adelanto": 50.00, "duracion": 60,
    },
    {
        "nombre": "Endodoncia Multirradicular (Molares)",
        "descripcion": "Procedimiento complejo de desinfección y limpieza en molares de 3 o más conductos.",
        "precio": 380.00, "adelanto": 80.00, "duracion": 75,
    },
    {
        "nombre": "Retratamiento Endodóntico",
        "descripcion": "Retiro del sellado antiguo, re-desinfección y nuevo sellado en piezas con infección recurrente.",
        "precio": 450.00, "adelanto": 100.00, "duracion": 75,
    },
    {
        "nombre": "Cirugía Apical (Apicectomía)",
        "descripcion": "Procedimiento quirúrgico para remover lesiones en el ápice de la raíz y preservar la pieza dental.",
        "precio": 600.00, "adelanto": 120.00, "duracion": 60,
    },
]

# Genérico que queda reemplazado por las opciones específicas.
DESACTIVAR = ["Tratamiento de Conducto (Endodoncia)"]


def _resolver_especialidad(cur):
    """Devuelve el id de 'Endodoncia' (coincidencia normalizada)."""
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
        f"No se encontró la especialidad 'Endodoncia'. Disponibles: {disponibles}"
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
    print(f"Especialidad 'Endodoncia' -> id={esp_id}\n")

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

    # Soft delete del genérico reemplazado.
    desactivados = 0
    for nombre in DESACTIVAR:
        cur.execute(
            "UPDATE tratamientos SET activo=FALSE "
            "WHERE id_especialidad = %s AND lower(nombre) = lower(%s) "
            "AND COALESCE(activo, TRUE) = TRUE",
            (esp_id, nombre),
        )
        desactivados += cur.rowcount
        if cur.rowcount:
            print(f"  - Desactivado (reemplazado por los específicos): {nombre}")

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

    print("\nCatálogo de 'Endodoncia' activo:")
    for t in catalogo:
        print(
            f"  - {t['nombre']} | S/ {t['precio_base']} | "
            f"adelanto S/ {t['adelanto']} | {t['duracion_minutos']} min"
        )

    print(
        f"\nListo. Insertados: {insertados} | Actualizados: {actualizados} "
        f"| Desactivados: {desactivados} | Total activos: {len(catalogo)}"
    )


if __name__ == "__main__":
    main()
