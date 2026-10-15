"""Seed idempotente: odontólogos de ODONTOLOGÍA GENERAL (Clínica SELEDENT).

Uso:
    python seed_odontologos_generales.py

IMPORTANTE — esquema real del proyecto (Supabase/PostgreSQL):
  - No existen las tablas `doctores` ni `doctor_especialidad`.
  - Los odontólogos se guardan en `usuarios` con `id_rol` = 3 (odontologo).
  - La relación odontólogo ↔ especialidad se guarda en `odontologo_especialidad`
    (odontologo_id, especialidad_id, estado).
  Por tanto, este seed sigue ese esquema para que los profesionales aparezcan
  disponibles al reservar una "Evaluación General / Primera Consulta".

Hace upsert por `correo` (usuarios) y por (odontologo_id, especialidad_id)
(odontologo_especialidad): re-ejecutarlo no genera duplicados.
"""
import unicodedata

from flask_bcrypt import Bcrypt

from db import get_connection

# Contraseña inicial para las cuentas de staff creadas (cámbiela luego).
CLAVE_INICIAL = "Seledent2026"

ESPECIALIDAD = "Odontología General"
CANDIDATOS_ESPECIALIDAD = ["odontologia general", "odontologia general / preventiva"]

ODONTOLOGOS = [
    {
        "nombre": "Mary",
        "apepaterno": "Pacheco",
        "apematerno": "Acevedo",
        "correo": "mary.pacheco@seledent.com",
        "telefono": "964112233",
        "tipo_documento": "DNI",
        "numero_documento": "45678912",
    },
    {
        "nombre": "Carlos",
        "apepaterno": "Mendoza",
        "apematerno": "Quispe",
        "correo": "carlos.mendoza@seledent.com",
        "telefono": "961445566",
        "tipo_documento": "DNI",
        "numero_documento": "41235678",
    },
    {
        "nombre": "Sofía",
        "apepaterno": "Ramos",
        "apematerno": "Yupanqui",
        "correo": "sofia.ramos@seledent.com",
        "telefono": "962778899",
        "tipo_documento": "DNI",
        "numero_documento": "47891234",
    },
]


def _norm(texto):
    """Normaliza a minúsculas sin acentos para comparar nombres."""
    texto = (texto or "").strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def _asegurar_columnas(cur):
    """Garantiza (idempotente) las columnas usadas por el seed."""
    cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telefono VARCHAR(30)")
    cur.execute(
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS perfil_completo BOOLEAN DEFAULT TRUE"
    )
    cur.execute(
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(20)"
    )
    cur.execute(
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS numero_documento VARCHAR(20)"
    )
    cur.execute(
        "ALTER TABLE odontologo_especialidad ADD COLUMN IF NOT EXISTS estado "
        "VARCHAR(20) DEFAULT 'activo'"
    )


