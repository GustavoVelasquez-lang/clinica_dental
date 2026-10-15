import base64
import json
import logging
import threading
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


def enviar_en_segundo_plano(func, *args, **kwargs):
    """Ejecuta el envío de un correo en un hilo de fondo.

    Así la respuesta al usuario (p. ej. al agendar) no se ralentiza mientras
    se autentica contra Gmail y se envía el mensaje.
    """
    hilo = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    hilo.start()
    return hilo



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


def enviar_confirmacion_cita(
    destinatario: str,
    nombre_paciente: str,
    especialidad: str,
    fecha: str,
    hora: str,
) -> bool:
    with open(_BASE_DIR / "templates" / "email_confirmacion.html", encoding="utf-8") as f:
        cuerpo = f.read()

    cuerpo = (
        cuerpo.replace("{{nombre}}", nombre_paciente)
        .replace("{{especialidad}}", especialidad)
        .replace("{{fecha}}", fecha)
        .replace("{{hora}}", hora)
    )

    asunto = "Cita registrada - Sele Dent Clinica Dental"
    return enviar_correo(destinatario, asunto, cuerpo)


def enviar_confirmacion_pago(
    destinatario: str,
    nombre_paciente: str,
    especialidad: str,
    fecha: str,
    hora: str,
    monto: float,
    transaccion_id: str = "",
) -> bool:
    """Confirma al paciente que su adelanto se pagó y la cita quedó reservada."""
    monto_txt = f"S/ {monto:.2f}"
    cuerpo_html = f"""
    <div style="font-family:'Segoe UI',Tahoma,sans-serif;max-width:620px;margin:auto;
                border:1px solid #e6e9ec;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#2f6fd0,#1f57b3);color:#fff;padding:22px">
        <h2 style="margin:0;font-size:19px">Pago confirmado</h2>
        <p style="margin:6px 0 0;font-size:13px;color:#dbe6f7;letter-spacing:.08em">
          CLINICA SELEDENT
        </p>
      </div>
      <div style="padding:24px;color:#333;line-height:1.6">
        <h3 style="color:#2f6fd0;margin-top:0">Hola, {nombre_paciente}!</h3>
        <p>Recibimos tu adelanto de <strong>{monto_txt}</strong> y tu cita quedo
           <strong>confirmada</strong>.</p>
        <div style="background:#f2f7fd;border-left:4px solid #2f6fd0;
                    padding:14px 16px;border-radius:0 8px 8px 0;margin:20px 0">
          <p style="margin:0 0 6px"><strong>Especialidad:</strong> {especialidad}</p>
          <p style="margin:0 0 6px"><strong>Fecha:</strong> {fecha}</p>
          <p style="margin:0"><strong>Hora:</strong> {hora}</p>
        </div>
        <p style="color:#6f7d8d;font-size:12.5px">
          Te esperamos en la sede. Si necesitas reprogramar, hazlo desde
          "Mis Citas" o escribenos por WhatsApp.
        </p>
      </div>
      <div style="background:#12283f;padding:16px;text-align:center;
                 font-size:13px;color:#9db7b2">
        <p style="margin:4px 0;color:#c9a84c;font-weight:600">Sele Dent - Clinica Dental</p>
        <p style="margin:4px 0">Este es un mensaje automatico, por favor no responder.</p>
      </div>
    </div>
    """
    asunto = f"Pago confirmado - {monto_txt} - Sele Dent"
    return enviar_correo(destinatario, asunto, cuerpo_html)


def enviar_notificacion_pago_admin(
    nombre_paciente: str,
    especialidad: str,
    fecha: str,
    hora: str,
    monto: float,
    transaccion_id: str = "",
) -> bool:
    """Avisa al administrador que se recibió un pago en línea."""
    destino = correo_notificacion()
    if not destino:
        logger.error("No hay correo configurado para notificar pagos en linea")
        return False

    monto_txt = f"S/ {monto:.2f}"
    cuerpo_html = f"""
    <div style="font-family:'Segoe UI',Tahoma,sans-serif;max-width:620px;margin:auto;
                border:1px solid #e6e9ec;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#1f57b3,#12283f);color:#fff;padding:22px">
        <h2 style="margin:0;font-size:19px">Nuevo pago en linea recibido</h2>
        <p style="margin:6px 0 0;font-size:13px;color:#dbe6f7">Pasarela Culqi</p>
      </div>
      <div style="padding:24px;color:#333;line-height:1.6">
        <p><strong>Paciente:</strong> {nombre_paciente}</p>
        <p><strong>Especialidad:</strong> {especialidad}</p>
        <p><strong>Fecha:</strong> {fecha}</p>
        <p><strong>Hora:</strong> {hora}</p>
        <p><strong>Monto:</strong> {monto_txt}</p>
        {f'<p><strong>Transaccion:</strong> {transaccion_id}</p>' if transaccion_id else ''}
      </div>
    </div>
    """
    return enviar_correo(destino, f"[Pago] {monto_txt} - {nombre_paciente}", cuerpo_html)


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


