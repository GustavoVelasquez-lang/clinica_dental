"""Seed idempotente: staff médico y su relación con los tratamientos
(Clínica SELEDENT — Supabase/PostgreSQL).

Uso:
    python seed_staff_medico.py

Qué hace:
  1. Garantiza la columna `cmp` en `usuarios` y crea la tabla intermedia
     `doctor_tratamiento` (doctor_id, id_tratamiento).
  2. Registra un equipo de 6 especialistas clave en `usuarios` (id_rol=odontologo)
     con su número de CMP, y los vincula a sus especialidades
     (`odontologo_especialidad`).
  3. Asigna a cada doctor un subconjunto de tratamientos de su especialidad en
     `doctor_tratamiento`.
  4. ANTES de confirmar, valida que NINGÚN tratamiento quede huérfano (sin al
     menos un doctor). Si hay huérfanos, revierte todo y los lista en consola.

Es idempotente: upsert por `correo` (usuarios), por (odontologo_id,
especialidad_id) y por (doctor_id, id_tratamiento).
"""
import unicodedata

from flask_bcrypt import Bcrypt

from db import get_connection

try:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Contraseña inicial para las cuentas de staff creadas (cámbiela luego).
CLAVE_INICIAL = "Seledent2026"

# ── Equipo médico (6 especialistas) ────────────────────────────────────────
# Cada doctor define sus asignaciones por especialidad. `tratamientos` admite
# una lista de nombres (subconjunto) o "todos" para toda la especialidad.
DOCTORES = [
    {
        "nombre": "Ricardo",
        "apepaterno": "Salazar",
        "apematerno": "Dávila",
        "correo": "ricardo.salazar@seledent.com",
        "telefono": "964100201",
        "tipo_documento": "DNI",
        "numero_documento": "43780112",
        "cmp": "CMP 45231",
        "asignaciones": [
            {
                "especialidad": "Cirugía Oral",
                "tratamientos": [
                    "Extracción de Muela del Juicio (Tercer Molar)",
                    "Extracción Dental Compleja / Exodoncia",
                    "Injerto Óseos y Elevación de Seno Maxilar",
                    "Frenectomía (Labial o Lingual)",
                    "Drenaje de Absceso y Enucleación de Quiste Maxilar",
                ],
            },
            {
                "especialidad": "Implantología",
                "tratamientos": ["Implante Unitario", "Prótesis Híbrida (All-on-4 / All-on-6)"],
            },
            {
                "especialidad": "Periodoncia",
                "tratamientos": ["Cirugía de Colgajo Periodontal", "Mantenimiento Periodontal"],
            },
        ],
    },
    {
        "nombre": "Valeria",
        "apepaterno": "Núñez",
        "apematerno": "Cárdenas",
        "correo": "valeria.nunez@seledent.com",
        "telefono": "964100202",
        "tipo_documento": "DNI",
        "numero_documento": "47890123",
        "cmp": "CMP 48510",
        "asignaciones": [
            {
                "especialidad": "Periodoncia",
                "tratamientos": [
                    "Profilaxis Dental Profunda",
                    "Raspado y Alisado Radicular (Curetaje)",
                    "Injerto de Tejido Blando (Cirugía Plástica Periodontal)",
                    "Injertos Óseos y Regeneración Tisular Guiada (RTG)",
                ],
            },
            {
                "especialidad": "Implantología",
                "tratamientos": [
                    "Puente sobre Implantes",
                    "Sobredentadura sobre Implantes",
                ],
            },
            {
                "especialidad": "Estética Dental",
                "tratamientos": ["Gingivoplastia (Contorneo de Encías)"],
            },
        ],
    },
    {
        "nombre": "Andrés",
        "apepaterno": "Cordero",
        "apematerno": "Lira",
        "correo": "andres.cordero@seledent.com",
        "telefono": "964100202",
        "tipo_documento": "DNI",
        "numero_documento": "46782341",
        "cmp": "CMP 51234",
        "asignaciones": [
            {"especialidad": "Ortodoncia", "tratamientos": "todos"},
            {
                "especialidad": "Odontopediatría",
                "tratamientos": [
                    "Profilaxis Infantil y Aplicación de Flúor",
                    "Sellantes de Fosas y Fisuras (por pieza)",
                ],
            },
        ],
    },
    {
        "nombre": "Camila",
        "apepaterno": "Rojas",
        "apematerno": "Medina",
        "correo": "camila.rojas@seledent.com",
        "telefono": "964100204",
        "tipo_documento": "DNI",
        "numero_documento": "45391287",
        "cmp": "CMP 48901",
        "asignaciones": [
            {"especialidad": "Endodoncia", "tratamientos": "todos"},
            {
                "especialidad": "Cirugía Oral",
                "tratamientos": [
                    "Apicectomía (Cirugía Endodóntica)",
                    "Biopsia Bukal y Análisis Patológico",
                ],
            },
        ],
    },
    {
        "nombre": "Lucía",
        "apepaterno": "Fernández",
        "apematerno": "Soto",
        "correo": "lucia.fernandez@seledent.com",
        "telefono": "964100205",
        "tipo_documento": "DNI",
        "numero_documento": "43218765",
        "cmp": "CMP 47650",
        "asignaciones": [
            {
                "especialidad": "Odontopediatría",
                "tratamientos": [
                    "Obturación Pediátrica (Cura y Resina)",
                    "Corona Pediátrica (Acero Inoxidable / Estética)",
                    "Pulpotomía / Pulpectomía (Endodoncia Infantil)",
                    "Mantenedor de Espacio (Fijo o Removible)",
                    "Atención Infantil con Sedación Consciente (Óxido Nitroso)",
                ],
            },
            {"especialidad": "Odontología General", "tratamientos": "todos"},
            {
                "especialidad": "Estética Dental",
                "tratamientos": [
                    "Blanqueamiento Dental LED",
                    "Diseño de Sonrisa Digital (DSD)",
                ],
            },
        ],
    },
    {
        "nombre": "Marco",
        "apepaterno": "Ríos",
        "apematerno": "Valverde",
        "correo": "marco.rios@seledent.com",
        "telefono": "964100206",
        "tipo_documento": "DNI",
        "numero_documento": "41120983",
        "cmp": "CMP 52110",
        "asignaciones": [
            {"especialidad": "Radiología", "tratamientos": "todos"},
            {"especialidad": "Rehabilitación Oral", "tratamientos": "todos"},
            {
                "especialidad": "Estética Dental",
                "tratamientos": [
                    "Carillas de Resina (Composite)",
                    "Carillas de Porcelana o Cerámica",
                    "Corona de Zirconio o Disilicato de Litio",
                ],
            },
        ],
    },
]


