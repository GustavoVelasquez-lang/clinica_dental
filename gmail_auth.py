"""
Script de autenticacion para Gmail API.

Pasos:
1. Crea credenciales OAuth2 en https://console.cloud.google.com/apis/credentials
   - Tipo: "Aplicacion de escritorio"
   - Descarga el JSON y renombralo como "client_secret.json"
2. Ejecuta: python gmail_auth.py
3. Se abrira el navegador para autorizar
4. Se generara el archivo "gmail_token.json"
"""

import os
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

BASE_DIR = Path(__file__).parent
CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"
TOKEN_FILE = BASE_DIR / "gmail_token.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def generar_token():
    if not CLIENT_SECRET_FILE.exists():
        print(f"ERROR: No se encuentra {CLIENT_SECRET_FILE}")
        print("1. Ve a https://console.cloud.google.com/apis/credentials")
        print("2. Crea credenciales OAuth > 'Aplicacion de escritorio'")
        print("3. Descarga el JSON y guardalo como 'client_secret.json'")
        return False

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"Token generado correctamente: {TOKEN_FILE}")
    return True


if __name__ == "__main__":
    generar_token()