def _enviar_mime(msg) -> bool:
    """Envía un mensaje MIME ya construido vía Gmail API."""
    creds = _get_credentials()
    if not creds:
        return False

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        service = build("gmail", "v1", credentials=creds)
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info(f"Notificación enviada a {msg.get('To', '')}: {msg.get('Subject', '')}")
        return True
    except Exception as e:
        logger.error(f"Error al enviar notificación a {msg.get('To', '')}: {e}")
        return False


def enviar_notificacion_agendamiento_admin(
    *,
    nombre_paciente: str,
    telefono: str,
    correo: str,
    tratamiento: str,
    doctor: str,
    fecha: str,
    hora: str,
    monto_adelanto: float,
    con_comprobante: bool,
    comprobante_path: str | None = None,
) -> bool:
    """Notifica al administrador que un paciente agendó una cita.

    Con ``con_comprobante=False`` avisa que la cita quedó pendiente de pago;
    con ``con_comprobante=True`` avisa del nuevo pago adjuntando el voucher.
    """
    destino = correo_admin()
    if not destino:
        logger.error(
            "No hay correo de administrador configurado (ADMIN_EMAIL/CORREO_CLINICA)"
        )
        return False

    monto_txt = f"S/ {float(monto_adelanto or 0):.2f}"
    tratamiento_txt = tratamiento or "Sin tratamiento especificado"
    doctor_txt = doctor or "Asignación automática"

    if con_comprobante:
        asunto = (
            f"[NUEVO PAGO] Cita agendada por {nombre_paciente} - {tratamiento_txt}"
        )
        estado_txt = "Pendiente de Verificación de Pago"
        caja = f"""
        <div style="background:#e8f5e9;border-left:4px solid #43a047;padding:12px 16px;border-radius:6px;margin:16px 0;">
          <strong style="color:#2e7d32;">Nuevo pago registrado</strong>
          <p style="margin:6px 0 0;">Monto abonado (adelanto): <strong>{monto_txt}</strong></p>
          <p style="margin:6px 0 0;">Se ha adjuntado el comprobante. Revisa el panel de
          administración para validar la transacción y confirmar la cita.</p>
        </div>
        """
        fila_monto = (
            f"<p><strong>Monto abonado (adelanto):</strong> {monto_txt}</p>"
        )
    else:
        asunto = (
            f"[PENDIENTE DE PAGO] Cita agendada por {nombre_paciente} - Sin Adelanto"
        )
        estado_txt = "Pendiente de Pago"
        caja = f"""
        <div style="background:#fff8e1;border-left:4px solid #fb8c00;padding:12px 16px;border-radius:6px;margin:16px 0;">
          <strong style="color:#e65100;">⚠️ Cita sin adelanto</strong>
          <p style="margin:6px 0 0;">El paciente completó el agendamiento pero todavía
          <strong>no ha subido su comprobante de adelanto</strong>. Ponte en contacto
          para recordarle que debe realizar el abono de <strong>{monto_txt}</strong>
          para asegurar su cupo.</p>
        </div>
        """
        fila_monto = ""

    msg = MIMEMultipart("mixed")
    msg["To"] = destino
    msg["Subject"] = asunto

    cuerpo_html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;color:#263238;max-width:600px;margin:auto;">
      <div style="background:linear-gradient(135deg,#1565c0,#42a5f5);padding:20px;border-radius:10px 10px 0 0;color:#fff;">
        <h2 style="margin:0;">🦷 Nueva cita agendada</h2>
        <p style="margin:6px 0 0;opacity:.9;">Clínica Dental SELEDENT</p>
      </div>
      <div style="border:1px solid #e0e0e0;border-top:none;border-radius:0 0 10px 10px;padding:20px;">
        <p><strong>Paciente:</strong> {nombre_paciente}</p>
        <p><strong>Teléfono:</strong> {telefono or "No indicado"}</p>
        <p><strong>Correo:</strong> {correo or "No indicado"}</p>
        <p><strong>Tratamiento:</strong> {tratamiento_txt}</p>
        <p><strong>Doctor/Especialista:</strong> {doctor_txt}</p>
        <p><strong>Fecha:</strong> {fecha}</p>
        <p><strong>Hora:</strong> {hora}</p>
        {fila_monto}
        <p><strong>Estado:</strong> {estado_txt}</p>
        {caja}
      </div>
    </div>
    """
    msg.attach(MIMEText(cuerpo_html, "html"))

    if con_comprobante and comprobante_path:
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
            logger.error(f"Error al adjuntar comprobante al admin: {e}")

    return _enviar_mime(msg)


def enviar_alerta_comprobante_admin(
    *,
    nombre_paciente: str,
    telefono: str,
    correo: str,
    tratamiento: str,
    especialista: str,
    fecha: str,
    hora: str,
    monto_adelanto: float,
    panel_url: str = "",
    comprobante_path: str | None = None,
) -> bool:
    """Avisa al administrador que un paciente subió su comprobante de pago.

    El correo va SIEMPRE al administrador (ADMIN_EMAIL) y adjunta el voucher
    para que recepción valide el pago y confirme la cita.
    """
    destino = correo_admin()
    if not destino:
        logger.error(
            "No hay correo de administrador configurado (ADMIN_EMAIL/CORREO_CLINICA)"
        )
        return False

    monto_txt = f"S/ {float(monto_adelanto or 0):.2f}"
    tratamiento_txt = tratamiento or "Sin tratamiento especificado"
    especialista_txt = especialista or "Asignación automática"

    asunto = f"[COMPROBANTE SUBIDO - PENDIENTE DE VALIDACIÓN] Cita de {nombre_paciente}"

    enlace = ""
    if panel_url:
        enlace = f"""
        <p style="margin:18px 0 0;">
          <a href="{panel_url}"
             style="background:#1565c0;color:#fff;padding:11px 22px;border-radius:8px;
                    text-decoration:none;font-weight:600;font-size:14px;">
            Revisar y confirmar el pago
          </a>
        </p>
        <p style="margin:8px 0 0;font-size:12.5px;color:#78909c;">
          O entra al panel de administración: {panel_url}
        </p>
        """

    cuerpo_html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;color:#263238;max-width:600px;margin:auto;">
      <div style="background:linear-gradient(135deg,#1565c0,#42a5f5);padding:20px;border-radius:10px 10px 0 0;color:#fff;">
        <h2 style="margin:0;">🦷 Alerta de nuevo pago subido</h2>
        <p style="margin:6px 0 0;opacity:.9;">Pendiente de Verificación por recepción</p>
      </div>
      <div style="border:1px solid #e0e0e0;border-top:none;border-radius:0 0 10px 10px;padding:20px;">
        <div style="background:#fff8e1;border-left:4px solid #fb8c00;padding:12px 16px;border-radius:6px;margin:0 0 18px;">
          <strong style="color:#e65100;">Comprobante recibido</strong>
          <p style="margin:6px 0 0;">El paciente subió su comprobante de pago. Revisa el
          archivo adjunto y confirma el pago en el panel de administración.</p>
        </div>

        <h3 style="color:#1565c0;margin:0 0 8px;font-size:15px;">Datos del paciente</h3>
        <p style="margin:4px 0;"><strong>Nombre:</strong> {nombre_paciente}</p>
        <p style="margin:4px 0;"><strong>Teléfono:</strong> {telefono or "No indicado"}</p>
        <p style="margin:4px 0;"><strong>Correo:</strong> {correo or "No indicado"}</p>

        <h3 style="color:#1565c0;margin:18px 0 8px;font-size:15px;">Detalles de la cita</h3>
        <p style="margin:4px 0;"><strong>Tratamiento:</strong> {tratamiento_txt}</p>
        <p style="margin:4px 0;"><strong>Especialista:</strong> {especialista_txt}</p>
        <p style="margin:4px 0;"><strong>Fecha:</strong> {fecha}</p>
        <p style="margin:4px 0;"><strong>Hora:</strong> {hora}</p>

        <div style="background:#e8f5e9;border-left:4px solid #43a047;padding:12px 16px;border-radius:6px;margin:18px 0;">
          <strong style="color:#2e7d32;">Monto del adelanto abonado</strong>
          <p style="margin:6px 0 0;font-size:18px;"><strong>{monto_txt}</strong></p>
        </div>

        <p style="margin:0;">Revisa el comprobante adjunto y confirma el pago en el panel
        de administración.</p>
        {enlace}
      </div>
    </div>
    """

    msg = MIMEMultipart("mixed")
    msg["To"] = destino
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo_html, "html"))

    if comprobante_path:
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
            logger.error(f"Error al adjuntar comprobante al admin: {e}")

    return _enviar_mime(msg)