def _resolver_especialidad(cur):
    """Devuelve el id de 'Odontología General' (coincidencia normalizada)."""
    cur.execute("SELECT id, nombre FROM especialidades")
    filas = cur.fetchall()
    candidatos = [_norm(c) for c in CANDIDATOS_ESPECIALIDAD]

    # Coincidencia exacta normalizada.
    for f in filas:
        if _norm(f["nombre"]) in candidatos:
            return f["id"]

    # Coincidencia por contención (p. ej. "Odontología General").
    for f in filas:
        nf = _norm(f["nombre"])
        for c in candidatos:
            if c and (c in nf or nf in c):
                return f["id"]

    disponibles = ", ".join(str(f["nombre"]) for f in filas)
    raise SystemExit(
        f"No se encontró la especialidad '{ESPECIALIDAD}'. Disponibles: {disponibles}"
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


def main():
    bcrypt = Bcrypt()
    conn = get_connection()
    cur = conn.cursor()
    _asegurar_columnas(cur)

    esp_id = _resolver_especialidad(cur)
    rol_id = _resolver_rol_odontologo(cur)
    print(f"Especialidad '{ESPECIALIDAD}' -> id={esp_id} | rol odontologo -> id={rol_id}\n")

    usuarios_ins = usuarios_upd = 0
    vinculos_ins = vinculos_upd = 0

    for o in ODONTOLOGOS:
        cur.execute(
            "SELECT id FROM usuarios WHERE lower(trim(correo)) = lower(trim(%s))",
            (o["correo"],),
        )
        existente = cur.fetchone()

        if existente:
            cur.execute(
                "UPDATE usuarios SET nombre=%s, apePaterno=%s, apeMaterno=%s, "
                "telefono=%s, tipo_documento=%s, numero_documento=%s, "
                "id_rol=%s, estado='ACTIVO', perfil_completo=TRUE "
                "WHERE id=%s",
                (o["nombre"], o["apepaterno"], o["apematerno"], o["telefono"],
                 o["tipo_documento"], o["numero_documento"], rol_id,
                 existente["id"]),
            )
            odontologo_id = existente["id"]
            usuarios_upd += 1
            print(f"  ~ Actualizado usuario: {o['nombre']} {o['apepaterno']} (id={odontologo_id})")
        else:
            clave_hash = bcrypt.generate_password_hash(CLAVE_INICIAL).decode("utf-8")
            cur.execute(
                "INSERT INTO usuarios (nombre, apePaterno, apeMaterno, correo, "
                "contrasenia, telefono, tipo_documento, numero_documento, "
                "id_rol, estado, perfil_completo) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVO', TRUE) "
                "RETURNING id",
                (o["nombre"], o["apepaterno"], o["apematerno"], o["correo"],
                 clave_hash, o["telefono"], o["tipo_documento"],
                 o["numero_documento"], rol_id),
            )
            odontologo_id = cur.fetchone()["id"]
            usuarios_ins += 1
            print(f"  + Insertado usuario: {o['nombre']} {o['apepaterno']} (id={odontologo_id})")

        # Vincular a la especialidad Odontología General.
        cur.execute(
            "SELECT id FROM odontologo_especialidad "
            "WHERE odontologo_id=%s AND especialidad_id=%s",
            (odontologo_id, esp_id),
        )
        vinculo = cur.fetchone()
        if vinculo:
            cur.execute(
                "UPDATE odontologo_especialidad SET estado='activo' WHERE id=%s",
                (vinculo["id"],),
            )
            vinculos_upd += 1
            print(f"      ~ Vinculado a la especialidad (relación existente)")
        else:
            cur.execute(
                "INSERT INTO odontologo_especialidad "
                "(odontologo_id, especialidad_id, estado) VALUES (%s, %s, 'activo')",
                (odontologo_id, esp_id),
            )
            vinculos_ins += 1
            print(f"      + Vinculado a la especialidad")

    conn.commit()

    # ── Verificación: mismos filtros que usa el endpoint de reserva ──
    cur.execute(
        "SELECT u.id, u.nombre, u.apePaterno, u.apeMaterno "
        "FROM odontologo_especialidad oe "
        "JOIN usuarios u ON u.id = oe.odontologo_id "
        "WHERE oe.especialidad_id = %s AND oe.estado = 'activo' "
        "AND u.estado = 'ACTIVO' "
        "ORDER BY u.nombre",
        (esp_id,),
    )
    disponibles = cur.fetchall()
    conn.close()

    print("\nOdontólogos disponibles en 'Odontología General':")
    for d in disponibles:
        completo = " ".join(
            p for p in [d["nombre"], d["apepaterno"], d["apematerno"]] if p
        )
        print(f"  - Dr(a). {completo} (id={d['id']})")

    print(
        f"\nListo. Usuarios insertados: {usuarios_ins} | actualizados: {usuarios_upd}"
        f" | Vínculos insertados: {vinculos_ins} | actualizados: {vinculos_upd}"
    )
    print(f"Contraseña inicial de cuentas nuevas: {CLAVE_INICIAL} (cámbiela luego)")


if __name__ == "__main__":
    main()