def _norm(texto):
    """Normaliza a minúsculas sin acentos para comparar nombres."""
    texto = (texto or "").strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def _asegurar_estructura(cur):
    """Garantiza (idempotente) la columna CMP y la tabla doctor_tratamiento."""
    cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS cmp VARCHAR(20)")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS doctor_tratamiento (
            id             SERIAL PRIMARY KEY,
            doctor_id      INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            id_tratamiento INTEGER NOT NULL REFERENCES tratamientos(id_tratamiento) ON DELETE CASCADE,
            estado         VARCHAR(20) DEFAULT 'activo',
            created_at     TIMESTAMP DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_doctor_tratamiento "
        "ON doctor_tratamiento (doctor_id, id_tratamiento)"
    )


def _resolver_rol_odontologo(cur):
    """Devuelve el id del rol 'odontologo' (lo crea si no existe)."""
    cur.execute("SELECT id FROM roles WHERE lower(nombre) = 'odontologo'")
    fila = cur.fetchone()
    if fila:
        return fila["id"]
    cur.execute(
        "INSERT INTO roles (nombre, estado) VALUES ('odontologo', 'activo') RETURNING id"
    )
    return cur.fetchone()["id"]


def _mapa_especialidades(cur):
    """dict {nombre_normalizado: (id, nombre_real)} de todas las especialidades."""
    cur.execute("SELECT id, nombre FROM especialidades")
    return {_norm(f["nombre"]): (f["id"], f["nombre"]) for f in cur.fetchall()}