ASUNTOS_CONTACTO = (
    "Consulta general",
    "Agendamiento de citas",
    "Presupuesto/Tratamientos",
    "Reclamaciones",
)


def correo_notificacion() -> str:
    """Correo que recibe los mensajes del formulario de contacto.

    Prioridad: variable de entorno CORREO_CLINICA; si no esta, el correo del
    administrador registrado en la base de datos.
    """
    correo = (dotenv_values(_ENV_PATH).get("CORREO_CLINICA") or "").strip()
    if correo:
        return correo

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT correo
            FROM usuarios
            WHERE id_rol = (SELECT id FROM roles WHERE nombre = 'admin')
            LIMIT 1
        """)
        admin = cursor.fetchone()
        conn.close()
    except Exception as e:
        logger.error(f"No se pudo resolver el correo de la clinica: {e}")
        return ""

    return admin["correo"] if admin else ""


def correo_admin() -> str:
    """Correo del administrador para notificaciones internas.

    Prioridad: variable de entorno ADMIN_EMAIL; si no está, CORREO_CLINICA;
    y como último recurso, el correo del administrador en la base de datos.
    """
    config = dotenv_values(_ENV_PATH)
    correo = (config.get("ADMIN_EMAIL") or "").strip()
    if correo:
        return correo

    correo = (config.get("CORREO_CLINICA") or "").strip()
    if correo:
        return correo

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT correo FROM usuarios
            WHERE id_rol = (SELECT id FROM roles WHERE nombre = 'admin')
            LIMIT 1
        """)
        admin = cursor.fetchone()
        conn.close()
    except Exception as e:
        logger.error(f"No se pudo resolver el correo del administrador: {e}")
        return ""

    return admin["correo"] if admin else ""


