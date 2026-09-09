import base64
import json
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from dotenv import dotenv_values
from db import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).parent
_ENV_PATH = _BASE_DIR / ".env"
_TOKEN_FILE = _BASE_DIR / "gmail_token.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _get_credentials() -> Credentials | None:
    if not _TOKEN_FILE.exists():
        logger.error(
            f"No se encuentra {_TOKEN_FILE}. "
            "Ejecuta primero: python gmail_auth.py"
        )
        return None

    with open(_TOKEN_FILE) as f:
        token_data = json.load(f)

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes", SCOPES),
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(_TOKEN_FILE, "w") as f:
            json.dump(
                {
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": creds.scopes,
                },
                f,
                indent=2,
            )
        logger.info("Token de Gmail actualizado automaticamente")

    return creds


def enviar_correo(destinatario: str, asunto: str, cuerpo_html: str) -> bool:
    creds = _get_credentials()
    if not creds:
        return False

    msg = MIMEMultipart("alternative")
    msg["To"] = destinatario
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        service = build("gmail", "v1", credentials=creds)
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info(f"Correo enviado a {destinatario}: {asunto}")
        return True
    except Exception as e:
        logger.error(f"Error al enviar correo a {destinatario}: {e}")
        return False


def enviar_recordatorio_cita(
    destinatario: str,
    nombre_paciente: str,
    especialidad: str,
    fecha: str,
    hora: str,
    dias_antes: int,
) -> bool:
    with open(_BASE_DIR / "templates" / "email_reminder.html", encoding="utf-8") as f:
        cuerpo = f.read()

    cuerpo = (
        cuerpo.replace("{{nombre}}", nombre_paciente)
        .replace("{{especialidad}}", especialidad)
        .replace("{{fecha}}", fecha)
        .replace("{{hora}}", hora)
    )

    dias_texto = f"{dias_antes} dia{'s' if dias_antes > 1 else ''} de anticipacion"
    asunto = f"Recordatorio de cita - Clinica Dental ({dias_texto})"
    return enviar_correo(destinatario, asunto, cuerpo)


def enviar_comprobante_admin(
    nombre_paciente: str,
    especialidad: str,
    fecha: str,
    hora: str,
    comprobante_path: str,
) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.correo
        FROM usuarios u
        JOIN roles r ON u.id_rol = r.id
        WHERE r.nombre = 'admin'
        LIMIT 1
    """)
    admin = cursor.fetchone()
    conn.close()

    if not admin:
        logger.error("No se encontro un administrador en la base de datos")
        return False

    admin_email = admin["correo"]

    msg = MIMEMultipart("mixed")
    msg["To"] = admin_email
    msg["Subject"] = f"Nuevo comprobante de pago - {nombre_paciente}"

    cuerpo_html = f"""
    <h2>Nuevo comprobante de pago</h2>
    <p><strong>Paciente:</strong> {nombre_paciente}</p>
    <p><strong>Especialidad:</strong> {especialidad}</p>
    <p><strong>Fecha:</strong> {fecha}</p>
    <p><strong>Hora:</strong> {hora}</p>
    <p>Revisa el comprobante adjunto para confirmar la cita.</p>
    """
    msg.attach(MIMEText(cuerpo_html, "html"))

    try:
        with open(comprobante_path, "rb") as f:
            adjunto = MIMEBase("application", "octet-stream")
            adjunto.set_payload(f.read())
        encoders.encode_base64(adjunto)
        filename = Path(comprobante_path).name
        adjunto.add_header(
            "Content-Disposition",
            f"attachment; filename={filename}",
        )
        msg.attach(adjunto)
    except Exception as e:
        logger.error(f"Error al adjuntar comprobante: {e}")

    creds = _get_credentials()
    if not creds:
        return False

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        service = build("gmail", "v1", credentials=creds)
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info(f"Comprobante enviado al admin {admin_email}")
        return True
    except Exception as e:
        logger.error(f"Error al enviar comprobante al admin: {e}")
        return False