def _tratamientos_de(cur, esp_id):
    """dict {nombre_normalizado: (id_tratamiento, nombre_real)} de una especialidad."""
    cur.execute(
        "SELECT id_tratamiento, nombre FROM tratamientos WHERE id_especialidad = %s",
        (esp_id,),
    )
    return {_norm(f["nombre"]): (f["id_tratamiento"], f["nombre"]) for f in cur.fetchall()}


def _vincular_especialidad(cur, odontologo_id, esp_id):
    """Upsert de la relación odontólogo ↔ especialidad."""
    cur.execute(
        "SELECT id FROM odontologo_especialidad "
        "WHERE odontologo_id = %s AND especialidad_id = %s",
        (odontologo_id, esp_id),
    )
    fila = cur.fetchone()
    if fila:
        cur.execute(
            "UPDATE odontologo_especialidad SET estado = 'activo' WHERE id = %s",
            (fila["id"],),
        )
    else:
        cur.execute(
            "INSERT INTO odontologo_especialidad (odontologo_id, especialidad_id, estado) "
            "VALUES (%s, %s, 'activo')",
            (odontologo_id, esp_id),
        )


def _vincular_tratamiento(cur, doctor_id, id_tratamiento):
    """Upsert de la relación doctor ↔ tratamiento."""
    cur.execute(
        """
        INSERT INTO doctor_tratamiento (doctor_id, id_tratamiento, estado)
        VALUES (%s, %s, 'activo')
        ON CONFLICT (doctor_id, id_tratamiento)
        DO UPDATE SET estado = 'activo'
        """,
        (doctor_id, id_tratamiento),
    )


def _tratamientos_huerfanos(cur):
    """Lista de tratamientos sin ningún doctor asignado."""
    cur.execute(
        """
        SELECT t.id_tratamiento, e.nombre AS especialidad, t.nombre
        FROM tratamientos t
        JOIN especialidades e ON e.id = t.id_especialidad
        WHERE NOT EXISTS (
            SELECT 1 FROM doctor_tratamiento dt
            WHERE dt.id_tratamiento = t.id_tratamiento
        )
        ORDER BY e.nombre, t.nombre
        """
    )
    return cur.fetchall()