def enviar_notificacion_contacto(
    nombre: str,
    email: str,
    telefono: str,
    asunto: str,
    mensaje: str,
    fecha_envio: str,
) -> bool:
    """Avisa al correo de la clinica que hay un mensaje nuevo sin responder."""
    destino = correo_notificacion()
    if not destino:
        logger.error("No hay correo configurado para notificar mensajes de contacto")
        return False

    cuerpo_html = f"""
    <div style="font-family:'Segoe UI',Tahoma,sans-serif;max-width:620px;margin:auto;
                border:1px solid #e6e9ec;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#2f6fd0,#1f57b3);color:#fff;padding:22px">
        <h2 style="margin:0;font-size:19px">Nuevo mensaje de contacto</h2>
        <p style="margin:6px 0 0;font-size:13px;color:#dbe6f7">
          Formulario web - Clinica Sele Dent
        </p>
      </div>
      <div style="padding:24px;color:#333;line-height:1.6">
        <p><strong>Nombre:</strong> {nombre}</p>
        <p><strong>Correo:</strong> {email}</p>
        <p><strong>Telefono:</strong> {telefono or 'No indicated'}</p>
        <p><strong>Asunto:</strong> {asunto}</p>
        <p><strong>Recibido:</strong> {fecha_envio}</p>
        <div style="background:#f2f7fd;border-left:4px solid #2f6fd0;
                    padding:14px 16px;border-radius:0 8px 8px 0;margin-top:18px">
          <p style="margin:0;white-space:pre-wrap">{mensaje}</p>
        </div>
        <p style="margin-top:22px">
          <a href="mailto:{email}"
             style="background:#2f6fd0;color:#fff;padding:10px 22px;border-radius:8px;
                    text-decoration:none;font-weight:600;font-size:14px">Responder al paciente</a>
        </p>
      </div>
    </div>
    """

    return enviar_correo(destino, f"[Contacto] {asunto} - {nombre}", cuerpo_html)


