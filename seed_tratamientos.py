"""Seed idempotente: registro inicial de tratamientos de Clinica SELEDENT.

Uso:
    python seed_tratamientos.py

Vincula cada tratamiento con su especialidad (por nombre, con creación
automática si no existe) y hace upsert por (id_especialidad, nombre).
Ejecutarlo varias veces no genera duplicados.
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


GRUPOS = [
    {
        "especialidad": "Odontología General / Preventiva",
        "candidatos": ["odontologia general", "odontologia general / preventiva"],
        "descripcion": "Prevención, diagnóstico y tratamiento integral de tu salud bucal.",
        "tratamientos": [
            {
                "nombre": "Evaluación General / Primera Consulta",
                "precio": 50.00, "adelanto": 50.00, "duracion": 30,
                "descripcion": "Diagnóstico inicial y plan de tratamiento personalizado.",
            },
            {
                "nombre": "Profilaxis Dental (Limpieza Bucal)",
                "precio": 80.00, "adelanto": 30.00, "duracion": 45,
                "descripcion": "Eliminación de placa y sarro para mantener dientes y encías sanos.",
            },
            {
                "nombre": "Curación con Resina Estética",
                "precio": 70.00, "adelanto": 30.00, "duracion": 40,
                "descripcion": "Restauración de caries con resina del color natural del diente.",
            },
            {
                "nombre": "Extracción Dental Simple",
                "precio": 90.00, "adelanto": 30.00, "duracion": 45,
                "descripcion": "Retiro de una pieza dental dañada o infectada sin complicaciones.",
            },
        ],
    },
    {
        "especialidad": "Estética Dental",
        "candidatos": ["estetica dental"],
        "descripcion": "Mejoramos tu sonrisa con blanqueamiento, carillas y diseños personalizados.",
        "tratamientos": [
            {
                "nombre": "Blanqueamiento Dental LED",
                "precio": 250.00, "adelanto": 50.00, "duracion": 60,
                "descripcion": "Aclarado del tono dental con luz LED, con resultados visibles.",
            },
        ],
    },
    {
        "especialidad": "Ortodoncia",
        "candidatos": ["ortodoncia"],
        "descripcion": "Alineamos tus dientes con brackets y alineadores para una sonrisa armoniosa.",
        "tratamientos": [
            {
                "nombre": "Instalación de Brackets",
                "precio": 800.00, "adelanto": 100.00, "duracion": 60,
                "descripcion": "Colocación de brackets para iniciar el tratamiento de ortodoncia.",
            },
        ],
    },
    {
        "especialidad": "Endodoncia",
        "candidatos": ["endodoncia"],
        "descripcion": "Tratamiento de conductos que salva piezas dentales infectadas o muy dañadas.",
        "tratamientos": [
            {
                "nombre": "Tratamiento de Conducto (Endodoncia)",
                "precio": 200.00, "adelanto": 50.00, "duracion": 60,
                "descripcion": "Elimina la infección del nervio dental y preserva la pieza.",
            },
        ],
    },
    {
        "especialidad": "Diagnóstico por Imágenes",
        "candidatos": ["diagnostico por imagenes", "radiologia e imagen 3d", "radiologia"],
        "descripcion": "Radiografías y estudios de imagen para un diagnóstico preciso.",
        "tratamientos": [
            {
                "nombre": "Radiografía Dental Periapical",
                "precio": 30.00, "adelanto": 30.00, "duracion": 15,
                "descripcion": "Imagen de la pieza dental y su raíz para un diagnóstico preciso.",
            },
        ],
    },
    {
        "especialidad": "Implantología",
        "candidatos": ["implantologia"],
        "descripcion": "Reposición de piezas dentales con implantes de titanio y prótesis fijas.",
        "tratamientos": [
            {
                "nombre": "Implante Unitario",
                "precio": 1200.00, "adelanto": 300.00, "duracion": 60,
                "descripcion": "Reemplazo de un solo diente mediante un implante y una corona independiente. No desgasta los dientes vecinos.",
            },
            {
                "nombre": "Puente sobre Implantes",
                "precio": 2800.00, "adelanto": 700.00, "duracion": 90,
                "descripcion": "Reposición de varias piezas seguidas mediante un puente fijo anclado a implantes, sin desgastar dientes sanos.",
            },
            {
                "nombre": "Prótesis Híbrida (All-on-4 / All-on-6)",
                "precio": 6500.00, "adelanto": 1500.00, "duracion": 120,
                "descripcion": "Rehabilitación completa de una arcada sobre 4 o 6 implantes estratégicamente colocados. Dentadura fija que no se mueve.",
            },
            {
                "nombre": "Sobredentadura sobre Implantes",
                "precio": 3500.00, "adelanto": 800.00, "duracion": 90,
                "descripcion": "Prótesis completa sujeta a los implantes con sistema de anclaje (retech o barras). Estable y removible para una fácil limpieza.",
            },
        ],
    },
]


def _asegurar_columnas(cur):
    """Garantiza las columnas usadas por el seed (idempotente)."""
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS precio_base NUMERIC(10,2)")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS adelanto NUMERIC(10,2)")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS duracion_minutos INTEGER")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE")
    cur.execute(
        "ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()"
    )


def _resolver_especialidad(cur, grupo):
    """Devuelve el id de la especialidad del grupo, creándola si no existe."""
    cur.execute("SELECT id, nombre FROM especialidades")
    filas = cur.fetchall()
    candidatos = [_norm(c) for c in grupo["candidatos"]]

    # Coincidencia exacta normalizada.
    for f in filas:
        if _norm(f["nombre"]) in candidatos:
            return f["id"], False

    # Coincidencia por contención (p. ej. "Odontología General").
    for f in filas:
        nf = _norm(f["nombre"])
        for c in candidatos:
            if c and (c in nf or nf in c):
                return f["id"], False

    # No existe: se crea.
    cur.execute(
        "INSERT INTO especialidades (nombre, descripcion, estado, adelanto) "
        "VALUES (%s, %s, 'activo', 0) RETURNING id",
        (grupo["especialidad"], grupo.get("descripcion")),
    )
    return cur.fetchone()["id"], True


def main():
    conn = get_connection()
    cur = conn.cursor()
    _asegurar_columnas(cur)

    insertados = actualizados = creadas = 0

    for grupo in GRUPOS:
        esp_id, creada = _resolver_especialidad(cur, grupo)
        if creada:
            creadas += 1
            print(f"  + Especialidad creada: {grupo['especialidad']} (id={esp_id})")

        for t in grupo["tratamientos"]:
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
                print(f"    ~ Actualizado: {t['nombre']}")
            else:
                cur.execute(
                    "INSERT INTO tratamientos (id_especialidad, nombre, descripcion, "
                    "precio_base, adelanto, duracion_minutos, activo) "
                    "VALUES (%s, %s, %s, %s, %s, %s, TRUE)",
                    (esp_id, t["nombre"], t["descripcion"], t["precio"],
                     t["adelanto"], t["duracion"]),
                )
                insertados += 1
                print(f"    + Insertado: {t['nombre']}")

    conn.commit()
    conn.close()
    print(
        f"\nListo. Especialidades creadas: {creadas} | "
        f"Tratamientos insertados: {insertados} | "
        f"actualizados: {actualizados}"
    )


if __name__ == "__main__":
    main()
