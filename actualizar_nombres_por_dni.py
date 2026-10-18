"""Actualiza nombres y apellidos de los usuarios a partir de su DNI,
consultando la API RENIEC de Decolecta.

Regla clave: SOLO se actualizan los usuarios cuyo DNI la API reconoce como
válido (respuesta 200). Los DNIs inexistentes o incorrectos se omiten sin
tocar sus datos.

Uso:
    python actualizar_nombres_por_dni.py                 # aplica cambios
    python actualizar_nombres_por_dni.py --dry-run       # solo muestra
    python actualizar_nombres_por_dni.py --solo-pacientes

Es determinista: si se vuelve a ejecutar, el resultado es el mismo.
"""
import argparse
import os
import sys
import time

import requests
from dotenv import load_dotenv

from db import get_connection

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DECOLECTA_API_URL = os.getenv(
    "DECOLECTA_API_URL", "https://api.decolecta.com/v1/reniec/dni"
)
PAUSA = 0.35  # segundos entre consultas (evita el límite de la API)


def _token():
    return (os.getenv("DECOLECTA_TOKEN") or os.getenv("DNI_API_TOKEN") or "").strip()


def _normalizar(data):
    """Devuelve (nombres, apePaterno, apeMaterno) desde la respuesta."""
    if not isinstance(data, dict):
        return "", "", ""

    def pick(*claves):
        for clave in claves:
            valor = data.get(clave)
            if valor:
                return str(valor).strip()
        return ""

    nombres = pick("first_name", "nombres", "name", "given_name")
    ape_paterno = pick("first_last_name", "apellido_paterno", "paternal_surname")
    ape_materno = pick("second_last_name", "apellido_materno", "maternal_surname")

    if not (nombres and ape_paterno):
        completo = pick("full_name", "nombre_completo", "nombreCompleto")
        if completo:
            partes = completo.split()
            if len(partes) >= 3:
                ape_paterno = ape_paterno or partes[0]
                ape_materno = ape_materno or partes[1]
                nombres = nombres or " ".join(partes[2:])
            elif len(partes) == 2:
                ape_paterno = ape_paterno or partes[0]
                nombres = nombres or partes[1]

    return nombres, ape_paterno, ape_materno


def consultar_dni(dni):
    """Consulta un DNI. Devuelve (ok, nombres, apePaterno, apeMaterno, mensaje)."""
    token = _token()
    if not token:
        return False, "", "", "", "Falta DECOLECTA_TOKEN en el entorno."

    for intento in (1, 2):
        try:
            resp = requests.get(
                DECOLECTA_API_URL,
                params={"numero": dni},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=10,
            )
        except requests.RequestException as e:
            return False, "", "", "", f"error de conexión: {e}"

        if resp.status_code == 200:
            datos = resp.json()
            nombres, ape_p, ape_m = _normalizar(datos)
            if not nombres:
                return False, "", "", "", "sin datos"
            return True, nombres, ape_p, ape_m, "ok"
        if resp.status_code == 404:
            return False, "", "", "", "DNI no encontrado"
        if resp.status_code == 429 and intento == 1:
            time.sleep(2.0)
            continue
        if resp.status_code in (401, 403):
            return False, "", "", "", "token inválido o sin permisos"

        return False, "", "", "", f"HTTP {resp.status_code}"

    return False, "", "", "", "HTTP 429 (límite alcanzado)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No escribe en la BD.")
    parser.add_argument("--solo-pacientes", action="store_true",
                        help="Solo usuarios con rol 'paciente'.")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    filtro = "AND r.nombre = 'paciente'" if args.solo_pacientes else ""
    cur.execute(f"""
        SELECT u.id, COALESCE(r.nombre, '?') AS rol, u.numero_documento,
               u.nombre, u.apepaterno, u.apematerno
        FROM usuarios u
        LEFT JOIN roles r ON u.id_rol = r.id
        WHERE u.numero_documento IS NOT NULL
          AND u.numero_documento ~ '^[0-9]{{8}}$'
          {filtro}
        ORDER BY u.id
    """)
    usuarios = cur.fetchall()

    total = len(usuarios)
    print(f"Usuarios con DNI de 8 dígitos: {total}"
          f"{' (solo pacientes)' if args.solo_pacientes else ''}\n")

    actualizados = 0
    omitidos = 0

    for u in usuarios:
        dni = u["numero_documento"]
        ok, nombres, ape_p, ape_m, msg = consultar_dni(dni)
        time.sleep(PAUSA)

        if not ok:
            omitidos += 1
            print(f"  ⏭  id {u['id']:>3}  DNI {dni}  -> omitido ({msg})")
            continue

        # Conservar valor existente si la API no trae ese campo.
        nuevo_nombre = nombres or u["nombre"]
        nuevo_paterno = ape_p or u["apepaterno"]
        nuevo_materno = ape_m or u["apematerno"]

        iguales = (
            (nuevo_nombre or "") == (u["nombre"] or "")
            and (nuevo_paterno or "") == (u["apepaterno"] or "")
            and (nuevo_materno or "") == (u["apematerno"] or "")
        )
        if iguales:
            actualizados += 1
            print(f"  =  id {u['id']:>3}  DNI {dni}  -> ya coincide")
            continue

        print(f"  ✅ id {u['id']:>3}  DNI {dni}")
        print(f"        antes: {u['nombre']} | {u['apepaterno']} | {u['apematerno']}")
        print(f"        ahora: {nuevo_nombre} | {nuevo_paterno} | {nuevo_materno}")

        if not args.dry_run:
            cur.execute(
                """UPDATE usuarios
                   SET nombre = %s, apepaterno = %s, apematerno = %s
                   WHERE id = %s""",
                (nuevo_nombre, nuevo_paterno, nuevo_materno, u["id"]),
            )
        actualizados += 1

    if args.dry_run:
        conn.rollback()
        print(f"\n[dry-run] Se actualizarían {actualizados}, omitidos {omitidos}.")
    else:
        conn.commit()
        print(f"\n✅ Actualizados/confirmados {actualizados}, omitidos {omitidos}.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