def enviar_confirmacion_contacto(destinatario: str, nombre: str, asunto: str) -> bool:
    """Confirma al paciente que su mensaje fue recibido."""
    cuerpo_html = f"""
    <div style="font-family:'Segoe UI',Tahoma,sans-serif;max-width:620px;margin:auto;
                border:1px solid #e6e9ec;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#2f6fd0,#1f57b3);color:#fff;padding:22px">
        <h2 style="margin:0;font-size:19px">Clinica Sele Dent</h2>
        <p style="margin:6px 0 0;font-size:13px;color:#dbe6f7;letter-spacing:.08em">
          CONFIRMACION DE MENSAJE
        </p>
      </div>
      <div style="padding:24px;color:#333;line-height:1.6">
        <h3 style="color:#2f6fd0;margin-top:0">Hola, {nombre}!</h3>
        <p>Hemos recibido tu mensaje y nos pondremos en contacto a la brevedad.</p>
        <div style="background:#f2fbf9;border-left:4px solid #c9a84c;
                    padding:14px 16px;border-radius:0 8px 8px 0;margin:20px 0">
          <p style="margin:0"><strong>Asunto registrado:</strong> {asunto}</p>
        </div>
        <p>Atendemos de <strong>lunes a sabado de 8:00 am a 8:00 pm</strong>.</p>
        <p>Si tu consulta es urgente, escribenos por WhatsApp al
           <strong>+51 964 123 456</strong>.</p>
        <p>Gracias por confiar en nosotros.</p>
      </div>
      <div style="background:#12283f;padding:16px;text-align:center;
                 font-size:13px;color:#9db7b2">
        <p style="margin:4px 0;color:#c9a84c;font-weight:600">Sele Dent - Clinica Dental</p>
        <p style="margin:4px 0">Este es un mensaje automatico, por favor no responder.</p>
      </div>
    </div>
    """

    return enviar_correo(destinatario, "Recibimos tu mensaje - Sele Dent", cuerpo_html)


def enviar_codigo_recuperacion(
    destinatario: str,
    nombre: str,
    codigo: str,
    minutos: int = 15,
) -> bool:
    """Envia el codigo de un solo uso para restablecer la contrasena."""
    cuerpo_html = f"""
    <div style="font-family:'Segoe UI',Tahoma,sans-serif;max-width:620px;margin:auto;
                border:1px solid #e6e9ec;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#2f6fd0,#1f57b3);color:#fff;padding:22px">
        <h2 style="margin:0;font-size:19px">Recuperar contrasena</h2>
        <p style="margin:6px 0 0;font-size:13px;color:#dbe6f7;letter-spacing:.08em">
          CLINICA SELEDENT
        </p>
      </div>
      <div style="padding:24px;color:#333;line-height:1.6">
        <h3 style="color:#2f6fd0;margin-top:0">Hola, {nombre}!</h3>
        <p>Recibimos una solicitud para restablecer la contrasena de tu cuenta.
           Usa el siguiente codigo de verificacion:</p>
        <div style="text-align:center;margin:22px 0">
          <span style="display:inline-block;font-family:monospace;font-size:34px;
                       font-weight:700;letter-spacing:.32em;color:#1f57b3;
                       background:#eaf2fd;border-radius:12px;padding:14px 26px 14px 32px">
            {codigo}
          </span>
        </div>
        <p style="margin-top:6px">Este codigo vence en <strong>{minutos} minutos</strong>
           y solo puede usarse una vez.</p>
        <p style="color:#6f7d8d;font-size:12.5px">
          Si no solicitaste este cambio, ignora este correo; tu contrasena seguira siendo la misma.
        </p>
      </div>
      <div style="background:#12283f;padding:16px;text-align:center;
                 font-size:13px;color:#9db7b2">
        <p style="margin:4px 0;color:#c9a84c;font-weight:600">Sele Dent - Clinica Dental</p>
        <p style="margin:4px 0">Este es un mensaje automatico, por favor no responder.</p>
      </div>
    </div>
    """

    return enviar_correo(destinatario, "Codigo para restablecer tu contrasena - Sele Dent", cuerpo_html)