def main():
    bcrypt = Bcrypt()
    conn = get_connection()
    cur = conn.cursor()
    _asegurar_estructura(cur)

    rol_id = _resolver_rol_odontologo(cur)
    especialidades = _mapa_especialidades(cur)
    print(f"Rol odontologo -> id={rol_id} | especialidades disponibles: {len(especialidades)}\n")

    usuarios_ins = usuarios_upd = 0
    vinculos = asignaciones = 0

    for d in DOCTORES:
        # 1) Alta / actualización del doctor.
        cur.execute(
            "SELECT id FROM usuarios WHERE lower(trim(correo)) = lower(trim(%s))",
            (d["correo"],),
        )
        existente = cur.fetchone()
        if existente:
            cur.execute(
                "UPDATE usuarios SET nombre=%s, apePaterno=%s, apeMaterno=%s, "
                "telefono=%s, tipo_documento=%s, numero_documento=%s, cmp=%s, "
                "id_rol=%s, estado='ACTIVO', perfil_completo=TRUE WHERE id=%s",
                (d["nombre"], d["apepaterno"], d["apematerno"], d["telefono"],
                 d["tipo_documento"], d["numero_documento"], d["cmp"], rol_id,
                 existente["id"]),
            )
            doctor_id = existente["id"]
            usuarios_upd += 1
            print(f"  ~ Doctor actualizado: {d['nombre']} {d['apepaterno']} "
                  f"(id={doctor_id}, {d['cmp']})")
        else:
            clave_hash = bcrypt.generate_password_hash(CLAVE_INICIAL).decode("utf-8")
            cur.execute(
                "INSERT INTO usuarios (nombre, apePaterno, apeMaterno, correo, "
                "contrasenia, telefono, tipo_documento, numero_documento, cmp, "
                "id_rol, estado, perfil_completo) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVO', TRUE) "
                "RETURNING id",
                (d["nombre"], d["apepaterno"], d["apematerno"], d["correo"],
                 clave_hash, d["telefono"], d["tipo_documento"],
                 d["numero_documento"], d["cmp"], rol_id),
            )
            doctor_id = cur.fetchone()["id"]
            usuarios_ins += 1
            print(f"  + Doctor insertado: {d['nombre']} {d['apepaterno']} "
                  f"(id={doctor_id}, {d['cmp']})")

        # 2) Especialidades y tratamientos asignados.
        for asignacion in d["asignaciones"]:
            clave_esp = _norm(asignacion["especialidad"])
            if clave_esp not in especialidades:
                raise SystemExit(
                    f"No existe la especialidad '{asignacion['especialidad']}' "
                    f"(doctor {d['nombre']})"
                )
            esp_id, esp_real = especialidades[clave_esp]
            _vincular_especialidad(cur, doctor_id, esp_id)
            vinculos += 1

            catalogo = _tratamientos_de(cur, esp_id)
            if asignacion["tratamientos"] == "todos":
                objetivos = list(catalogo.values())
            else:
                objetivos = []
                for nombre in asignacion["tratamientos"]:
                    clave_t = _norm(nombre)
                    if clave_t not in catalogo:
                        raise SystemExit(
                            f"El tratamiento '{nombre}' no existe en "
                            f"'{esp_real}' (doctor {d['nombre']})"
                        )
                    objetivos.append(catalogo[clave_t])

            for id_tratamiento, nombre_trat in objetivos:
                _vincular_tratamiento(cur, doctor_id, id_tratamiento)
                asignaciones += 1
            print(f"      · {esp_real}: {len(objetivos)} tratamiento(s) asignado(s)")

    # ── VALIDACIÓN DE INTEGRIDAD (antes de confirmar) ──────────────────────
    huerfanos = _tratamientos_huerfanos(cur)

    print("\n── Validación de integridad ──")
    if huerfanos:
        print(f"❌ Hay {len(huerfanos)} tratamiento(s) HUÉRFANO(S) (sin doctor):")
        for h in huerfanos:
            print(f"   - [{h['especialidad']}] {h['nombre']} (id={h['id_tratamiento']})")
        conn.rollback()
        conn.close()
        raise SystemExit(
            "Cambios revertidos: asigna al menos un doctor a cada tratamiento "
            "y vuelve a ejecutar el seed."
        )

    print("✅ Todos los tratamientos tienen al menos un doctor asignado.")

    conn.commit()

    # ── Resumen final ──────────────────────────────────────────────────────
    cur.execute("SELECT count(*) AS n FROM tratamientos")
    total_trat = cur.fetchone()["n"]
    cur.execute("SELECT count(DISTINCT doctor_id) AS n FROM doctor_tratamiento")
    total_doctores = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM doctor_tratamiento")
    total_asig = cur.fetchone()["n"]
    conn.close()

    print(
        f"\nListo. Usuarios insertados: {usuarios_ins} | actualizados: {usuarios_upd}"
        f" | Vínculos especialidad: {vinculos} | Asignaciones tratamiento: {asignaciones}"
    )
    print(
        f"Tratamientos: {total_trat} | Doctores con tratamientos: {total_doctores} "
        f"| Filas en doctor_tratamiento: {total_asig}"
    )
    print(f"Contraseña inicial de cuentas nuevas: {CLAVE_INICIAL} (cámbiela luego)")


if __name__ == "__main__":
    main()
