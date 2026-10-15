"""
Script para configurar Google Calendar API.

Pasos:
1. Ve a https://console.cloud.google.com/apis/credentials
2. Crea credenciales OAuth2 (tipo "Aplicacion de escritorio")
3. Habilita la Google Calendar API en https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
4. Descarga el JSON como "client_secret.json" (ya existente para Gmail)
5. Ejecuta: python google_calendar_auth.py
6. Se abrira el navegador para autorizar el acceso al calendario
7. Se guardara el token en "gmail_token.json" (se reutiliza)
"""

import json
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

BASE_DIR = Path(__file__).parent
CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"

SCOPES_GMAIL = ["https://www.googleapis.com/auth/gmail.send"]
SCOPES_CALENDAR = ["https://www.googleapis.com/auth/calendar"]
SCOPES_COMBINED = SCOPES_GMAIL + SCOPES_CALENDAR

TOKEN_FILE = BASE_DIR / "gmail_token.json"


def generar_token_calendario():
    if not CLIENT_SECRET_FILE.exists():
        print(f"ERROR: No se encuentra {CLIENT_SECRET_FILE}")
        print("1. Ve a https://console.cloud.google.com/apis/credentials")
        print("2. Crea credenciales OAuth > 'Aplicacion de escritorio'")
        print("3. Descarga el JSON y guardalo como 'client_secret.json'")
        return False

    existing_scopes = SCOPES_GMAIL
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            data = json.load(f)
            existing_scopes = data.get("scopes", SCOPES_GMAIL)

    if "https://www.googleapis.com/auth/calendar" in existing_scopes:
        print("Ya tienes autorizado el acceso a Google Calendar.")
        return True

    all_scopes = list(set(existing_scopes + SCOPES_CALENDAR))
    print(f"Solicitando permisos: {', '.join(all_scopes)}")

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), all_scopes)
    creds = flow.run_local_server(port=0)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or all_scopes),
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"Token actualizado con permisos de calendario: {TOKEN_FILE}")
    print("Ahora puedes configurar GOOGLE_CALENDAR_ID en tu archivo .env")
    return True


def verificar_calendario():
    """Verifica que la conexion con Google Calendar funcione."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        if not TOKEN_FILE.exists():
            print("No se encuentra gmail_token.json. Ejecuta primero: python gmail_auth.py")
            return False

        with open(TOKEN_FILE) as f:
            data = json.load(f)

        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=data.get("scopes", []),
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        if "https://www.googleapis.com/auth/calendar" not in (creds.scopes or []):
            print("El token no tiene permisos de calendario.")
            print("Ejecuta: python google_calendar_auth.py")
            return False

        service = build("calendar", "v3", credentials=creds)
        calendar_list = service.calendarList().list().execute()

        print("\nCalendarios disponibles:")
        for cal in calendar_list.get("items", []):
            marker = " *" if cal.get("primary") else ""
            print(f"  - {cal['id']}: {cal.get('summary', 'Sin nombre')}{marker}")

        print(f"\nConfigura GOOGLE_CALENDAR_ID en .env (usa 'primary' para el calendario principal)")
        return True

    except Exception as e:
        print(f"Error al verificar Google Calendar: {e}")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        verificar_calendario()
    else:
        generar_token_calendario()
