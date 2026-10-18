import json
import logging
import os
import random
import re
from math import ceil

import psycopg2
from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import quote

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from authlib.common.security import generate_token
from authlib.integrations.flask_client import OAuth
from db import db_connection, get_connection
from dotenv import dotenv_values, load_dotenv, set_key
from email_utils import (enviar_alerta_comprobante_admin,
                         enviar_codigo_recuperacion,
                         enviar_confirmacion_cita,
                         enviar_confirmacion_contacto,
                         enviar_confirmacion_pago,
                         enviar_en_segundo_plano,
                         enviar_notificacion_agendamiento_admin,
                         enviar_notificacion_contacto,
                         enviar_notificacion_pago_admin)
from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from io import BytesIO
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "clave_secreta_segura")
bcrypt = Bcrypt(app)


@app.after_request
def add_header(response):
    """Cabeceras anti-caché para que el botón "atrás" no muestre páginas
    protegidas expiradas desde la caché del navegador. Se excluyen los
    archivos estáticos para no forzar su re-descarga en cada visita."""
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# --- Pasarela de pago Culqi (tarjeta + Yape) ------------------------------
CULQI_PUBLIC_KEY = os.getenv("CULQI_PUBLIC_KEY", "")
CULQI_SECRET_KEY = os.getenv("CULQI_SECRET_KEY", "")
CULQI_API_URL = os.getenv("CULQI_API_URL", "https://api.culqi.com/v2")
CULQI_MONEDA = os.getenv("CULQI_MONEDA", "PEN")
# URL pública del sitio (para el webhook y retornos de pago).
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000").rstrip("/")

# --- Consulta de DNI (RENIEC vía Decolecta) -------------------------------
DECOLECTA_API_URL = os.getenv(
    "DECOLECTA_API_URL", "https://api.decolecta.com/v1/reniec/dni"
)

# Horas de atención disponibles para agendar/reprogramar citas.
HORAS_SISTEMA = ["09:00:00", "10:00:00", "11:00:00", "12:00:00", "15:00:00", "16:00:00"]
SEDE_PREDETERMINADA = "Sede Principal - El Tambo, Huancayo"

# Urgencias: se atienden el mismo día (hoy) con la especialidad de emergencias.
URGENCIA_TIPO_KEY = "urgencia"
URGENCIA_ESPECIALIDAD_ID = 4
PRIORIDAD_PRIORITARIA = "Atención Prioritaria"
PRIORIDAD_NORMAL = "Normal"

DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "setiembre", "octubre", "noviembre", "diciembre"]

# Tipos de atención disponibles al agendar, orientados a síntomas/objetivos.
# `esp_match` = palabras clave para resolver la especialidad fija; None => el
# paciente elige la especialidad en el formulario.
TIPOS_ATENCION = [
    {
        "key": "general",
        "label": "Evaluación General / Primera Consulta",
        "descripcion": "Ideal si quieres un chequeo completo, diagnóstico o no sabes qué especialidad necesitas.",
        "recomendada": True,
        "icono": "fa-solid fa-stethoscope",
        "esp_match": ("general",),
    },
    {
        "key": "tratamiento",
        "label": "Evaluación para Tratamiento Específico",
        "descripcion": "Selecciona esta opción si deseas valoración para un tratamiento particular (brackets, implantes, estética).",
        "recomendada": False,
        "icono": "fa-solid fa-tooth",
        "esp_match": None,
    },
    {
        "key": "urgencia",
        "label": "Atención de Urgencia / Dolor Agudo",
        "descripcion": "Para dolor de muela, inflamación o emergencias inmediatas.",
        "recomendada": False,
        "icono": "fa-solid fa-truck-medical",
        "esp_match": ("cirug",),
    },
]


def _id_especialidad_coincidente(especialidades, palabras):
    """Devuelve el id de la especialidad cuyo nombre contiene todas las palabras."""
    if not palabras:
        return None
    for esp in especialidades:
        nombre = (esp["nombre"] or "").lower()
        if all(p in nombre for p in palabras):
            return esp["id"]
    return None


def _resolver_adelanto(cursor, especialidad_id, tratamiento_id=None):
    """Monto de adelanto (float) para una cita.

    Prioriza el adelanto del tratamiento; si no está definido, usa el de la
    especialidad; si tampoco, 0.
    """
    if tratamiento_id:
        cursor.execute(
            "SELECT adelanto FROM tratamientos WHERE id_tratamiento = %s",
            (tratamiento_id,),
        )
        fila = cursor.fetchone()
        if fila and fila["adelanto"] is not None:
            return float(fila["adelanto"])
    if especialidad_id:
        cursor.execute(
            "SELECT adelanto FROM especialidades WHERE id = %s",
            (especialidad_id,),
        )
        fila = cursor.fetchone()
        if fila and fila["adelanto"] is not None:
            return float(fila["adelanto"])
    return 0.0


def _adelanto_efectivo(cursor, cita):
    """Adelanto efectivo de una cita ya creada (float).

    Orden estricto de resolución:
      1) citas.adelanto si es > 0
      2) tratamientos.adelanto (si la cita tiene un tratamiento asociado)
      3) especialidades.adelanto de la especialidad de la cita
      4) 0.0 => la cita no requiere adelanto
    """
    monto = float(cita.get("adelanto") or 0)
    if monto > 0:
        return monto

    # Tratamiento asociado a la cita (tabla puente cita_tratamiento).
    cursor.execute(
        """
        SELECT t.adelanto
        FROM cita_tratamiento ct
        JOIN tratamientos t ON t.id_tratamiento = ct.id_tratamiento
        WHERE ct.id_cita = %s AND t.adelanto > 0
        ORDER BY ct.id
        LIMIT 1
        """,
        (cita["id"],),
    )
    fila = cursor.fetchone()
    if fila and fila["adelanto"] is not None:
        return float(fila["adelanto"])

    # Especialidad de la cita.
    if cita.get("especialidad_id"):
        cursor.execute(
            "SELECT adelanto FROM especialidades WHERE id = %s",
            (cita["especialidad_id"],),
        )
        fila = cursor.fetchone()
        if fila and fila["adelanto"] is not None:
            adelanto_esp = float(fila["adelanto"])
            if adelanto_esp > 0:
                return adelanto_esp

    return 0.0


def _sincronizar_adelanto_cita(cursor, cita):
    """Recalcula el adelanto de la cita y lo persiste si cambió.

    Sirve para citas creadas cuando la especialidad/tratamiento aún no
    tenía adelanto definido: al consultar la pantalla de pago se vuelve
    a resolver y se actualiza `citas.adelanto`.

    Devuelve (monto, actualizado).
    """
    monto = _adelanto_efectivo(cursor, cita)
    actualizado = False
    if monto != float(cita.get("adelanto") or 0):
        cursor.execute(
            "UPDATE citas SET adelanto = %s WHERE id = %s",
            (monto, cita["id"]),
        )
        cita["adelanto"] = monto
        actualizado = True
    return monto, actualizado


def _monto_form(valor):
    """Convierte un monto de formulario a float >= 0 (None si vacío o inválido)."""
    valor = (valor or "").strip().replace(",", ".")
    if not valor:
        return None
    try:
        monto = float(valor)
    except ValueError:
        return None
    return monto if monto >= 0 else None


def _datos_notificacion_admin(cursor, cita_id):
    """Datos (paciente, tratamiento, doctor, fecha, hora, adelanto) de una cita.

    Se usa para las notificaciones internas al administrador; devuelve None si
    la cita no existe.
    """
    cursor.execute(
        """
        SELECT u.nombre, u.apePaterno, u.apeMaterno, u.telefono, u.correo,
               c.fecha, c.hora, c.adelanto, c.comprobante, c.odontologo_id,
               e.nombre AS especialidad,
               t.nombre AS tratamiento,
               d.nombre AS doc_nombre, d.apePaterno AS doc_apepaterno,
               d.apeMaterno AS doc_apematerno
        FROM citas c
        JOIN usuarios u ON u.id = c.paciente_id
        JOIN especialidades e ON e.id = c.especialidad_id
        LEFT JOIN usuarios d ON d.id = c.odontologo_id
        LEFT JOIN cita_tratamiento ct ON ct.id_cita = c.id
        LEFT JOIN tratamientos t ON t.id_tratamiento = ct.id_tratamiento
        WHERE c.id = %s
        ORDER BY ct.id
        LIMIT 1
        """,
        (cita_id,),
    )
    fila = cursor.fetchone()
    if not fila:
        return None

    nombre_paciente = " ".join(
        p for p in (fila["nombre"], fila["apepaterno"], fila["apematerno"]) if p
    ).strip()

    if fila["odontologo_id"]:
        doctor = " ".join(
            p
            for p in (
                fila["doc_nombre"],
                fila["doc_apepaterno"],
                fila["doc_apematerno"],
            )
            if p
        ).strip()
    else:
        doctor = "Asignación automática"

    return {
        "nombre_paciente": nombre_paciente,
        "telefono": fila["telefono"],
        "correo": fila["correo"],
        "tratamiento": fila["tratamiento"] or fila["especialidad"],
        "doctor": doctor,
        "fecha": str(fila["fecha"]),
        "hora": str(fila["hora"])[:5],
        "monto_adelanto": float(fila["adelanto"] or 0),
        "con_comprobante": bool(fila["comprobante"]),
    }


@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if os.environ.get("FLASK_DEBUG", "0") == "0":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _log_auditoria(accion, usuario_id=None, detalle=None):
    """Registra una accion en la tabla auditoria (no rompe si falla)."""
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO auditoria (usuario_id, accion, detalle, ip, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (usuario_id or session.get("usuario_id"), accion, detalle, request.remote_addr))
            conn.commit()
    except Exception as e:
        logger.error(f"Error en auditoria: {e}")


@app.context_processor
def inject_admin_context():
    """Variables globales disponibles en todas las vistas (sidebar admin)."""
    if session.get("rol") != "admin":
        return {}
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM citas WHERE estado = 'pendiente'")
        pendientes = cur.fetchone()["n"]
        conn.close()
        return {"citas_pendientes": pendientes}
    except Exception:
        return {"citas_pendientes": 0}
                                 
                            
                                 
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login", next=_url_actual()))
        return f(*args, **kwargs)
    return decorated_function

# Roles considerados "doctor" para el flujo de agendamiento médico.
# En la BD los odontólogos tienen rol 'odontologo' o 'dentista'; se incluye
# 'doctor' por si se crea ese rol a futuro.
ROLES_DOCTOR = {"doctor", "odontologo", "dentista"}


def _rol_actual():
    """Rol del usuario autenticado (soporta la clave 'rol' y 'usuario_rol')."""
    return session.get("rol") or session.get("usuario_rol")


def _es_doctor():
    """True si el usuario autenticado tiene un rol de doctor/odontólogo."""
    return _rol_actual() in ROLES_DOCTOR


def _redirigir_roles_no_paciente():
    """Evita que admins y doctores usen el flujo de agendamiento del paciente.

    Si el usuario autenticado es admin/administrador o doctor, devuelve la
    redirección (con flash) hacia su panel correspondiente. Si es paciente (o
    invitado, que ya habría sido llevado al login por @login_required),
    devuelve None para permitir el acceso.
    """
    rol = (session.get("rol") or "").lower()
    if rol in ("admin", "administrador"):
        flash("Para gestionar o agendar citas administrativas, utiliza el panel de control.", "warning")
        return redirect(url_for("admin_citas"))
    if _es_doctor():
        flash("Como doctor, agenda y gestiona tus citas desde tu panel.", "warning")
        return redirect(url_for("doctor_dashboard"))
    return None


@app.context_processor
def inject_panel_context():
    """Variables disponibles en el sidebar/topbar del panel de usuario."""
    if not session.get("usuario_id"):
        return {}
    return {
        "es_doctor": _es_doctor(),
        "nombre_sesion": session.get("nombre") or "Usuario",
    }


def doctor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login", next=_url_actual()))
        if _rol_actual() not in ROLES_DOCTOR:
            flash("❌ Acceso exclusivo para doctores", "danger")
            return redirect(url_for("mis_citas"))
        return f(*args, **kwargs)
    return decorated_function


@app.route("/agendar", methods=["GET", "POST"])
@login_required
def agendar():

    # Admins y doctores no usan el flujo de agendamiento del paciente.
    redirigido = _redirigir_roles_no_paciente()
    if redirigido:
        return redirigido

    if not _perfil_esta_completo(session["usuario_id"]):
        flash("Completa tu perfil (DNI y WhatsApp) para poder agendar tu cita.", "warning")
        return redirect(url_for("completar_perfil", next=url_for("agendar")))

    conn = get_connection()
    cursor = conn.cursor()

                            
    cursor.execute("SELECT id, nombre FROM especialidades")
    especialidades = cursor.fetchall()

    if request.method == "POST":

        fecha_str = request.form.get("fecha")
        especialidad_id = request.form.get("especialidad")
        hora = request.form.get("hora")
        mensaje = (request.form.get("mensaje") or "").strip()
        tipo_key = (request.form.get("tipo") or "").strip()
        tratamiento_id = (request.form.get("tratamiento") or "").strip() or None
        odontologo_id = (
            request.form.get("odontologo_id")
            or request.form.get("id_doctor")
            or ""
        ).strip() or None
        if odontologo_id and not odontologo_id.isdigit():
            odontologo_id = None
        tipo_label = next(
            (t["label"] for t in TIPOS_ATENCION if t["key"] == tipo_key),
            None,
        )
        es_urgencia = tipo_key == URGENCIA_TIPO_KEY

        # En urgencias se fuerza la especialidad de emergencias (Cirugía Oral).
        if es_urgencia:
            especialidad_id = (
                _id_especialidad_coincidente(especialidades, ("cirug",))
                or especialidad_id
                or URGENCIA_ESPECIALIDAD_ID
            )

                               
        if not fecha_str:
            flash("❌ Debes seleccionar una fecha", "danger")
            return redirect(url_for("agendar"))

        if not especialidad_id:
            flash("❌ Debes seleccionar una especialidad", "danger")
            return redirect(url_for("agendar"))

        if not hora:
            flash("❌ Debes seleccionar una hora", "danger")
            return redirect(url_for("agendar"))

                           
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            flash("❌ Fecha inválida", "danger")
            return redirect(url_for("agendar"))

        # Las urgencias pueden ser el mismo día; el resto, desde mañana.
        hoy = date.today()
        fecha_minima = hoy if es_urgencia else hoy + timedelta(days=1)
        if fecha < fecha_minima:
            if es_urgencia:
                flash("❌ La fecha de urgencia no puede ser anterior a hoy", "danger")
            else:
                flash("❌ Solo puedes agendar desde mañana", "danger")
            return redirect(url_for("agendar"))
        if session["rol"] != "paciente":
            flash("❌ Solo pacientes pueden agendar citas", "danger")
            return redirect(url_for("inicio"))

                                                       
        cursor.execute("""
            SELECT id FROM citas
            WHERE especialidad_id = %s AND fecha = %s AND hora = %s
        """, (especialidad_id, fecha, hora))

        ocupado = cursor.fetchone()

        if ocupado:
            flash("❌ Esa hora ya está ocupada", "danger")
            return redirect(url_for("agendar"))

        # Verificar que el odontólogo elegido esté habilitado para la especialidad.
        if odontologo_id:
            cursor.execute("""
                SELECT 1 FROM odontologo_especialidad
                WHERE odontologo_id = %s AND especialidad_id = %s
                  AND COALESCE(estado, 'activo') = 'activo'
            """, (odontologo_id, especialidad_id))
            if not cursor.fetchone():
                odontologo_id = None

                         
        adelanto = _resolver_adelanto(cursor, especialidad_id, tratamiento_id)

        try:
            cursor.execute("""
                INSERT INTO citas 
                (paciente_id, odontologo_id, especialidad_id, fecha, hora, estado, estado_pago,
                 tipo_atencion, sede, prioridad, observaciones, adelanto)
                VALUES (%s, %s, %s, %s, %s, 'pendiente', 'pendiente', %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                session["usuario_id"],
                int(odontologo_id) if odontologo_id else None,
                especialidad_id,
                fecha,
                hora,
                tipo_label,
                SEDE_PREDETERMINADA,
                PRIORIDAD_PRIORITARIA if es_urgencia else PRIORIDAD_NORMAL,
                mensaje or None,
                adelanto,
            ))
            cita_id = cursor.fetchone()["id"]
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            conn.close()
            flash("❌ Ese especialista ya tiene una cita a esa hora. Elige otro horario.", "danger")
            return redirect(url_for("agendar"))

        # Vincular el tratamiento elegido a la cita (para resolver el
        # adelanto por tratamiento en consultas posteriores).
        if tratamiento_id and str(tratamiento_id).isdigit():
            cursor.execute(
                """
                INSERT INTO cita_tratamiento (id_cita, id_tratamiento, precio_aplicado)
                VALUES (
                    %s, %s,
                    (SELECT precio_base FROM tratamientos WHERE id_tratamiento = %s)
                )
                """,
                (cita_id, int(tratamiento_id), int(tratamiento_id)),
            )

        conn.commit()
        conn.close()
        _log_auditoria("agendar_cita", detalle=f"cita #{cita_id}")

                                                            
        # Notificar al administrador del agendamiento (en segundo plano).
        try:
            conn = get_connection()
            cursor = conn.cursor()
            datos = _datos_notificacion_admin(cursor, cita_id)
            conn.close()

            if datos:
                enviar_en_segundo_plano(
                    enviar_notificacion_agendamiento_admin,
                    nombre_paciente=datos["nombre_paciente"],
                    telefono=datos["telefono"],
                    correo=datos["correo"],
                    tratamiento=datos["tratamiento"],
                    doctor=datos["doctor"],
                    fecha=datos["fecha"],
                    hora=datos["hora"],
                    monto_adelanto=datos["monto_adelanto"],
                    con_comprobante=datos["con_comprobante"],
                )
        except Exception as e:
            logger.error(f"Error al notificar la cita {cita_id} al administrador: {e}")

        return redirect(url_for("pago", cita_id=cita_id))

    # ---------- GET: parámetros de la URL ----------
    especialidad_param = (request.args.get("especialidad") or "").strip()
    tratamiento_param = (
        request.args.get("tratamiento_id")
        or request.args.get("tratamiento")
        or ""
    ).strip()
    tipo_param = (request.args.get("tipo") or "").strip().lower()
    tipo_seleccionado = ""

    # Si viene un tratamiento (p. ej. desde el catálogo público), resolvemos
    # automáticamente su especialidad y preseleccionamos el tipo "tratamiento".
    if tratamiento_param.isdigit():
        cursor.execute(
            "SELECT id_especialidad FROM tratamientos WHERE id_tratamiento = %s",
            (int(tratamiento_param),),
        )
        fila_trat = cursor.fetchone()
        if fila_trat:
            especialidad_param = str(fila_trat["id_especialidad"])
            tipo_seleccionado = "tratamiento"
        else:
            tratamiento_param = ""
    conn.close()

    # Acceso directo a la vista de evaluación: /agendar?tipo=evaluacion
    if tipo_param == "evaluacion":
        return redirect(url_for(
            "agendar_evaluacion",
            especialidad=especialidad_param,
            tratamiento=tratamiento_param,
        ))

    tipos_render = []
    for t in TIPOS_ATENCION:
        tipo = dict(t)
        tipo["esp_id"] = _id_especialidad_coincidente(especialidades, t.get("esp_match"))
        tipos_render.append(tipo)

    return render_template(
        "agendar_cita.html",
        especialidades=especialidades,
        especialidad_seleccionada=especialidad_param,
        tratamiento_seleccionado=tratamiento_param,
        tipo_seleccionado=tipo_seleccionado,
        tipos_atencion=tipos_render,
    )


def _buscar_especialidad(cursor, valor):
    """Resuelve (id, nombre) de una especialidad por id numérico o por nombre."""
    valor = (valor or "").strip()
    if not valor:
        return None, None
    if valor.isdigit():
        cursor.execute("SELECT id, nombre FROM especialidades WHERE id = %s", (int(valor),))
    else:
        cursor.execute(
            "SELECT id, nombre FROM especialidades WHERE LOWER(nombre) = LOWER(%s)",
            (valor,),
        )
    fila = cursor.fetchone()
    if fila:
        return fila["id"], fila["nombre"]
    return None, None


@app.route("/agendar/evaluacion", methods=["GET", "POST"])
@login_required
def agendar_evaluacion():
    """Vista de reserva de evaluación especializada."""
    # Admins y doctores no usan el flujo de agendamiento del paciente.
    redirigido = _redirigir_roles_no_paciente()
    if redirigido:
        return redirigido

    if not _perfil_esta_completo(session["usuario_id"]):
        flash("Completa tu perfil (DNI y WhatsApp) para poder agendar tu evaluación.", "warning")
        return redirect(url_for("completar_perfil", next=url_for("agendar_evaluacion")))

    conn = get_connection()
    cursor = conn.cursor()

    especialidad_param = (request.values.get("especialidad") or "").strip()
    tratamiento_param = (request.values.get("tratamiento") or "").strip()

    cursor.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
    especialidades = cursor.fetchall()

    esp_id, esp_nombre = _buscar_especialidad(cursor, especialidad_param)

    tratamientos = []
    if esp_id:
        cursor.execute(
            """
            SELECT id_tratamiento AS id, nombre
            FROM tratamientos
            WHERE id_especialidad = %s AND COALESCE(activo, TRUE) = TRUE
            ORDER BY nombre
            """,
            (esp_id,),
        )
        tratamientos = cursor.fetchall()

    if request.method == "POST":
        sede = (request.form.get("sede") or "").strip()
        nombres = (request.form.get("nombres") or "").strip()
        dni = (request.form.get("dni") or "").strip()
        whatsapp = (request.form.get("whatsapp") or "").strip()
        correo = (request.form.get("correo") or "").strip()
        fecha = (request.form.get("fecha") or "").strip()
        turno = (request.form.get("turno") or "").strip()
        tratamiento_form = (request.form.get("tratamiento") or "").strip()

        if not (esp_nombre and nombres and whatsapp and fecha and turno):
            flash("⚠️ Completa los campos obligatorios para confirmar tu evaluación.", "warning")
            conn.close()
            return redirect(url_for(
                "agendar_evaluacion",
                especialidad=especialidad_param,
                tratamiento=tratamiento_param,
            ))

        session["eval_resumen"] = {
            "especialidad": esp_nombre,
            "tratamiento": tratamiento_form or tratamiento_param or esp_nombre,
            "sede": sede or "Sede Principal - El Tambo, Huancayo",
            "nombres": nombres,
            "dni": dni,
            "whatsapp": whatsapp,
            "correo": correo,
            "fecha": fecha,
            "turno": turno,
        }
        conn.close()
        return redirect(url_for("agendar_evaluacion_confirmacion"))

    conn.close()

    especialidad_sel = {"id": esp_id, "nombre": esp_nombre} if esp_id else None
    return render_template(
        "agendar_evaluacion.html",
        especialidades=especialidades,
        especialidad_sel=especialidad_sel,
        tratamiento_sel=tratamiento_param,
        tratamientos=tratamientos,
    )


@app.route("/agendar/evaluacion/confirmacion")
@login_required
def agendar_evaluacion_confirmacion():
    """Pantalla de resumen/confirmación de la evaluación reservada."""
    resumen = session.pop("eval_resumen", None)
    if not resumen:
        return redirect(url_for("agendar_evaluacion"))

    config = dotenv_values()
    wa_numero = config.get("WHATSAPP_NUMERO", "51956536766")
    mensaje = (
        f"Hola Clínica Sele Dent, deseo confirmar mi evaluación de "
        f"{resumen['especialidad']} para el {resumen['fecha']} ({resumen['turno']}). "
        f"Mi nombre es {resumen['nombres']}."
    )
    wa_link = f"https://wa.me/{wa_numero}?text={quote(mensaje)}"

    return render_template(
        "agendar_evaluacion_confirmacion.html",
        resumen=resumen,
        wa_link=wa_link,
    )


def _formatear_numero_yape(numero):
    """Agrupa un número de Yape en bloques de 3 dígitos.

    Ej: '946536766' -> '946 536 766'.
    """
    digitos = re.sub(r"\D", "", str(numero or ""))
    return " ".join(digitos[i:i + 3] for i in range(0, len(digitos), 3))


@app.route("/pago/<int:cita_id>", methods=["GET"])
@login_required
def pago(cita_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, c.especialidad_id, c.fecha, c.hora, c.estado, c.comprobante, c.tipo_atencion,
               c.adelanto, c.estado_pago, c.nro_operacion, c.voucher_url, c.metodo_pago,
               e.nombre AS especialidad
        FROM citas c
        JOIN especialidades e ON c.especialidad_id = e.id
        WHERE c.id = %s AND c.paciente_id = %s
    """, (cita_id, session["usuario_id"]))

    cita = cursor.fetchone()

    if not cita:
        conn.close()
        flash("Cita no encontrada", "danger")
        return redirect(url_for("mis_citas"))

    # Recalcular el adelanto: la cita pudo crearse antes de que la
    # especialidad (o tratamiento) tuviera un adelanto definido.
    monto_adelanto, actualizado = _sincronizar_adelanto_cita(cursor, cita)
    if actualizado:
        conn.commit()

    config = dotenv_values()
    yape_numero = config.get("YAPE_NUMERO", "946536766")
    yape_nombre = config.get("YAPE_NOMBRE", "Clinica Sele Dent")
    yape_qr = config.get("YAPE_QR", "static/img/QR.yape.jpeg")

    conn.close()
    if yape_qr.startswith("http"):
        yape_qr_url = yape_qr
    else:
        qr_filename = yape_qr.replace("static/", "")
        yape_qr_url = url_for("static", filename=qr_filename)
    return render_template(
        "pago.html",
        cita=cita,
        yape_numero=yape_numero,
        yape_numero_fmt=_formatear_numero_yape(yape_numero),
        yape_nombre=yape_nombre,
        yape_qr=yape_qr_url,
        culqi_public_key=CULQI_PUBLIC_KEY,
        culqi_habilitado=bool(CULQI_PUBLIC_KEY and CULQI_SECRET_KEY),
        monto_adelanto=float(monto_adelanto or 0),
        mostrar_modal_confirmacion=(request.args.get("enviado") == "1"),
    )


EXTENSIONES_VOUCHER = {".jpg", ".jpeg", ".png"}


def _guardar_voucher(cita_id, archivo):
    """Lee y guarda el voucher de Yape.

    Devuelve (ruta_relativa, datos, mime, error). `datos` son los bytes del
    archivo (para persistirlos también en la base de datos) y `mime` su tipo.
    La ruta incluye el prefijo 'static/' y se guarda además en disco como
    respaldo (y para adjuntarlo al correo de aviso al administrador).
    """
    ext = os.path.splitext(archivo.filename or "")[1].lower()
    if ext not in EXTENSIONES_VOUCHER:
        return None, None, None, "Formato no permitido. Sube una imagen JPG o PNG."

    datos = archivo.read()
    if not datos:
        return None, None, None, "El archivo del comprobante está vacío."

    mime = "image/png" if ext == ".png" else "image/jpeg"
    nombre = secure_filename(
        f"voucher_cita_{cita_id}_{datetime.now():%Y%m%d%H%M%S}{ext}"
    )
    upload_dir = os.path.join(app.root_path, "static", "uploads", "vouchers")
    try:
        os.makedirs(upload_dir, exist_ok=True)
        with open(os.path.join(upload_dir, nombre), "wb") as fh:
            fh.write(datos)
    except OSError as e:
        # El disco puede ser efímero (Render); lo importante es la BD.
        logger.warning(f"No se pudo guardar el voucher en disco: {e}")
    return f"static/uploads/vouchers/{nombre}", datos, mime, None


@app.route("/pago/<int:cita_id>/manual", methods=["POST"])
@login_required
def pago_manual(cita_id):
    """Registra el pago por Yape directo (voucher + N° de operación).

    Deja la cita en 'pendiente_verificacion' a la espera de que el
    administrador valide el comprobante y confirme el pago.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, c.especialidad_id, c.fecha, c.hora, c.estado,
               c.adelanto, c.estado_pago, c.paciente_id,
               e.nombre AS especialidad
        FROM citas c
        JOIN especialidades e ON c.especialidad_id = e.id
        WHERE c.id = %s AND c.paciente_id = %s
    """, (cita_id, session["usuario_id"]))
    cita = cursor.fetchone()

    if not cita:
        conn.close()
        flash("❌ Cita no encontrada", "danger")
        return redirect(url_for("mis_citas"))

    # Recalcular el adelanto (pudo cambiar desde la reserva).
    monto, actualizado = _sincronizar_adelanto_cita(cursor, cita)
    if actualizado:
        conn.commit()

    nro_operacion = (request.form.get("nro_operacion") or "").strip()
    if not nro_operacion.isdigit() or not (4 <= len(nro_operacion) <= 20):
        conn.close()
        flash("❌ Ingresa un número de operación válido (solo dígitos).", "danger")
        return redirect(url_for("pago", cita_id=cita_id))

    archivo = request.files.get("voucher")
    if not archivo or archivo.filename == "":
        conn.close()
        flash("❌ Debes adjuntar el comprobante de Yape (JPG o PNG).", "danger")
        return redirect(url_for("pago", cita_id=cita_id))

    ruta_rel, datos, mime, error = _guardar_voucher(cita_id, archivo)
    if error:
        conn.close()
        flash(f"❌ {error}", "danger")
        return redirect(url_for("pago", cita_id=cita_id))

    cursor.execute("""
        UPDATE citas
        SET metodo_pago = 'yape_manual',
            nro_operacion = %s,
            voucher_url = %s,
            comprobante = %s,
            voucher_data = %s,
            voucher_mime = %s,
            estado_pago = 'pendiente_verificacion',
            estado = 'pendiente'
        WHERE id = %s
    """, (nro_operacion, ruta_rel, ruta_rel,
          psycopg2.Binary(datos), mime, cita_id))

    # Registrar la ejecución y el comprobante en el tratamiento de la cita.
    cursor.execute("""
        UPDATE cita_tratamiento
        SET fecha_ejecucion = now(),
            comprobante_pago = %s
        WHERE id_cita = %s
    """, (ruta_rel, cita_id))
    conn.commit()
    _log_auditoria("subir_comprobante", detalle=f"cita #{cita_id}")

    # Notificar al administrador del nuevo pago (en segundo plano, con voucher).
    try:
        datos = _datos_notificacion_admin(cursor, cita_id)
    except Exception as e:
        logger.error(f"Error al obtener datos de la cita {cita_id}: {e}")
        datos = None
    conn.close()

    if datos:
        try:
            enviar_en_segundo_plano(
                enviar_alerta_comprobante_admin,
                nombre_paciente=datos["nombre_paciente"],
                telefono=datos["telefono"],
                correo=datos["correo"],
                tratamiento=datos["tratamiento"],
                especialista=datos["doctor"],
                fecha=datos["fecha"],
                hora=datos["hora"],
                monto_adelanto=datos["monto_adelanto"],
                panel_url=f"{BASE_URL}/admin/citas",
                comprobante_path=os.path.join(
                    app.root_path, *ruta_rel.split("/")
                ),
            )
        except Exception as e:
            logger.error(f"Error al notificar voucher de la cita {cita_id}: {e}")

    flash(
        "✅ Comprobante recibido. Tu pago quedará confirmado tras la validación.",
        "success",
    )
    return redirect(url_for("pago", cita_id=cita_id, enviado=1))


@app.route("/comprobante/<int:cita_id>")
@login_required
def ver_comprobante(cita_id):
    """Sirve el comprobante de pago de una cita.

    Prioriza la imagen guardada en la base de datos (voucher_data); si no
    existe, cae al archivo en disco (registros antiguos). Accesible para el
    administrador y para el paciente dueño de la cita.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT paciente_id, voucher_data, voucher_mime,
               voucher_url, comprobante
        FROM citas
        WHERE id = %s
    """, (cita_id,))
    cita = cursor.fetchone()
    conn.close()

    if not cita:
        abort(404)

    es_admin = session.get("rol") == "admin"
    es_dueno = cita["paciente_id"] == session.get("usuario_id")
    if not (es_admin or es_dueno):
        abort(403)

    datos = cita["voucher_data"]
    if datos:
        return send_file(
            BytesIO(bytes(datos)),
            mimetype=cita["voucher_mime"] or "image/jpeg",
        )

    ruta = cita["voucher_url"] or cita["comprobante"]
    if ruta:
        ruta_limpia = ruta.replace("\\", "/")
        if ruta_limpia.startswith("static/"):
            ruta_limpia = ruta_limpia[len("static/"):]
        abs_path = os.path.join(app.root_path, "static", *ruta_limpia.split("/"))
        if os.path.exists(abs_path):
            return send_file(abs_path)

    abort(404)


def _culqi_headers():
    return {
        "Authorization": f"Bearer {CULQI_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def _culqi_charge_exitoso(data):
    """True si el objeto devuelto por Culqi es un cargo aprobado."""
    if not isinstance(data, dict) or data.get("object") != "charge":
        return False
    outcome = data.get("outcome") or {}
    return (outcome.get("type") or "").lower() == "venta_exitosa"


def _culqi_mensaje_error(data):
    """Extrae el mejor mensaje de error de una respuesta de Culqi."""
    if not isinstance(data, dict):
        return "No se pudo procesar el pago."
    return (
        data.get("user_message")
        or data.get("merchant_message")
        or data.get("message")
        or "No se pudo procesar el pago."
    )


def _culqi_obtener_cargo(charge_id):
    """Consulta un cargo en Culqi (para verificar el webhook)."""
    try:
        resp = requests.get(
            f"{CULQI_API_URL}/charges/{charge_id}",
            headers=_culqi_headers(),
            timeout=20,
        )
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.error(f"Culqi: no se pudo consultar el cargo {charge_id}: {e}")
        return None


def _registrar_pago_culqi(cita_id, *, monto, transaccion_id, payload):
    """Registra (idempotente) un pago aprobado de Culqi y confirma la cita.

    Devuelve un dict con los datos de la cita si se registró por primera vez,
    o None si ya estaba registrado / la cita no existe.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM pagos WHERE transaccion_id = %s", (transaccion_id,))
        if cursor.fetchone():
            return None

        cursor.execute("""
            SELECT c.id, c.fecha, c.hora, c.paciente_id,
                   u.nombre, u.apePaterno, u.apeMaterno, u.correo,
                   e.nombre AS especialidad
            FROM citas c
            JOIN usuarios u ON c.paciente_id = u.id
            JOIN especialidades e ON c.especialidad_id = e.id
            WHERE c.id = %s
        """, (cita_id,))
        cita = cursor.fetchone()
        if not cita:
            return None

        cursor.execute("""
            INSERT INTO pagos (id_cita, monto, tipo, gateway, transaccion_id, payload, estado)
            VALUES (%s, %s, 'adelanto', 'culqi', %s, %s, 'valido')
        """, (cita["id"], monto, transaccion_id, payload))

        cursor.execute("""
            UPDATE citas
            SET estado_pago = 'pagado', estado = 'confirmada'
            WHERE id = %s
        """, (cita["id"],))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Culqi: error registrando pago de la cita {cita_id}: {e}")
        return None
    finally:
        conn.close()

    # Notificaciones por correo (no bloquean el registro del pago).
    try:
        nombre_pac = (
            f"{cita['nombre']} {cita['apepaterno']} {cita['apematerno']}"
        ).strip()
        if cita.get("correo"):
            enviar_confirmacion_pago(
                destinatario=cita["correo"],
                nombre_paciente=nombre_pac,
                especialidad=cita["especialidad"],
                fecha=str(cita["fecha"]),
                hora=str(cita["hora"])[:5],
                monto=monto,
                transaccion_id=transaccion_id,
            )
        enviar_notificacion_pago_admin(
            nombre_paciente=nombre_pac,
            especialidad=cita["especialidad"],
            fecha=str(cita["fecha"]),
            hora=str(cita["hora"])[:5],
            monto=monto,
            transaccion_id=transaccion_id,
        )
    except Exception as e:
        logger.error(f"Culqi: error enviando correos de pago: {e}")

    return dict(cita)


@app.route("/pago/<int:cita_id>/culqi", methods=["POST"])
@login_required
def pago_culqi(cita_id):
    """Crea el cargo en Culqi usando el token generado por Checkout v4."""
    if not (CULQI_PUBLIC_KEY and CULQI_SECRET_KEY):
        return jsonify(ok=False, mensaje="El pago en línea no está disponible."), 503

    if request.form.get("tipo") == "evaluacion":
        return jsonify(ok=False, mensaje="Las evaluaciones no requieren pago en línea."), 400

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.especialidad_id, c.adelanto, c.estado_pago, c.paciente_id, u.correo
        FROM citas c
        JOIN usuarios u ON c.paciente_id = u.id
        WHERE c.id = %s AND c.paciente_id = %s
    """, (cita_id, session["usuario_id"]))
    cita = cursor.fetchone()

    if not cita:
        conn.close()
        return jsonify(ok=False, mensaje="Cita no encontrada."), 404

    # Resolver el adelanto efectivo (puede haber cambiado desde la reserva).
    monto, actualizado = _sincronizar_adelanto_cita(cursor, cita)
    if actualizado:
        conn.commit()
    conn.close()

    monto = float(monto or 0)
    if monto <= 0:
        return jsonify(ok=False, mensaje="Esta cita no requiere adelanto."), 400

    token = (request.form.get("token") or "").strip()
    if not token:
        datos_json = request.get_json(silent=True) or {}
        token = (datos_json.get("token") or "").strip()
    if not token:
        return jsonify(ok=False, mensaje="No se recibió el token de pago."), 400

    payload = {
        "amount": int(round(monto * 100)),
        "currency_code": CULQI_MONEDA,
        "email": cita["correo"] or "paciente@clinicaseledent.com",
        "source_id": token,
        "description": f"Adelanto cita #{cita_id} - Clinica Sele Dent",
        "metadata": {"cita_id": str(cita_id)},
    }
    try:
        resp = requests.post(
            f"{CULQI_API_URL}/charges",
            json=payload,
            headers=_culqi_headers(),
            timeout=25,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.error(f"Culqi: error creando cargo para la cita {cita_id}: {e}")
        return jsonify(ok=False, mensaje="No se pudo conectar con la pasarela."), 502

    if _culqi_charge_exitoso(data):
        transaccion_id = data.get("id") or ""
        registrada = _registrar_pago_culqi(
            cita_id,
            monto=monto,
            transaccion_id=transaccion_id,
            payload=json.dumps(data),
        )
        return jsonify(
            ok=True,
            confirmado=True,
            monto=monto,
            nueva=bool(registrada),
            mensaje="Pago aprobado. Tu cita quedó confirmada.",
        )

    return jsonify(
        ok=False,
        mensaje=_culqi_mensaje_error(data),
        codigo=data.get("type") if isinstance(data, dict) else None,
    ), 402


@app.route("/pago/culqi/webhook", methods=["POST"])
def culqi_webhook():
    """Webhook de Culqi: confirma el pago reconsultando el cargo (sin firma HMAC)."""
    evento = request.get_json(silent=True) or {}
    tipo = (evento.get("type") or "").lower()
    data = evento.get("data") or {}
    charge_id = data.get("id") if isinstance(data, dict) else None

    if not charge_id or not str(charge_id).startswith("chr_"):
        return jsonify(ok=True, ignorado=True), 200

    charge = _culqi_obtener_cargo(charge_id)
    if not _culqi_charge_exitoso(charge):
        return jsonify(ok=True, ignorado=True), 200

    metadata = charge.get("metadata") or {}
    cita_id = metadata.get("cita_id")
    if not cita_id:
        return jsonify(ok=True, ignorado=True), 200

    monto = float(charge.get("amount") or 0) / 100.0
    registrada = _registrar_pago_culqi(
        int(cita_id),
        monto=monto,
        transaccion_id=charge_id,
        payload=json.dumps(charge),
    )
    return jsonify(ok=True, nueva=bool(registrada), tipo=tipo), 200


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form["nombre"]
        apePaterno = request.form["apePaterno"]
        apeMaterno = request.form["apeMaterno"]
        dni = (request.form.get("dni") or "").strip()
        correo = (request.form["correo"] or "").strip().lower()
        clave = request.form["clave"]
        confirmar = request.form["confirmar"]
        siguiente = request.values.get("next")

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", correo):
            flash("⚠️ Correo electrónico inválido", "warning")
            return redirect(url_for("registro", next=siguiente))

        if dni and not re.fullmatch(r"\d{8}", dni):
            flash("⚠️ El DNI debe tener 8 dígitos.", "warning")
            return redirect(url_for("registro", next=siguiente))

        fecha_nac, error_fecha = _validar_fenacimiento(request.form.get("fenacimiento"))
        if error_fecha:
            flash(f"⚠️ {error_fecha}", "warning")
            return redirect(url_for("registro", next=siguiente))

        if clave != confirmar:
            flash("❌ Las contraseñas no coinciden", "danger")
            return redirect(url_for("registro", next=siguiente))

        if not _validar_password(clave):
            flash(PASSWORD_MENSAJE, "danger")
            return redirect(url_for("registro", next=siguiente))

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM usuarios WHERE LOWER(correo) = %s",
            (correo,)
        )
        existe = cursor.fetchone()
        if existe:
            conn.close()
            flash("⚠️ Correo ya registrado", "warning")
            return redirect(url_for("registro", next=siguiente))
        
        clave_hash = bcrypt.generate_password_hash(clave).decode("utf-8")


        cursor.execute("""
            INSERT INTO usuarios (
                nombre,
                apePaterno,
                apeMaterno,
                numero_documento,
                tipo_documento,
                fenacimiento,
                correo,
                contrasenia,
                id_rol,
                perfil_completo
            )   
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,2,FALSE)
            RETURNING id, nombre
        """, (
            nombre,
            apePaterno,
            apeMaterno,
            dni or None,
            "DNI" if dni else None,
            fecha_nac,
            correo,
            clave_hash
        ))
        try:
            nuevo = cursor.fetchone()
            conn.commit()
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            conn.close()
            flash("⚠️ Ese DNI ya está registrado en otra cuenta.", "warning")
            return redirect(url_for("registro", next=siguiente))
        conn.close()

        # Iniciar sesión y forzar a completar el perfil (DNI y WhatsApp) una
        # sola vez, justo después de registrarse.
        session["usuario_id"] = nuevo["id"]
        session["rol"] = "paciente"
        session["nombre"] = nuevo["nombre"]
        flash(
            "✅ Registro exitoso. Completa tu perfil para poder agendar tu cita.",
            "success",
        )
        return redirect(url_for("completar_perfil", next=siguiente))

    return render_template("registro.html", next=request.args.get("next"))


def _perfil_esta_completo(usuario_id):
    """Devuelve True si el usuario ya registró su DNI y teléfono."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(perfil_completo, TRUE) AS completo FROM usuarios WHERE id = %s",
            (usuario_id,),
        )
        fila = cursor.fetchone()
        conn.close()
        return bool(fila and fila["completo"])
    except Exception:
        # Si algo falla, no bloqueamos el flujo de agendamiento.
        return True


def _datos_perfil(usuario_id):
    """Devuelve los datos del usuario (o None) para pintar el formulario."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT correo, nombre, apepaterno, apematerno, numero_documento,
               telefono, fenacimiento
        FROM usuarios WHERE id = %s
    """, (usuario_id,))
    fila = cursor.fetchone()
    conn.close()
    return fila


def _calcular_edad(fecha_nac):
    """Calcula la edad (int) a partir de una fecha de nacimiento (date)."""
    if not fecha_nac:
        return None
    hoy = date.today()
    return hoy.year - fecha_nac.year - ((hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day))


def _validar_fenacimiento(valor):
    """Valida una fecha de nacimiento (YYYY-MM-DD).

    Devuelve (fecha: date | None, error: str | None).
    """
    valor = (valor or "").strip()
    if not valor:
        return None, "La fecha de nacimiento es obligatoria."
    try:
        fecha = datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None, "La fecha de nacimiento no es válida."
    if fecha > date.today():
        return None, "La fecha de nacimiento no puede ser futura."
    edad = _calcular_edad(fecha)
    if edad is None or edad < 0 or edad > 100:
        return None, "Ingresa una fecha de nacimiento válida."
    return fecha, None


# Contraseñas: mínimo 8 caracteres con mayúscula, minúscula, número y especial.
PASSWORD_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&_-])[A-Za-z\d@$!%*?&_-]{8,}$"
)
PASSWORD_MENSAJE = (
    "❌ La contraseña debe tener al menos 8 caracteres e incluir una mayúscula, "
    "una minúscula, un número y un carácter especial (@, $, !, %, *, ?, &, -, _)."
)


def _validar_password(clave):
    """True si la contraseña cumple la política mínima de seguridad."""
    return bool(PASSWORD_REGEX.fullmatch(clave or ""))


def _destino_seguro(valor, por_defecto="inicio"):
    """Devuelve una ruta interna segura (evita redirecciones abiertas)."""
    valor = (valor or "").strip()
    if valor.startswith("/") and not valor.startswith("//"):
        return valor
    return url_for(por_defecto)


def _url_actual():
    """Devuelve la URL interna actual (ruta + query) para volver tras el login."""
    destino = request.path
    if request.query_string:
        destino += "?" + request.query_string.decode("utf-8", "ignore")
    return destino


@app.route("/completar-perfil", methods=["GET", "POST"])
@login_required
def completar_perfil():
    """Obliga a completar DNI y WhatsApp (p.ej. tras login con Google)."""
    usuario_id = session["usuario_id"]
    siguiente = request.values.get("next")

    if request.method == "POST":
        dni = (request.form.get("dni") or "").strip()
        telefono = (request.form.get("telefono") or "").strip()

        # (c) Trazabilidad: datos recibidos desde el formulario.
        logger.info(
            "completar_perfil POST · usuario_id=%s · dni=%r · telefono=%r",
            usuario_id, dni, telefono,
        )

        nombre = (request.form.get("nombre") or "").strip()
        ape_paterno = (request.form.get("apePaterno") or "").strip()
        ape_materno = (request.form.get("apeMaterno") or "").strip()
        fecha_raw = (request.form.get("fenacimiento") or "").strip()
        fecha_nac, error_fecha = _validar_fenacimiento(fecha_raw)

        error = None
        if not re.fullmatch(r"\d{8}", dni):
            error = "⚠️ El DNI debe tener exactamente 8 dígitos."
        elif not re.fullmatch(r"[0-9+\s]{6,20}", telefono):
            error = "⚠️ Ingresa un número de WhatsApp válido."
        elif not nombre:
            error = "⚠️ Ingresa tus nombres."
        elif not ape_paterno or not ape_materno:
            error = "⚠️ Ingresa tus apellidos."
        elif error_fecha:
            error = f"⚠️ {error_fecha}"

        form_extra = dict(
            form_dni=dni, form_telefono=telefono,
            form_nombre=nombre, form_apePaterno=ape_paterno, form_apeMaterno=ape_materno,
            form_fenacimiento=fecha_raw,
        )

        if error:
            logger.warning(
                "completar_perfil: validación fallida · usuario_id=%s", usuario_id
            )
            return render_template(
                "completar_perfil.html", datos=_datos_perfil(usuario_id),
                next=siguiente, error=error, **form_extra,
            )

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE usuarios
                SET numero_documento = %s,
                    tipo_documento   = COALESCE(tipo_documento, 'DNI'),
                    telefono         = %s,
                    nombre           = %s,
                    apepaterno       = %s,
                    apematerno       = %s,
                    fenacimiento     = %s,
                    perfil_completo  = TRUE
                WHERE id = %s
            """, (dni, telefono, nombre, ape_paterno, ape_materno,
                  fecha_nac, usuario_id))
            filas = cursor.rowcount
            conn.commit()
            logger.info(
                "completar_perfil: UPDATE OK · usuario_id=%s · filas=%s",
                usuario_id, filas,
            )
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            logger.warning(
                "completar_perfil: DNI duplicado · usuario_id=%s · dni=%s",
                usuario_id, dni,
            )
            conn.close()
            return render_template(
                "completar_perfil.html", datos=_datos_perfil(usuario_id),
                next=siguiente,
                error="⚠️ Ese DNI ya está registrado en otra cuenta.",
                **form_extra,
            )
        except Exception as e:
            conn.rollback()
            conn.close()
            # (c) Log del error real de Supabase/PostgreSQL en lugar de ocultarlo.
            logger.exception(
                "completar_perfil: error al actualizar en Supabase · usuario_id=%s · dni=%s",
                usuario_id, dni,
            )
            return render_template(
                "completar_perfil.html", datos=_datos_perfil(usuario_id),
                next=siguiente,
                error=f"❌ No se pudo guardar tu perfil: {e}",
                **form_extra,
            )

        conn.close()

        # ¡MUY IMPORTANTE!: refrescar los datos del usuario en la sesión.
        session["perfil_completo"] = True
        session["dni"] = dni
        session["telefono"] = telefono

        flash("✅ Perfil completado correctamente. Ya puedes agendar tus citas.", "success")

        if session.get("rol") == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(_destino_seguro(siguiente, "mis_citas"))

    siguiente = request.args.get("next")
    datos = _datos_perfil(usuario_id)

    if datos and datos["numero_documento"] and datos["telefono"]:
        return redirect(_destino_seguro(siguiente))

    return render_template("completar_perfil.html", datos=datos, next=siguiente)


@app.route("/logout")
def logout():
    _log_auditoria("logout")
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def inicio():
                                                
    if session.get("rol") == "admin":
        return redirect(url_for("admin_dashboard"))

                                     
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, descripcion FROM especialidades WHERE estado = 'activo'")
    filas = cursor.fetchall()
    conn.close()
    especialidades = [_map_especialidad(f) for f in filas]

    return render_template("index.html", especialidades=especialidades)


@app.route("/login", methods=["GET", "POST"])
def login():
    ip = request.remote_addr                
    siguiente = request.values.get("next")

                                 
    baneada, minutos = esta_baneada(ip)
    if baneada:
        flash(f"🚫 IP bloqueada. Intenta en {minutos} minutos", "danger")
        return render_template("login.html", next=siguiente)

    if request.method == "POST":
        correo = (request.form.get("usuario") or request.form.get("correo") or "").strip().lower()
        clave = request.form["clave"]

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", correo):
            flash("❌ Correo electrónico inválido", "danger")
            return redirect(url_for("login", next=siguiente))

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT u.*, COALESCE(r.nombre, 'paciente') AS rol
            FROM usuarios u
            LEFT JOIN roles r ON u.id_rol = r.id
            WHERE LOWER(u.correo) = %s
        """, (correo,))
        user = cursor.fetchone()
        conn.close()

                             
        if not user:
            baneada, restantes = registrar_intento_fallido(ip)
            flash(f"❌ Usuario no existe ({restantes} intentos restantes)", "danger")
            return redirect(url_for("login", next=siguiente))

                            
        if user["estado"] != "ACTIVO":
            baneada, restantes = registrar_intento_fallido(ip)
            flash("❌ Usuario inactivo", "danger")
            return redirect(url_for("login", next=siguiente))

                                 
        if not bcrypt.check_password_hash(user["contrasenia"], clave):
            baneada, restantes = registrar_intento_fallido(ip)

            if baneada:
                flash("🚫 Demasiados intentos. IP bloqueada 15 min", "danger")
            else:
                flash(f"❌ Contraseña incorrecta ({restantes} intentos restantes)", "danger")

            return redirect(url_for("login", next=siguiente))

                                       
        limpiar_ip(ip)

        session["usuario_id"] = user["id"]
        session["nombre"] = user["nombre"]
        session["rol"] = user["rol"]
        _log_auditoria("login", user["id"])

        # Volver a la página que el usuario intentaba abrir (p.ej. agendar).
        if user["rol"] == "admin":
            # El admin siempre va al panel, salvo que el destino sea otra ruta /admin.
            if siguiente and siguiente.startswith("/admin"):
                return redirect(siguiente)
            return redirect(url_for("admin_dashboard"))
        else:
            return redirect(_destino_seguro(siguiente, "mis_citas"))

    return render_template("login.html", next=request.args.get("next"))


# ════════════════════════════════════════════════════════════
#   RECUPERACIÓN DE CONTRASEÑA (código por correo)
# ════════════════════════════════════════════════════════════
RESET_VIGENCIA_MIN = 15
RESET_MAX_INTENTOS = 5


def _generar_codigo() -> str:
    """Genera un código numérico de 6 dígitos."""
    return f"{random.randint(0, 999999):06d}"


@app.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    """Paso 1: el usuario ingresa su correo y recibe un código."""
    if request.method == "POST":
        correo = (request.form.get("correo") or "").strip().lower()

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", correo):
            flash("❌ Correo electrónico inválido", "danger")
            return redirect(url_for("recuperar"))

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, nombre, correo
            FROM usuarios
            WHERE LOWER(correo) = %s AND estado = 'ACTIVO'
        """, (correo,))
        user = cursor.fetchone()

        # Por seguridad no revelamos si el correo existe o no.
        if not user:
            conn.close()
            session["reset_correo"] = correo
            flash("✅ Si el correo está registrado, recibirás un código.", "success")
            return redirect(url_for("verificar_codigo"))

        codigo = _generar_codigo()
        expira = datetime.now() + timedelta(minutes=RESET_VIGENCIA_MIN)

        # Invalida códigos anteriores de ese correo
        cursor.execute(
            "UPDATE codigos_recuperacion SET usado = TRUE WHERE correo = %s AND usado = FALSE",
            (correo,),
        )
        cursor.execute("""
            INSERT INTO codigos_recuperacion (correo, codigo, expira)
            VALUES (%s, %s, %s)
        """, (correo, codigo, expira))
        conn.commit()
        conn.close()

        enviado = enviar_codigo_recuperacion(
            destinatario=user["correo"],
            nombre=user["nombre"],
            codigo=codigo,
            minutos=RESET_VIGENCIA_MIN,
        )

        if not enviado:
            flash("⚠️ No se pudo enviar el correo. Intenta nuevamente.", "warning")
            return redirect(url_for("recuperar"))

        session["reset_correo"] = correo
        session.pop("reset_intentos", None)
        flash("✅ Enviamos un código a tu correo electrónico.", "success")
        return redirect(url_for("verificar_codigo"))

    return render_template("recuperar.html")


@app.route("/verificar_codigo", methods=["GET", "POST"])
def verificar_codigo():
    """Paso 2: el usuario ingresa el código recibido."""
    correo = session.get("reset_correo")
    if not correo:
        flash("⚠️ Primero ingresa tu correo electrónico.", "warning")
        return redirect(url_for("recuperar"))

    if request.method == "POST":
        codigo = (request.form.get("codigo") or "").strip()

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, expira, usado
            FROM codigos_recuperacion
            WHERE correo = %s AND codigo = %s
            ORDER BY fecha_creacion DESC
            LIMIT 1
        """, (correo, codigo))
        row = cursor.fetchone()

        valido = (
            row is not None
            and not row["usado"]
            and row["expira"] >= datetime.now()
        )

        if not valido:
            conn.close()
            intentos = session.get("reset_intentos", 0) + 1
            session["reset_intentos"] = intentos

            if intentos >= RESET_MAX_INTENTOS:
                session.pop("reset_correo", None)
                session.pop("reset_intentos", None)
                flash("🚫 Demasiados intentos. Solicita un nuevo código.", "danger")
                return redirect(url_for("recuperar"))

            restantes = RESET_MAX_INTENTOS - intentos
            flash(f"❌ Código inválido o vencido ({restantes} intentos restantes)", "danger")
            return redirect(url_for("verificar_codigo"))

        # Marca el código como usado
        cursor.execute(
            "UPDATE codigos_recuperacion SET usado = TRUE WHERE id = %s",
            (row["id"],),
        )
        conn.commit()
        conn.close()

        session["reset_ok"] = correo
        session.pop("reset_intentos", None)
        flash("✅ Código verificado. Define tu nueva contraseña.", "success")
        return redirect(url_for("restablecer"))

    return render_template("verificar_codigo.html", correo=correo)


@app.route("/restablecer", methods=["GET", "POST"])
def restablecer():
    """Paso 3: el usuario establece su nueva contraseña."""
    correo = session.get("reset_ok")
    if not correo:
        flash("⚠️ Debes verificar tu código primero.", "warning")
        return redirect(url_for("recuperar"))

    if request.method == "POST":
        clave = request.form.get("clave") or ""
        confirmar = request.form.get("confirmar") or ""

        if len(clave) < 8:
            flash("❌ La contraseña debe tener al menos 8 caracteres", "danger")
            return redirect(url_for("restablecer"))
        if clave != confirmar:
            flash("❌ Las contraseñas no coinciden", "danger")
            return redirect(url_for("restablecer"))

        clave_hash = bcrypt.generate_password_hash(clave).decode("utf-8")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios SET contrasenia = %s WHERE LOWER(correo) = %s",
            (clave_hash, correo),
        )
        conn.commit()
        conn.close()

        session.pop("reset_ok", None)
        session.pop("reset_correo", None)
        flash("✅ Contraseña actualizada. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("login"))

    return render_template("restablecer.html", correo=correo)


@app.route("/contacto", methods=["GET", "POST"])
def contacto():
    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        telefono = (request.form.get("telefono") or "").strip()
        asunto = (request.form.get("asunto") or "").strip()
        mensaje = (request.form.get("mensaje") or "").strip()
        acepta = request.form.get("acepta")

        errores = []
        if len(nombre) < 3:
            errores.append("Ingresa tu nombre completo.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email):
            errores.append("Ingresa un correo electrónico válido.")
        if not asunto:
            errores.append("Selecciona un asunto.")
        if len(mensaje) < 10:
            errores.append("El mensaje debe tener al menos 10 caracteres.")
        if not acepta:
            errores.append("Debes aceptar la política de privacidad.")

        if errores:
            return render_template("contacto.html", errores=errores)

        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO mensajes_contacto (nombre, email, telefono, asunto, mensaje)
                VALUES (%s, %s, %s, %s, %s)
            """, (nombre, email, telefono or None, asunto, mensaje))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error al guardar mensaje de contacto: {e}")

        fecha_envio = datetime.now().strftime("%d/%m/%Y %H:%M")
        enviar_notificacion_contacto(nombre, email, telefono, asunto, mensaje, fecha_envio)
        enviar_confirmacion_contacto(email, nombre, asunto)

        return render_template(
            "contacto.html",
            enviado=True,
            nombre_contacto=nombre,
            flash_ok="Hemos recibido tu mensaje y te responderemos a la brevedad.",
        )

    return render_template("contacto.html")


@app.route("/nosotros")
def nosotros():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM especialidades")
    especialidades = cursor.fetchall()
    conn.close()
    return render_template("nosotros.html", especialidades=especialidades)

@app.route("/especialidades")
def especialidades():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, descripcion FROM especialidades WHERE estado = 'activo'")
    filas = cursor.fetchall()
    conn.close()
    lista = [_map_especialidad(f) for f in filas]
    return render_template("especialidades.html", especialidades=lista)


ESPECIALIDAD_IMGS = {
    "ortodoncia": "brakets.jpg",
    "endodoncia": "endodoncia.jpg",
    "odontologia general": "limpieza_dental.jpg",
    "cirugia oral": "extraccion.jpg",
    "implantologia": "remplazo.jpg",
    "periodoncia": "limpieza_dental.jpg",
    "estetica dental": "blanquiamiento.jpg",
    "cirugia": "extraccion.jpg",
    "odontopediatria": "limpieza_dental.jpg",
    "rehabilitacion oral": "remplazo.jpg",
    "radiologia": "cuatro.jpg",
    "radiologia e imagen 3d": "cuatro.jpg",
    "urgencias odontologicas": "extraccion.jpg",
}

ESPECIALIDAD_DESC = {
    "ortodoncia": "Alineamos tus dientes con brackets y alineadores para lograr una sonrisa armoniosa.",
    "endodoncia": "Tratamiento de conductos que salva piezas dentales infectadas o muy dañadas.",
    "odontologia general": "Prevención, diagnóstico y tratamiento integral de tu salud bucal.",
    "cirugia oral": "Extracciones y procedimientos quirúrgicos de la cavidad oral con máxima seguridad.",
    "implantologia": "Reemplazamos piezas dentales perdidas con implantes de titanio de alta durabilidad.",
    "periodoncia": "Cuidamos tus encías y los tejidos que sostienen firmemente tus dientes.",
    "estetica dental": "Mejoramos tu sonrisa con blanqueamiento, carillas y diseños personalizados.",
    "cirugia": "Extracciones y procedimientos quirúrgicos de la cavidad oral con máxima seguridad.",
    "odontopediatria": "Atención dental especializada para niños y adolescentes, con un trato cercano y sin miedo.",
    "rehabilitacion oral": "Restauración de la función y estética mediante coronas y prótesis a medida.",
    "radiologia": "Radiología y procedimientos guiados por imágenes para diagnóstico y tratamiento.",
    "radiologia e imagen 3d": "Tomografías y escaneo intraoral de alta precisión para un diagnóstico exacto.",
    "urgencias odontologicas": "Atención rápida ante dolores agudos y traumatismos dentales.",
}


def _sin_acentos(texto):
    return (texto or "").lower().replace("á", "a").replace("é", "e").replace(
        "í", "i").replace("ó", "o").replace("ú", "u")


def _map_especialidad(fila):
    nombre = fila.get("nombre") or ""
    clave = _sin_acentos(nombre)
    descripcion = (fila.get("descripcion") or "").strip()
    return {
        "id": fila.get("id"),
        "nombre": nombre,
        "descripcion": descripcion or ESPECIALIDAD_DESC.get(
            clave, "Atención odontológica integral."),
        "imagen": ESPECIALIDAD_IMGS.get(clave, "cuatro.jpg"),
        "categoria": nombre,
    }


@app.route("/especialidades/<int:id>")
def detalle_especialidad(id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre, descripcion FROM especialidades WHERE id = %s", (id,))
    fila = cursor.fetchone()
    if not fila:
        conn.close()
        flash("⚠️ Especialidad no encontrada", "warning")
        return redirect(url_for("especialidades"))

    cursor.execute("""
        SELECT nombre, descripcion, precio_base
        FROM tratamientos
        WHERE id_especialidad = %s
        ORDER BY nombre
    """, (id,))
    tratamientos = cursor.fetchall()

    cursor.execute("""
        SELECT u.id, u.nombre, u.apepaterno, u.apematerno
        FROM odontologo_especialidad oe
        JOIN usuarios u ON u.id = oe.odontologo_id
        WHERE oe.especialidad_id = %s AND oe.estado = 'activo'
        ORDER BY u.nombre
    """, (id,))
    odontologos = cursor.fetchall()
    conn.close()

    esp = _map_especialidad(fila)
    esp["icono"] = "fa-solid fa-tooth"
    esp["beneficios"] = [
        "Diagnóstico y evaluación clínica personalizada",
        "Especialistas con formación profesional",
        "Equipamiento moderno y material esterilizado",
        "Planes de tratamiento adaptados a tu caso",
    ]

    return render_template(
        "detalle_especialidad.html",
        esp=esp,
        tratamientos=tratamientos,
        odontologos=odontologos,
    )


@app.route("/tratamientos")
def tratamientos():
    """Catálogo público de tratamientos agrupados por especialidad."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id_tratamiento, t.nombre, t.descripcion, t.precio_base,
               t.duracion_minutos,
               e.id AS especialidad_id, e.nombre AS especialidad
        FROM tratamientos t
        JOIN especialidades e ON t.id_especialidad = e.id
        WHERE COALESCE(t.activo, TRUE) = TRUE
          AND e.estado = 'activo'
        ORDER BY e.nombre, t.nombre
    """)
    filas = cursor.fetchall()
    conn.close()

    grupos = []
    indice = {}
    for f in filas:
        eid = f["especialidad_id"]
        if eid not in indice:
            indice[eid] = {
                "especialidad_id": eid,
                "especialidad": f["especialidad"],
                "tratamientos": [],
            }
            grupos.append(indice[eid])
        indice[eid]["tratamientos"].append({
            "id_tratamiento": f["id_tratamiento"],
            "nombre": f["nombre"],
            "descripcion": f["descripcion"],
            "precio_base": f["precio_base"],
            "duracion_minutos": f["duracion_minutos"],
        })

    return render_template("tratamientos.html", grupos=grupos)


ESTADOS_ATENDIDA = {"atendida", "atendido", "completada"}
ESTADOS_CANCELADA = {"cancelada", "cancelado"}
ESTADOS_ACTIVA = {"pendiente", "confirmada"}


def _formatear_citas(filas, wa_numero):
    """Agrega campos de presentación (fechas largas, WhatsApp) a cada cita."""
    citas = []
    for fila in filas:
        c = dict(fila)
        fecha = c.get("fecha")
        hora = c.get("hora")

        if hasattr(fecha, "strftime"):
            c["fecha_corta"] = fecha.strftime("%d/%m/%Y")
            c["fecha_larga"] = (
                f"{DIAS_ES[fecha.weekday()]} {fecha.day} de "
                f"{MESES_ES[fecha.month - 1]} del {fecha.year}"
            )
        else:
            c["fecha_corta"] = str(fecha or "")
            c["fecha_larga"] = str(fecha or "")

        c["hora_corta"] = hora.strftime("%H:%M") if hasattr(hora, "strftime") else str(hora or "")

        especialidad = c.get("especialidad") or "Atención odontológica"
        mensaje = (
            f"Hola Clínica SELEDENT, necesito ayuda con mi cita de "
            f"{especialidad} del {c['fecha_corta']} a las {c['hora_corta']}."
        )
        c["wa_link"] = f"https://wa.me/{wa_numero}?text={quote(mensaje)}"
        citas.append(c)
    return citas


@app.route("/mis_citas")
@login_required
def mis_citas():
    wa_numero = dotenv_values().get("WHATSAPP_NUMERO", "51956536766")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id,
               e.nombre AS especialidad,
               c.tipo_atencion,
               c.prioridad,
               c.fecha,
               c.hora,
               c.estado,
               c.estado_pago,
               c.comprobante,
               c.nro_operacion,
               c.adelanto,
               c.motivo_cancelacion,
               COALESCE(c.sede, %s) AS sede,
               COALESCE(
                   NULLIF(TRIM(CONCAT_WS(' ', o.nombre, o.apepaterno, o.apematerno)), ''),
                   'Por asignar'
               ) AS odontologo
        FROM citas c
        JOIN especialidades e ON c.especialidad_id = e.id
        LEFT JOIN usuarios o ON c.odontologo_id = o.id
        WHERE c.paciente_id = %s
        ORDER BY c.fecha DESC, c.hora DESC
    """, (SEDE_PREDETERMINADA, session["usuario_id"]))

    citas = _formatear_citas(cursor.fetchall(), wa_numero)
    conn.close()

    proximas = [c for c in citas if c["estado"] in ESTADOS_ACTIVA]
    historial = [c for c in citas if c["estado"] in ESTADOS_ATENDIDA]
    canceladas = [c for c in citas if c["estado"] in ESTADOS_CANCELADA]

    manana = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    return render_template(
        "mis_citas.html",
        citas=citas,
        proximas=proximas,
        historial=historial,
        canceladas=canceladas,
        horas=HORAS_SISTEMA,
        fecha_min=manana,
        wa_numero=wa_numero,
        es_doctor=_es_doctor(),
        rol=session.get("rol"),
    )


@app.route("/documentos")
@login_required
def documentos():
    """Centro de documentos clínicos del paciente (7 secciones)."""
    return render_template("documentos.html")


@app.route("/citas/<int:cita_id>/cancelar", methods=["POST"])
@login_required
def cancelar_cita(cita_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT estado FROM citas WHERE id = %s AND paciente_id = %s",
        (cita_id, session["usuario_id"]),
    )
    cita = cursor.fetchone()

    if not cita:
        conn.close()
        flash("❌ No se encontró la cita.", "danger")
        return redirect(url_for("mis_citas"))

    if cita["estado"] not in ESTADOS_ACTIVA:
        conn.close()
        flash("⚠️ Esta cita ya no se puede cancelar.", "warning")
        return redirect(url_for("mis_citas"))

    motivo = (request.form.get("motivo") or "").strip()

    cursor.execute("""
        UPDATE citas
        SET estado = 'cancelada', motivo_cancelacion = %s
        WHERE id = %s AND paciente_id = %s
    """, (motivo or None, cita_id, session["usuario_id"]))
    conn.commit()
    conn.close()
    _log_auditoria("cancelar_cita_paciente", detalle=f"cita #{cita_id}")

    flash("✅ Tu cita fue cancelada correctamente.", "success")
    return redirect(url_for("mis_citas"))


@app.route("/citas/<int:cita_id>/reprogramar", methods=["POST"])
@login_required
def reprogramar_cita(cita_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT especialidad_id, estado FROM citas WHERE id = %s AND paciente_id = %s",
        (cita_id, session["usuario_id"]),
    )
    cita = cursor.fetchone()

    if not cita:
        conn.close()
        flash("❌ No se encontró la cita.", "danger")
        return redirect(url_for("mis_citas"))

    if cita["estado"] not in ESTADOS_ACTIVA:
        conn.close()
        flash("⚠️ Esta cita ya no se puede reprogramar.", "warning")
        return redirect(url_for("mis_citas"))

    fecha_str = (request.form.get("fecha") or "").strip()
    hora = (request.form.get("hora") or "").strip()

    try:
        nueva_fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        conn.close()
        flash("❌ Debes elegir una fecha válida.", "danger")
        return redirect(url_for("mis_citas"))

    if nueva_fecha < date.today() + timedelta(days=1):
        conn.close()
        flash("❌ Solo puedes reprogramar desde mañana.", "danger")
        return redirect(url_for("mis_citas"))

    if hora not in HORAS_SISTEMA:
        conn.close()
        flash("❌ Debes elegir una hora válida.", "danger")
        return redirect(url_for("mis_citas"))

    cursor.execute("""
        SELECT id FROM citas
        WHERE especialidad_id = %s AND fecha = %s AND hora = %s AND id <> %s
    """, (cita["especialidad_id"], nueva_fecha, hora, cita_id))
    if cursor.fetchone():
        conn.close()
        flash("❌ Esa hora ya está ocupada. Elige otro horario.", "warning")
        return redirect(url_for("mis_citas"))

    cursor.execute(
        "UPDATE citas SET fecha = %s, hora = %s WHERE id = %s AND paciente_id = %s",
        (nueva_fecha, hora, cita_id, session["usuario_id"]),
    )
    conn.commit()
    conn.close()
    _log_auditoria("reprogramar_cita_paciente", detalle=f"cita #{cita_id}")

    flash("✅ Tu cita fue reprogramada correctamente.", "success")
    return redirect(url_for("mis_citas"))


@app.route("/doctor/dashboard")
@doctor_required
def doctor_dashboard():
    """Punto de entrada del panel del doctor (su vista de citas)."""
    return redirect(url_for("mis_citas"))


@app.route("/doctor/agendar", methods=["GET", "POST"])
@doctor_required
def agendar_doctor():
    """Gestión interna de citas para doctores/odontólogos.

    Permite al doctor programar una cita asignándose a sí mismo (odontologo_id
    = su propio id) y eligiendo al paciente, especialidad, tratamiento y horario.
    """
    conn = get_connection()
    cursor = conn.cursor()

    doctor_id = session["usuario_id"]

    if request.method == "POST":
        paciente_id = (request.form.get("paciente_id") or "").strip()
        especialidad_id = (request.form.get("especialidad") or "").strip()
        tratamiento_id = (request.form.get("tratamiento") or "").strip() or None
        fecha_str = (request.form.get("fecha") or "").strip()
        hora = (request.form.get("hora") or "").strip()
        mensaje = (request.form.get("mensaje") or "").strip()

        if not paciente_id.isdigit():
            conn.close()
            flash("❌ Debes seleccionar un paciente", "danger")
            return redirect(url_for("agendar_doctor"))

        if not especialidad_id.isdigit():
            conn.close()
            flash("❌ Debes seleccionar una especialidad", "danger")
            return redirect(url_for("agendar_doctor"))

        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            conn.close()
            flash("❌ Debes elegir una fecha válida", "danger")
            return redirect(url_for("agendar_doctor"))

        if fecha < date.today():
            conn.close()
            flash("❌ La fecha no puede ser anterior a hoy", "danger")
            return redirect(url_for("agendar_doctor"))

        if hora not in HORAS_SISTEMA:
            conn.close()
            flash("❌ Debes elegir una hora válida", "danger")
            return redirect(url_for("agendar_doctor"))

        if tratamiento_id and not str(tratamiento_id).isdigit():
            tratamiento_id = None

        # Hora ocupada para el mismo doctor.
        cursor.execute(
            """
            SELECT id FROM citas
            WHERE odontologo_id = %s AND fecha = %s AND hora = %s
              AND estado NOT IN ('cancelada', 'cancelado')
            """,
            (doctor_id, fecha, hora),
        )
        if cursor.fetchone():
            conn.close()
            flash("❌ Ya tienes una cita agendada a esa hora.", "warning")
            return redirect(url_for("agendar_doctor"))

        adelanto = _resolver_adelanto(cursor, int(especialidad_id), tratamiento_id)

        try:
            cursor.execute(
                """
                INSERT INTO citas
                (paciente_id, odontologo_id, especialidad_id, fecha, hora, estado,
                 estado_pago, tipo_atencion, sede, prioridad, observaciones, adelanto)
                VALUES (%s, %s, %s, %s, %s, 'confirmada', 'pendiente',
                        %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    int(paciente_id),
                    doctor_id,
                    int(especialidad_id),
                    fecha,
                    hora,
                    "Cita médica (doctor)",
                    SEDE_PREDETERMINADA,
                    PRIORIDAD_NORMAL,
                    mensaje or None,
                    adelanto,
                ),
            )
            cita_id = cursor.fetchone()["id"]
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            conn.close()
            flash("❌ Ya existe una cita en ese horario.", "danger")
            return redirect(url_for("agendar_doctor"))

        if tratamiento_id and str(tratamiento_id).isdigit():
            cursor.execute(
                """
                INSERT INTO cita_tratamiento (id_cita, id_tratamiento, precio_aplicado)
                VALUES (
                    %s, %s,
                    (SELECT precio_base FROM tratamientos WHERE id_tratamiento = %s)
                )
                """,
                (cita_id, int(tratamiento_id), int(tratamiento_id)),
            )

        conn.commit()
        conn.close()
        _log_auditoria("agendar_cita_doctor", detalle=f"cita #{cita_id}")

        flash("✅ Cita registrada correctamente como doctor.", "success")
        return redirect(url_for("mis_citas"))

    # ---------- GET ----------
    cursor.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
    especialidades = cursor.fetchall()

    cursor.execute("""
        SELECT u.id, u.nombre, u.apepaterno, u.apematerno, u.numero_documento
        FROM usuarios u
        WHERE u.id_rol = 2 AND u.estado = 'ACTIVO'
        ORDER BY u.apepaterno, u.nombre
    """)
    pacientes = cursor.fetchall()

    conn.close()

    return render_template(
        "doctor_agendar.html",
        especialidades=especialidades,
        pacientes=pacientes,
        horas=HORAS_SISTEMA,
        hoy=date.today().strftime("%Y-%m-%d"),
    )


@app.route("/mi_cuenta")
@login_required
def mi_cuenta():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            u.id,
            u.tipo_documento,
            u.numero_documento,
            u.nombre,
            u.apePaterno,
            u.apeMaterno,
            u.correo,
            u.telefono,
            u.direccion,
            u.fenacimiento,
            COALESCE(r.nombre, 'paciente') AS rol,
            u.estado,
            u.fecha_registro
        FROM usuarios u
        LEFT JOIN roles r ON u.id_rol = r.id
        WHERE u.id = %s
    """, (session["usuario_id"],))

    usuario = cursor.fetchone()

    cursor.execute("""
        SELECT c.id, e.nombre AS especialidad, c.fecha, c.hora, c.estado
        FROM citas c
        JOIN especialidades e ON c.especialidad_id = e.id
        WHERE c.paciente_id = %s
        ORDER BY c.fecha DESC
    """, (session["usuario_id"],))

    citas = cursor.fetchall()
    conn.close()

    edad = _calcular_edad(usuario.get("fenacimiento")) if usuario else None

    return render_template("mi_cuenta.html", usuario=usuario, citas=citas, edad=edad)


@app.route("/mi_cuenta/actualizar", methods=["POST"])
@login_required
def mi_cuenta_actualizar():
    """Actualiza en caliente teléfono / correo / dirección del usuario."""
    data = request.get_json(silent=True) or {}
    campo = (data.get("campo") or "").strip()
    valor = (data.get("valor") or "").strip()

    permitidos = {"telefono", "correo", "direccion", "dni", "nombre",
                  "apepaterno", "apematerno", "fenacimiento"}
    if campo not in permitidos:
        return jsonify({"ok": False, "mensaje": "Campo no permitido."}), 400

    nombres_actualizados = None
    fecha_nac = None

    if campo == "telefono":
        if valor and not re.fullmatch(r"[0-9+\s]{6,20}", valor):
            return jsonify({"ok": False, "mensaje": "Ingresa un número de teléfono válido."}), 400
    elif campo == "correo":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", valor):
            return jsonify({"ok": False, "mensaje": "Ingresa un correo electrónico válido."}), 400
        valor = valor.lower()
    elif campo == "direccion":
        if len(valor) > 255:
            return jsonify({"ok": False, "mensaje": "La dirección es demasiado larga."}), 400
    elif campo == "dni":
        if not re.fullmatch(r"\d{8}", valor):
            return jsonify({"ok": False, "mensaje": "El DNI debe tener 8 dígitos."}), 400
        ok, payload, status = consultar_dni_api(valor)
        if not ok:
            return jsonify({"ok": False, "mensaje": payload.get("message", "Error al consultar el DNI.")}), status
        nombres_actualizados = {
            "nombre": payload.get("nombres", ""),
            "apepaterno": payload.get("apePaterno", ""),
            "apematerno": payload.get("apeMaterno", ""),
        }
    elif campo in ("nombre", "apepaterno", "apematerno"):
        if not valor:
            return jsonify({"ok": False, "mensaje": "Este campo no puede quedar vacío."}), 400
        if len(valor) > 100:
            return jsonify({"ok": False, "mensaje": "El valor es demasiado largo."}), 400
    elif campo == "fenacimiento":
        fecha_nac, error_fecha = _validar_fenacimiento(valor)
        if error_fecha:
            return jsonify({"ok": False, "mensaje": error_fecha}), 400

    conn = get_connection()
    cursor = conn.cursor()
    try:
        if campo == "fenacimiento":
            cursor.execute(
                "UPDATE usuarios SET fenacimiento = %s WHERE id = %s",
                (fecha_nac, session["usuario_id"]),
            )
        elif campo == "dni":
            cursor.execute("""
                UPDATE usuarios
                SET numero_documento = %s,
                    tipo_documento   = 'DNI',
                    nombre           = %s,
                    apepaterno       = %s,
                    apematerno       = %s
                WHERE id = %s
            """, (valor, nombres_actualizados["nombre"],
                  nombres_actualizados["apepaterno"],
                  nombres_actualizados["apematerno"], session["usuario_id"]))
        else:
            cursor.execute(
                f"UPDATE usuarios SET {campo} = %s WHERE id = %s",
                (valor or None, session["usuario_id"]),
            )
        conn.commit()
        _log_auditoria("perfil_actualizado", session["usuario_id"])
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        conn.close()
        return jsonify({"ok": False, "mensaje": "Ese dato ya está registrado en otra cuenta."}), 409
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.exception("mi_cuenta_actualizar: error al guardar %s", campo)
        return jsonify({"ok": False, "mensaje": f"No se pudo guardar: {e}"}), 500
    conn.close()

    respuesta = {
        "ok": True, "campo": campo, "valor": valor,
        "mensaje": "Datos actualizados correctamente.",
    }
    if nombres_actualizados is not None:
        respuesta["nombres"] = nombres_actualizados
    if campo == "fenacimiento":
        respuesta["edad"] = _calcular_edad(fecha_nac)
        respuesta["valor"] = fecha_nac.strftime("%Y-%m-%d")
    return jsonify(respuesta)

@app.route("/api/citas")
@login_required
def api_citas():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.fecha, c.hora, e.nombre
        FROM citas c
        JOIN especialidades e ON c.especialidad_id = e.id
    """)

    citas = cursor.fetchall()
    conn.close()

    eventos = []

    for c in citas:
        eventos.append({
            "title": c["nombre"],
            "start": f"{c['fecha']}T{c['hora']}"
        })

    return jsonify(eventos)

@app.route("/horarios_disponibles", methods=["POST"])
@login_required
def horarios_disponibles():

    data = request.get_json()
    fecha = data["fecha"]
    especialidad_id = data["especialidad"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT hora FROM citas
        WHERE fecha = %s AND especialidad_id = %s
    """, (fecha, especialidad_id))

    ocupadas = [str(c["hora"]) for c in cursor.fetchall()]

    conn.close()

    disponibles = [h for h in HORAS_SISTEMA if h not in ocupadas]

    return jsonify(disponibles)

@app.route("/buscar")
def buscar_especialidad():

    query = request.args.get("q")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM especialidades
        WHERE nombre LIKE %s OR descripcion LIKE %s
    """, (f"%{query}%", f"%{query}%"))

    resultados = cursor.fetchall()
    conn.close()

    if resultados:
        return render_template("resultados_busqueda.html", resultados=resultados, query=query)
    else:
        flash("❌ No se encontró la especialidad", "danger")
        return redirect(url_for("inicio"))
    

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if "usuario_id" not in session:
            return redirect(url_for("login", next=_url_actual()))

        if session.get("rol") != "admin":
            flash("❌ Acceso denegado", "danger")
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated_function

_DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _etiqueta_fecha(fecha, hoy):
    """Etiqueta legible para agrupar citas por fecha (Hoy/Ayer/Anteayer/fecha)."""
    if fecha == hoy:
        return "Hoy"
    if fecha == hoy - timedelta(days=1):
        return "Ayer"
    if fecha == hoy - timedelta(days=2):
        return "Anteayer"
    return f"{_DIAS_SEMANA[fecha.weekday()]} {fecha.day} {_MESES_ABREV[fecha.month - 1]}"


def _rango_paginas(actual, total, margen=1):
    """Páginas a mostrar en el paginador (None representa una elipsis)."""
    if total <= 7:
        return list(range(1, total + 1))
    paginas = {1, total}
    for p in range(actual - margen, actual + margen + 1):
        if 1 <= p <= total:
            paginas.add(p)
    ordenadas = sorted(paginas)
    resultado = []
    anterior = None
    for p in ordenadas:
        if anterior is not None and p - anterior > 1:
            resultado.append(None)
        resultado.append(p)
        anterior = p
    return resultado


@app.route("/admin/citas")
@admin_required
def admin_citas():
    # ── Parámetros de paginación y filtros ──
    def _int_arg(nombre, defecto):
        try:
            return int(request.args.get(nombre, defecto))
        except (TypeError, ValueError):
            return defecto

    page = max(_int_arg("page", 1), 1)
    per_page = min(max(_int_arg("per_page", 10), 1), 100)
    estado = (request.args.get("estado") or "todos").strip().lower()
    q = (request.args.get("q") or "").strip()
    hoy = date.today()

    # ── Filtros → cláusula WHERE con parámetros ──
    condiciones = []
    params = []
    if estado == "pendiente":
        condiciones.append("c.estado = %s"); params.append("pendiente")
    elif estado == "confirmada":
        condiciones.append("c.estado = %s"); params.append("confirmada")
    elif estado == "cancelada":
        condiciones.append("c.estado = %s"); params.append("cancelada")
    elif estado == "atendida":
        condiciones.append("c.estado IN ('atendida', 'atendido', 'completada')")
    elif estado == "por_verificar":
        condiciones.append("c.estado_pago = %s"); params.append("pendiente_verificacion")
    elif estado == "hoy":
        condiciones.append("c.fecha = %s"); params.append(hoy)

    if q:
        like = f"%{q}%"
        condiciones.append("""(
            u.nombre ILIKE %s OR u.apepaterno ILIKE %s OR u.apematerno ILIKE %s
            OR e.nombre ILIKE %s OR c.tipo_atencion ILIKE %s
            OR CAST(c.id AS TEXT) ILIKE %s
            OR EXISTS (
                SELECT 1 FROM cita_tratamiento ct2
                JOIN tratamientos t2 ON t2.id_tratamiento = ct2.id_tratamiento
                WHERE ct2.id_cita = c.id AND t2.nombre ILIKE %s
            )
        )""")
        params.extend([like] * 7)

    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    conn = get_connection()
    cursor = conn.cursor()

    # ── Total de citas que cumplen los filtros (para las páginas) ──
    cursor.execute(f"""
        SELECT COUNT(*) AS total
        FROM citas c
        JOIN usuarios u ON c.paciente_id = u.id
        JOIN especialidades e ON c.especialidad_id = e.id
        {where}
    """, params)
    total = cursor.fetchone()["total"]

    total_paginas = max(ceil(total / per_page), 1)
    page = min(max(page, 1), total_paginas)
    offset = (page - 1) * per_page

    # ── Página solicitada (LIMIT / OFFSET) ──
    cursor.execute(f"""
        SELECT c.id,
            TRIM(CONCAT_WS(' ', u.nombre, u.apepaterno, u.apematerno)) AS paciente,
            e.nombre AS especialidad,
            c.fecha, c.hora, c.estado, c.estado_pago, c.comprobante,
            c.tipo_atencion, c.adelanto, c.nro_operacion, c.voucher_url, c.metodo_pago,
            c.created_at,
            (
                SELECT t.nombre
                FROM cita_tratamiento ct
                JOIN tratamientos t ON t.id_tratamiento = ct.id_tratamiento
                WHERE ct.id_cita = c.id
                ORDER BY ct.id
                LIMIT 1
            ) AS tratamiento
        FROM citas c
        JOIN usuarios u ON c.paciente_id = u.id
        JOIN especialidades e ON c.especialidad_id = e.id
        {where}
        -- Orden por la fecha en que el paciente AGENDÓ la cita (no la de
        -- atención): lo más reciente primero, así lo agendado hoy queda arriba.
        ORDER BY c.created_at DESC NULLS LAST, c.id DESC
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])

    citas = [dict(c) for c in cursor.fetchall()]

    # ── KPIs globales (independientes de filtros y paginación) ──
    cursor.execute("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE estado = 'pendiente') AS pendientes,
               COUNT(*) FILTER (WHERE estado = 'confirmada') AS confirmadas,
               COUNT(*) FILTER (WHERE fecha = %s) AS hoy,
               COUNT(*) FILTER (WHERE estado_pago = 'pendiente_verificacion') AS por_verificar
        FROM citas
    """, (hoy,))
    kpi = cursor.fetchone()
    conn.close()

    for c in citas:
        # Fecha en que el paciente AGENDÓ la cita (registro), no la de atención.
        creada = c.get("created_at")
        c["agendada"] = creada.date() if creada else c["fecha"]
        # La cita se atiende hoy (para el KPI y el resaltado de la fila).
        c["es_hoy"] = (c["fecha"] == hoy)
        c["por_verificar"] = (c["estado_pago"] == "pendiente_verificacion")

    # Agrupar por la fecha en que se agendó la cita. Ya vienen ordenadas de la
    # más reciente a la más antigua (ORDER BY created_at DESC).
    grupos = []
    for c in citas:
        clave = c["agendada"]
        if not grupos or grupos[-1]["fecha"] != clave:
            grupos.append({
                "fecha": clave,
                "etiqueta": _etiqueta_fecha(clave, hoy),
                "es_hoy": clave == hoy,
                "citas": [],
            })
        grupos[-1]["citas"].append(c)

    rango_inicio = offset + 1 if total else 0
    rango_fin = min(offset + per_page, total)

    return render_template(
        "admin_citas.html",
        citas=citas, grupos=grupos,
        # Paginación
        page=page, per_page=per_page, total=total, total_paginas=total_paginas,
        rango_inicio=rango_inicio, rango_fin=rango_fin,
        rango_paginas=_rango_paginas(page, total_paginas),
        estado=estado, q=q,
        # KPIs globales
        total_citas=kpi["total"], kpi_pendientes=kpi["pendientes"],
        kpi_confirmadas=kpi["confirmadas"], citas_hoy=kpi["hoy"],
        por_verificar=kpi["por_verificar"])

@app.route("/admin/enviar_recordatorios")
@admin_required
def admin_enviar_recordatorios():
    from recordatorios import enviar_recordatorios
    try:
        enviar_recordatorios()
        flash("Recordatorios enviados correctamente", "success")
    except Exception as e:
        flash(f"Error al enviar recordatorios: {e}", "danger")
    return redirect(url_for("admin_citas"))

@app.route("/admin/recordatorios")
@admin_required
def admin_recordatorios():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.dias_antes, r.enviado,
               u.nombre, u.apePaterno, u.apeMaterno, u.correo,
               e.nombre AS especialidad, c.fecha, c.hora
        FROM recordatorios r
        JOIN citas c ON r.cita_id = c.id
        JOIN usuarios u ON c.paciente_id = u.id
        JOIN especialidades e ON c.especialidad_id = e.id
        ORDER BY r.enviado DESC
    """)

    recordatorios = cursor.fetchall()
    conn.close()

    return render_template("admin_recordatorios.html", recordatorios=recordatorios)

@app.route("/admin/eliminar/<int:id>")
@admin_required
def eliminar_cita(id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM citas WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    _log_auditoria("eliminar_cita", detalle=f"cita #{id}")

    return redirect(url_for("admin_citas"))

@app.route("/admin/editar/<int:id>", methods=["GET", "POST"])
@admin_required
def editar_cita(id):

    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        fecha = request.form["fecha"]
        hora = request.form["hora"]
        estado = request.form["estado"]

        cursor.execute("""
            UPDATE citas 
            SET fecha=%s, hora=%s, estado=%s
            WHERE id=%s
        """, (fecha, hora, estado, id))

        conn.commit()
        conn.close()
        _log_auditoria("editar_cita", detalle=f"cita #{id}")

        return redirect(url_for("admin_citas"))

    cursor.execute("SELECT * FROM citas WHERE id = %s", (id,))
    cita = cursor.fetchone()
    conn.close()

    return render_template("editar_cita.html", cita=cita)


@app.route("/admin/confirmar_pago/<int:id>")
@admin_required
def confirmar_pago(id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, c.adelanto, c.estado_pago, c.comprobante,
               c.nro_operacion, c.metodo_pago,
               c.fecha, c.hora, c.paciente_id,
               u.nombre, u.apePaterno, u.apeMaterno, u.correo,
               e.nombre AS especialidad
        FROM citas c
        JOIN usuarios u ON u.id = c.paciente_id
        JOIN especialidades e ON e.id = c.especialidad_id
        WHERE c.id = %s
    """, (id,))
    cita = cursor.fetchone()

    if not cita:
        conn.close()
        flash("❌ Cita no encontrada", "danger")
        return redirect(url_for("admin_citas"))

    adelanto = float(cita["adelanto"] or 0) or 20.00

    cursor.execute("""
        UPDATE citas
        SET adelanto = %s, estado = 'confirmada', estado_pago = 'pagado',
            metodo_pago = COALESCE(metodo_pago, 'yape_manual')
        WHERE id = %s
    """, (adelanto, id))

    cursor.execute("""
        INSERT INTO pagos (id_cita, monto, tipo, gateway, payload, estado)
        VALUES (%s, %s, 'adelanto', 'yape_manual', %s, 'valido')
    """, (id, adelanto, cita["nro_operacion"]))
    conn.commit()
    conn.close()
    _log_auditoria("aprobar_pago", detalle=f"cita #{id}")

    try:
        nombre_pac = f"{cita['nombre']} {cita['apepaterno']} {cita['apematerno']}".strip()
        if cita["correo"]:
            enviar_confirmacion_cita(
                destinatario=cita["correo"],
                nombre_paciente=nombre_pac,
                especialidad=cita["especialidad"],
                fecha=str(cita["fecha"]),
                hora=str(cita["hora"])[:5],
            )
    except Exception as e:
        logger.error(f"Error al enviar confirmacion de pago: {e}")

    flash(f"✅ Pago de S/ {adelanto:.2f} confirmado y cita confirmada", "success")
    return redirect(url_for("admin_citas"))


                                                      
                            
                                                      

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    hoy = date.today()
    lunes = hoy - timedelta(days=hoy.weekday())
    inicio_mes = hoy.replace(day=1)

    conn = get_connection()
    cur = conn.cursor()

                
    cur.execute("SELECT COALESCE(COUNT(*),0) AS n FROM citas WHERE fecha = %s AND estado <> 'cancelada'", (hoy,))
    citas_hoy = cur.fetchone()["n"]

    cur.execute("SELECT COALESCE(COUNT(*),0) AS n FROM citas WHERE fecha BETWEEN %s AND %s AND estado <> 'cancelada'",
                (lunes, lunes + timedelta(days=6)))
    citas_semana = cur.fetchone()["n"]

    cur.execute("SELECT COALESCE(COUNT(*),0) AS n FROM usuarios WHERE id_rol = 2 AND fecha_registro >= %s", (inicio_mes,))
    pacientes_nuevos = cur.fetchone()["n"]

    cur.execute("""
        SELECT COALESCE(SUM(adelanto),0) AS total
        FROM citas WHERE fecha BETWEEN %s AND %s AND estado_pago <> 'pendiente'
    """, (inicio_mes, hoy))
    ingresos_mes = float(cur.fetchone()["total"])

                        
    cur.execute("""
        SELECT c.id, c.hora, c.estado, u.nombre AS paciente, e.nombre AS servicio
        FROM citas c
        JOIN usuarios u ON c.paciente_id = u.id
        JOIN especialidades e ON c.especialidad_id = e.id
        WHERE c.fecha = %s AND c.estado <> 'cancelada'
        ORDER BY c.hora
    """, (hoy,))
    citas_hoy_lista = cur.fetchall()

                                                 
    cur.execute("""
        SELECT fecha, COUNT(*) AS n FROM citas
        WHERE fecha BETWEEN %s AND %s AND estado <> 'cancelada'
        GROUP BY fecha
    """, (lunes - timedelta(days=7), lunes + timedelta(days=6)))
    por_fecha = {r["fecha"]: r["n"] for r in cur.fetchall()}

    citas_actual = [por_fecha.get(lunes + timedelta(days=d), 0) for d in range(7)]
    citas_pasado = [por_fecha.get(lunes - timedelta(days=7) + timedelta(days=d), 0) for d in range(7)]

                                              
    cur.execute("""
        SELECT e.nombre AS nombre, COUNT(*) AS n
        FROM citas c JOIN especialidades e ON c.especialidad_id = e.id
        WHERE c.fecha BETWEEN %s AND %s AND c.estado <> 'cancelada'
        GROUP BY e.nombre ORDER BY n DESC LIMIT 4
    """, (inicio_mes, hoy))
    top_esp = cur.fetchall()
    total_tratamientos = sum(r["n"] for r in top_esp)
    colores = ["#0a7c6e", "#c9a84c", "#3b7dd8", "#e05252"]
    esp_donut = []
    for i, r in enumerate(top_esp):
        pct = round(r["n"] * 100 / total_tratamientos, 1) if total_tratamientos else 0
        esp_donut.append({
            "nombre": r["nombre"],
            "pct": pct,
            "color": colores[i % 4],
            "id": f"d{i + 1}"
        })

                                           
    cur.execute("""
        SELECT e.nombre AS nombre, COALESCE(SUM(c.adelanto),0) AS total
        FROM citas c JOIN especialidades e ON c.especialidad_id = e.id
        WHERE c.fecha BETWEEN %s AND %s AND c.estado_pago <> 'pendiente'
        GROUP BY e.nombre ORDER BY total DESC LIMIT 4
    """, (inicio_mes, hoy))
    top_ing = cur.fetchall()
    ing_max = max((float(r["total"]) for r in top_ing), default=1)
    ingresos_lista = [{
        "nombre": r["nombre"],
        "val": f"S/ {float(r['total']):,.0f}".replace(",", " "),
        "pct": round(float(r["total"]) * 100 / ing_max) if ing_max else 0
    } for r in top_ing]

    conn.close()

    return render_template("admin_dashboard.html",
                           citas_hoy=citas_hoy,
                           citas_semana=citas_semana,
                           pacientes_nuevos=pacientes_nuevos,
                           ingresos_mes=ingresos_mes,
                           citas_hoy_lista=citas_hoy_lista,
                           dias_labels=["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
                           citas_actual=citas_actual,
                           citas_pasado=citas_pasado,
                           esp_donut=esp_donut,
                           total_tratamientos=total_tratamientos,
                           ingresos_lista=ingresos_lista)


@app.route("/admin/pacientes")
@admin_required
def admin_pacientes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.tipo_documento, u.numero_documento, u.nombre,
               u.apepaterno, u.apematerno, u.correo, u.estado, u.fecha_registro,
               COUNT(c.id) AS total_citas,
               COUNT(c.id) FILTER (WHERE c.estado NOT IN ('cancelada', 'cancelado')) AS citas_activas
        FROM usuarios u
        LEFT JOIN citas c ON c.paciente_id = u.id
        WHERE u.id_rol = 2
        GROUP BY u.id
        ORDER BY u.fecha_registro DESC
    """)
    pacientes = cur.fetchall()
    conn.close()
    return render_template("admin_pacientes.html", pacientes=pacientes, active="pacientes")


@app.route("/admin/paciente/<int:id>/estado")
@admin_required
def admin_paciente_estado(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT estado FROM usuarios WHERE id = %s", (id,))
    u = cur.fetchone()
    if u:
        nuevo = "INACTIVO" if u["estado"] == "ACTIVO" else "ACTIVO"
        cur.execute("UPDATE usuarios SET estado = %s WHERE id = %s", (nuevo, id))
        conn.commit()
        flash(f"Estado del paciente actualizado a {nuevo}", "success")
    conn.close()
    return redirect(url_for("admin_pacientes"))


@app.route("/admin/tratamientos")
@admin_required
def admin_tratamientos():
    """Listado de tratamientos (con su especialidad) para el panel admin."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
    especialidades = cur.fetchall()

    cur.execute("""
        SELECT t.id_tratamiento, t.nombre, t.descripcion, t.precio_base,
               t.adelanto, t.duracion_minutos, t.activo,
               e.id AS especialidad_id, e.nombre AS especialidad
        FROM tratamientos t
        JOIN especialidades e ON t.id_especialidad = e.id
        ORDER BY e.nombre, t.nombre
    """)
    tratamientos = cur.fetchall()

    cur.execute("""
        SELECT e.id, e.nombre, e.descripcion, e.estado, e.adelanto,
               COUNT(t.id_tratamiento) AS n_tratamientos
        FROM especialidades e LEFT JOIN tratamientos t ON t.id_especialidad = e.id
        GROUP BY e.id ORDER BY e.nombre
    """)
    lista_especialidades = cur.fetchall()

    conn.close()
    return render_template("admin_tratamientos.html",
                           especialidades=especialidades,
                           tratamientos=tratamientos,
                           lista_especialidades=lista_especialidades)


@app.route("/admin/tratamientos/guardar", methods=["POST"])
@admin_required
def admin_tratamiento_guardar():
    """Crea o actualiza un tratamiento. El campo `id` es opcional (edición)."""
    id_tratamiento = (request.form.get("id") or "").strip()
    nombre = (request.form.get("nombre") or "").strip()
    especialidad_id = (request.form.get("especialidad_id") or "").strip()
    descripcion = (request.form.get("descripcion") or "").strip()
    precio = _monto_form(request.form.get("precio_estimado"))
    adelanto = _monto_form(request.form.get("adelanto"))
    duracion_raw = (request.form.get("duracion_minutos") or "").strip()
    duracion = int(duracion_raw) if duracion_raw.isdigit() else None
    activo = request.form.get("activo") in ("on", "true", "1", "True")

    if not (nombre and especialidad_id.isdigit()):
        flash("El nombre y la especialidad son obligatorios", "danger")
        return redirect(url_for("admin_tratamientos"))

    conn = get_connection()
    cur = conn.cursor()
    try:
        if id_tratamiento.isdigit():
            cur.execute("""
                UPDATE tratamientos
                SET id_especialidad = %s, nombre = %s, descripcion = %s,
                    precio_base = %s, adelanto = %s,
                    duracion_minutos = %s, activo = %s
                WHERE id_tratamiento = %s
            """, (especialidad_id, nombre, descripcion or None, precio,
                  adelanto, duracion, activo, id_tratamiento))
            flash("Tratamiento actualizado", "success")
        else:
            cur.execute("""
                INSERT INTO tratamientos
                    (id_especialidad, nombre, descripcion, precio_base,
                     adelanto, duracion_minutos, activo)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (especialidad_id, nombre, descripcion or None, precio,
                  adelanto, duracion, activo))
            flash("Tratamiento registrado", "success")
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f"Error al guardar el tratamiento: {e}", "danger")
    conn.close()
    return redirect(url_for("admin_tratamientos"))


@app.route("/admin/tratamientos/estado/<int:id>", methods=["POST"])
@admin_required
def admin_tratamiento_estado(id):
    """Alterna el estado activo/inactivo de un tratamiento (soft delete)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE tratamientos SET activo = NOT COALESCE(activo, TRUE)
            WHERE id_tratamiento = %s
            RETURNING activo
        """, (id,))
        fila = cur.fetchone()
        conn.commit()
        if fila is None:
            flash("Tratamiento no encontrado", "danger")
        elif fila["activo"]:
            flash("Tratamiento activado", "success")
        else:
            flash("Tratamiento desactivado", "success")
    except Exception as e:
        conn.rollback()
        flash(f"No se pudo cambiar el estado del tratamiento: {e}", "danger")
    conn.close()
    return redirect(url_for("admin_tratamientos"))


@app.route("/admin/tratamientos/especialidad", methods=["POST"])
@admin_required
def admin_especialidad_guardar():
    """Registra una especialidad o actualiza su adelanto por defecto."""
    accion = request.form.get("accion")
    conn = get_connection()
    cur = conn.cursor()

    if accion == "especialidad":
        nombre = (request.form.get("nombre") or "").strip()
        descripcion = (request.form.get("descripcion") or "").strip()
        adelanto = _monto_form(request.form.get("adelanto")) or 0
        if nombre:
            cur.execute("""
                INSERT INTO especialidades (nombre, descripcion, adelanto)
                VALUES (%s, %s, %s)
                ON CONFLICT (nombre) DO UPDATE SET adelanto = EXCLUDED.adelanto
            """, (nombre, descripcion, adelanto))
            conn.commit()
            flash("Especialidad registrada", "success")
        else:
            flash("Debes indicar el nombre de la especialidad", "danger")

    elif accion == "editar_adelanto":
        objetivo = request.form.get("objetivo")
        ref_id = request.form.get("ref_id")
        adelanto = _monto_form(request.form.get("adelanto")) or 0
        if objetivo == "especialidad" and ref_id:
            cur.execute(
                "UPDATE especialidades SET adelanto = %s WHERE id = %s",
                (adelanto, ref_id),
            )
            conn.commit()
            flash("Adelanto de la especialidad actualizado", "success")
        elif objetivo == "tratamiento" and ref_id:
            cur.execute(
                "UPDATE tratamientos SET adelanto = %s WHERE id_tratamiento = %s",
                (adelanto, ref_id),
            )
            conn.commit()
            flash("Adelanto del tratamiento actualizado", "success")
        else:
            flash("No se pudo actualizar el adelanto", "danger")

    conn.close()
    return redirect(url_for("admin_tratamientos"))


@app.route("/tratamientos_por_especialidad")
@login_required
def tratamientos_por_especialidad():
    """Tratamientos activos de una especialidad (para el formulario de reserva)."""
    especialidad_id = (request.args.get("especialidad_id") or "").strip()
    if not especialidad_id.isdigit():
        return jsonify([])

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id_tratamiento AS id, nombre
        FROM tratamientos
        WHERE id_especialidad = %s AND COALESCE(activo, TRUE) = TRUE
        ORDER BY nombre
    """, (especialidad_id,))
    tratamientos = [dict(t) for t in cur.fetchall()]
    conn.close()
    return jsonify(tratamientos)


@app.route("/api/doctores-por-especialidad/<int:id_especialidad>")
@login_required
def doctores_por_especialidad(id_especialidad):
    """Odontólogos activos habilitados para una especialidad (para reserva).

    La relación se guarda en `odontologo_especialidad` (odontologo_id,
    especialidad_id). Los odontólogos son usuarios con rol 'odontologo'
    o 'dentista'.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT u.id, u.nombre, u.apepaterno, u.apematerno
        FROM odontologo_especialidad oe
        JOIN usuarios u ON u.id = oe.odontologo_id
        JOIN roles r    ON r.id = u.id_rol
        WHERE oe.especialidad_id = %s
          AND COALESCE(oe.estado, 'activo') = 'activo'
          AND u.estado = 'ACTIVO'
          AND r.nombre IN ('odontologo', 'dentista')
        ORDER BY u.nombre, u.apepaterno
    """, (id_especialidad,))
    filas = cur.fetchall()
    conn.close()

    doctores = []
    for f in filas:
        partes = [f["nombre"], f["apepaterno"], f["apematerno"]]
        completo = " ".join((p or "").strip().title() for p in partes if p and p.strip())
        doctores.append({"id": f["id"], "nombre": f"Dr. {completo}".strip()})
    return jsonify(doctores)


@app.route("/admin/tratamiento/eliminar/<int:id>")
@admin_required
def eliminar_tratamiento(id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM tratamientos WHERE id_tratamiento = %s", (id,))
        conn.commit()
        flash("Tratamiento eliminado", "success")
    except Exception as e:
        conn.rollback()
        flash(f"No se pudo eliminar el tratamiento: {e}", "danger")
    conn.close()
    return redirect(url_for("admin_tratamientos"))


@app.route("/admin/facturacion")
@admin_required
def admin_facturacion():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.tipo, p.monto, p.fecha, u.nombre AS paciente,
               e.nombre AS especialidad, c.fecha AS fecha_cita,
               COALESCE(mp.nombre, p.gateway, 'Yape') AS metodo
        FROM pagos p
        JOIN citas c ON p.id_cita = c.id
        JOIN usuarios u ON c.paciente_id = u.id
        JOIN especialidades e ON c.especialidad_id = e.id
        LEFT JOIN comprobantes_pago cp ON cp.id_pago = p.id
        LEFT JOIN metodos_pago mp ON mp.id_metodo_pago = cp.id_metodo_pago
        ORDER BY p.fecha DESC
    """)
    pagos_lista = cur.fetchall()
    total_pagado = sum(float(r["monto"]) for r in pagos_lista)

    cur.execute("""
        SELECT c.id, u.nombre AS paciente, e.nombre AS especialidad,
               c.fecha, c.hora, c.adelanto, c.estado_pago, c.comprobante,
               c.tipo_atencion, c.nro_operacion, c.voucher_url, c.metodo_pago
        FROM citas c
        JOIN usuarios u ON c.paciente_id = u.id
        JOIN especialidades e ON c.especialidad_id = e.id
        WHERE c.adelanto > 0 OR c.comprobante IS NOT NULL OR c.voucher_url IS NOT NULL
        ORDER BY c.fecha DESC
    """)
    adelantos = cur.fetchall()
    total_adelantos = sum(float(r["adelanto"]) for r in adelantos)

    conn.close()
    return render_template("admin_facturacion.html",
                           pagos_lista=pagos_lista,
                           total_pagado=total_pagado,
                           adelantos=adelantos,
                           total_adelantos=total_adelantos)


@app.route("/admin/personal")
@admin_required
def admin_personal():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT u.id, u.nombre, u.apepaterno, u.apematerno, u.correo,
               u.tipo_documento, u.numero_documento, u.estado,
               ARRAY(
                   SELECT e.nombre FROM odontologo_especialidad oe
                   JOIN especialidades e ON oe.especialidad_id = e.id
                   WHERE oe.odontologo_id = u.id
               ) AS especialidades
        FROM usuarios u
        WHERE u.id IN (
            SELECT DISTINCT odontologo_id FROM citas WHERE odontologo_id IS NOT NULL
            UNION SELECT DISTINCT odontologo_id FROM horarios WHERE odontologo_id IS NOT NULL
            UNION SELECT DISTINCT odontologo_id FROM odontologo_especialidad WHERE odontologo_id IS NOT NULL
        )
        ORDER BY u.nombre
    """)
    personal = cur.fetchall()
    conn.close()
    return render_template("admin_personal.html", personal=personal)


@app.route("/admin/inventario", methods=["GET", "POST"])
@admin_required
def admin_inventario():
    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        accion = request.form.get("accion")

        if accion == "agregar":
            nombre = request.form.get("nombre", "").strip()
            if nombre:
                try:
                    cur.execute("""
                        INSERT INTO inventario (nombre, categoria, cantidad, stock_minimo, precio_compra, proveedor)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        nombre,
                        request.form.get("categoria", "").strip() or None,
                        request.form.get("cantidad") or 0,
                        request.form.get("stock_minimo") or 0,
                        request.form.get("precio_compra") or None,
                        request.form.get("proveedor", "").strip() or None,
                    ))
                    conn.commit()
                    flash("Producto agregado al inventario", "success")
                except Exception as e:
                    conn.rollback()
                    flash(f"Error al agregar producto: {e}", "danger")
            else:
                flash("El nombre del producto es obligatorio", "danger")

        elif accion == "actualizar":
            try:
                cur.execute("""
                    UPDATE inventario SET cantidad = %s, stock_minimo = %s
                    WHERE id = %s
                """, (request.form.get("cantidad") or 0,
                      request.form.get("stock_minimo") or 0,
                      request.form.get("id")))
                conn.commit()
                flash("Stock actualizado", "success")
            except Exception as e:
                conn.rollback()
                flash(f"Error al actualizar stock: {e}", "danger")

        conn.close()
        return redirect(url_for("admin_inventario"))

    cur.execute("SELECT * FROM inventario ORDER BY nombre")
    inventario = cur.fetchall()

    cur.execute("SELECT COALESCE(SUM(cantidad),0) AS total FROM inventario")
    total_items = cur.fetchone()["total"]
    cur.execute("SELECT COALESCE(SUM(cantidad * precio_compra),0) AS total FROM inventario WHERE precio_compra IS NOT NULL")
    valor_stock = float(cur.fetchone()["total"])
    cur.execute("SELECT COUNT(*) AS n FROM inventario WHERE cantidad <= stock_minimo")
    stock_bajo = cur.fetchone()["n"]

    conn.close()
    return render_template("admin_inventario.html",
                           inventario=inventario,
                           total_items=total_items,
                           valor_stock=valor_stock,
                           stock_bajo=stock_bajo)


@app.route("/admin/inventario/eliminar/<int:id>")
@admin_required
def eliminar_inventario(id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM inventario WHERE id = %s", (id,))
        conn.commit()
        flash("Producto eliminado", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error al eliminar producto: {e}", "danger")
    conn.close()
    return redirect(url_for("admin_inventario"))


@app.route("/admin/reportes")
@admin_required
def admin_reportes():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COALESCE(estado,'sin estado') AS estado, COUNT(*) AS n FROM citas GROUP BY estado ORDER BY n DESC")
    citas_por_estado = cur.fetchall()

    cur.execute("""
        SELECT to_char(fecha, 'YYYY-MM') AS mes, COUNT(*) AS n
        FROM citas
        WHERE fecha >= date_trunc('month', CURRENT_DATE) - (INTERVAL '5 months')
        GROUP BY mes ORDER BY mes
    """)
    citas_por_mes = cur.fetchall()

    cur.execute("""
        SELECT e.nombre AS nombre, COUNT(c.id) AS citas, COALESCE(SUM(c.adelanto),0) AS ingreso
        FROM especialidades e
        LEFT JOIN citas c ON c.especialidad_id = e.id
        GROUP BY e.nombre ORDER BY ingreso DESC, citas DESC
    """)
    ingresos_por_especialidad = cur.fetchall()

    cur.execute("""
        SELECT to_char(fecha_registro, 'YYYY-MM') AS mes, COUNT(*) AS n
        FROM usuarios
        WHERE id_rol = 2 AND fecha_registro >= date_trunc('month', CURRENT_DATE) - (INTERVAL '5 months')
        GROUP BY mes ORDER BY mes
    """)
    pacientes_por_mes = cur.fetchall()

    cur.execute("SELECT COALESCE(COUNT(*),0) AS n FROM citas")
    total_citas = cur.fetchone()["n"]
    cur.execute("SELECT COALESCE(COUNT(*),0) AS n FROM usuarios WHERE id_rol = 2")
    total_pacientes = cur.fetchone()["n"]
    cur.execute("SELECT COALESCE(SUM(adelanto),0) AS total FROM citas WHERE estado_pago <> 'pendiente'")
    total_ingresos = float(cur.fetchone()["total"])

    conn.close()
    return render_template("admin_reportes.html",
                           citas_por_estado=citas_por_estado,
                           citas_por_mes=citas_por_mes,
                           ingresos_por_especialidad=ingresos_por_especialidad,
                           pacientes_por_mes=pacientes_por_mes,
                           total_citas=total_citas,
                           total_pacientes=total_pacientes,
                           total_ingresos=total_ingresos)


FORMULAS_KPI = {
    "Tasa de asistencia": "atendidas / (atendidas + canceladas) x 100",
    "Tasa de cancelación": "canceladas / total citas x 100",
    "Tasa de conversión": "confirmadas / total citas x 100",
    "Ticket promedio": "ingresos validos / citas con pago",
    "Ingreso por paciente": "ingresos totales / pacientes activos",
    "Tasa de nuevos pacientes": "pacientes nuevos del mes / pacientes activos x 100",
}


@app.route("/admin/kpis")
@admin_required
def admin_kpis():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) AS n FROM citas
        WHERE estado IN ('atendida', 'atendido', 'completada')
    """)
    atendidas = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM usuarios WHERE id_rol = 2")
    pacientes_totales = cur.fetchone()["n"]

    cur.execute("SELECT COALESCE(SUM(monto),0) AS t FROM pagos WHERE estado = 'valido'")
    ingresos_totales = float(cur.fetchone()["t"])

    cur.execute("""
        SELECT COUNT(*) AS n
        FROM cita_tratamiento ct
        JOIN citas c ON c.id = ct.id_cita
        WHERE c.estado IN ('atendida', 'atendido', 'completada')
    """)
    tratamientos_realizados = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM citas")
    total_citas = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM citas WHERE estado = 'cancelada'")
    canceladas = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM citas WHERE estado = 'confirmada'")
    confirmadas = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM citas WHERE estado_pago <> 'pendiente'")
    citas_con_pago = cur.fetchone()["n"]

    cur.execute("""
        SELECT COUNT(*) AS n FROM usuarios
        WHERE id_rol = 2
          AND date_trunc('month', fecha_registro) = date_trunc('month', CURRENT_DATE)
    """)
    nuevos_mes = cur.fetchone()["n"]

    finalizadas = atendidas + canceladas
    tasa_asistencia = (atendidas / finalizadas * 100) if finalizadas else 0
    tasa_cancelacion = (canceladas / total_citas * 100) if total_citas else 0
    tasa_conversion = (confirmadas / total_citas * 100) if total_citas else 0
    ticket_promedio = (ingresos_totales / citas_con_pago) if citas_con_pago else 0
    ingreso_paciente = (ingresos_totales / pacientes_totales) if pacientes_totales else 0
    tasa_nuevos = (nuevos_mes / pacientes_totales * 100) if pacientes_totales else 0

    valores = {
        "Tasa de asistencia": (tasa_asistencia, True),
        "Tasa de cancelación": (tasa_cancelacion, False),
        "Tasa de conversión": (tasa_conversion, True),
        "Ticket promedio": (ticket_promedio, True),
        "Ingreso por paciente": (ingreso_paciente, True),
        "Tasa de nuevos pacientes": (tasa_nuevos, True),
    }

    cur.execute("""
        SELECT objetivo, nombre_kpi, descripcion, meta, unidad
        FROM metas_kpi WHERE estado = 'activo' ORDER BY id
    """)
    filas = cur.fetchall()
    conn.close()

    kpis = []
    for f in filas:
        nombre = f["nombre_kpi"]
        actual, mayor_mejor = valores.get(nombre, (0, True))
        meta = float(f["meta"] or 0)
        pct = round((actual / meta * 100) if meta else 0, 1)
        logrado = (actual >= meta) if mayor_mejor else (actual <= meta)
        kpis.append({
            "objetivo": f["objetivo"],
            "nombre": nombre,
            "descripcion": f["descripcion"],
            "formula": FORMULAS_KPI.get(nombre, ""),
            "unidad": f["unidad"] or "",
            "actual": round(actual, 2),
            "meta": meta,
            "pct": pct,
            "logrado": logrado,
        })

    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    hoy = date.today()
    mes_actual = f"{meses[hoy.month - 1].capitalize()} {hoy.year}"

    return render_template("admin_kpis.html",
                           atendidas=atendidas,
                           pacientes_totales=pacientes_totales,
                           ingresos_totales=ingresos_totales,
                           tratamientos_realizados=tratamientos_realizados,
                           mes_actual=mes_actual,
                           kpis=kpis)


@app.route("/admin/config", methods=["GET", "POST"])
@admin_required
def admin_config():
    env_path = os.path.join(app.root_path, ".env")

    if request.method == "POST":
        acciones = {
            "YAPE_NUMERO": request.form.get("yape_numero", "").strip(),
            "YAPE_NOMBRE": request.form.get("yape_nombre", "").strip(),
            "YAPE_QR": request.form.get("yape_qr", "").strip(),
        }
        for clave, valor in acciones.items():
            if valor:
                try:
                    set_key(env_path, clave, valor)
                except Exception as e:
                    flash(f"Error guardando {clave}: {e}", "danger")
        flash("Configuración guardada correctamente", "success")
        return redirect(url_for("admin_config"))

    config = dotenv_values(env_path)
    return render_template("admin_config.html",
                           yape_numero=config.get("YAPE_NUMERO", "946536766"),
                           yape_nombre=config.get("YAPE_NOMBRE", "Clinica Sele Dent"),
                           yape_qr=config.get("YAPE_QR", "static/img/QR.yape.jpeg"))


oauth = OAuth(app)


                                
load_dotenv()

                   
google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)
@app.route('/login/google')
def login_google():
    nonce = generate_token()
    session['nonce'] = nonce
    # Guardar el destino solicitado para volver tras el login con Google.
    session['oauth_next'] = request.args.get('next')

    return google.authorize_redirect(
        url_for('authorize_google', _external=True),
        nonce=nonce
    )

@app.route('/authorize/google')
def authorize_google():
                                                                   
    nonce = session.pop('nonce', None)
    # Destino solicitado antes de iniciar el flujo con Google.
    siguiente = session.pop('oauth_next', None)

    try:
        token = google.authorize_access_token()
        
                                                                                  
        if nonce:
            user = google.parse_id_token(token, nonce=nonce)
        else:
            user = google.parse_id_token(token)

        correo = (user['email'] or "").strip()
        nombre_google = (user.get('name') or correo.split('@')[0]).strip()

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT u.id, u.nombre, u.estado,
                   COALESCE(r.nombre, 'paciente') AS rol,
                   COALESCE(u.perfil_completo, TRUE) AS perfil_completo
            FROM usuarios u
            LEFT JOIN roles r ON u.id_rol = r.id
            WHERE LOWER(TRIM(u.correo)) = LOWER(TRIM(%s))
        """, (correo,))

        usuario_db = cursor.fetchone()

        # ---------- CASO B: usuario nuevo -> registro automático ----------
        if not usuario_db:
            partes = nombre_google.split()
            nombre = partes[0] if partes else correo.split('@')[0]
            apepaterno = partes[1] if len(partes) > 1 else None
            apematerno = " ".join(partes[2:]) if len(partes) > 2 else None

            # Contraseña aleatoria: la cuenta se gestiona vía Google.
            clave_aleatoria = bcrypt.generate_password_hash(generate_token(32)).decode("utf-8")

            cursor.execute("""
                INSERT INTO usuarios
                    (nombre, apepaterno, apematerno, correo, contrasenia,
                     id_rol, estado, perfil_completo)
                VALUES (%s, %s, %s, %s, %s, 2, 'ACTIVO', FALSE)
                RETURNING id, nombre
            """, (nombre, apepaterno, apematerno, correo, clave_aleatoria))
            nuevo = cursor.fetchone()
            conn.commit()
            conn.close()

            session['usuario_id'] = nuevo['id']
            session['rol'] = 'paciente'
            session['nombre'] = nuevo['nombre']

            flash("¡Bienvenido! Completa tu perfil para poder agendar tu primera cita.", "success")
            return redirect(url_for('completar_perfil', next=siguiente))

        # ---------- CASO A: usuario existente -> inicio de sesión ----------
        if usuario_db['estado'] != 'ACTIVO':
            conn.close()
            flash("❌ Tu cuenta está inactiva. Contacta con la clínica.", "danger")
            return redirect(url_for('login', next=siguiente))

        conn.close()

        session['usuario_id'] = usuario_db['id']
        session['rol']        = usuario_db['rol']
        session['nombre']     = usuario_db['nombre']

        if usuario_db['rol'] == 'admin':
            if siguiente and siguiente.startswith('/admin'):
                return redirect(siguiente)
            return redirect(url_for('admin_dashboard'))
        return redirect(_destino_seguro(siguiente, 'mis_citas'))

    except Exception as e:
        logger.exception("Error en la autenticación con Google")
        flash(f"Error durante la autenticación: {str(e)}", "danger")
        return redirect(url_for('login', next=siguiente))


def _token_decolecta():
    """Token de Decolecta (acepta DECOLECTA_TOKEN o DNI_API_TOKEN)."""
    return (os.getenv("DECOLECTA_TOKEN") or os.getenv("DNI_API_TOKEN") or "").strip()


def _normalizar_respuesta_dni(data, dni):
    """Normaliza la respuesta de Decolecta a (nombres, apePaterno, apeMaterno)."""
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

    # Fallback: derivar de full_name / nombre_completo si faltan campos.
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


def consultar_dni_api(dni):
    """Consulta un DNI en Decolecta.

    Devuelve (ok, payload, status_http) donde payload incluye los datos
    normalizados o un mensaje de error.
    """
    token = _token_decolecta()
    if not token:
        return False, {"message": "Consulta de DNI no configurada (falta el token)."}, 503

    try:
        respuesta = requests.get(
            DECOLECTA_API_URL,
            params={"numero": dni},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=8,
        )
    except requests.RequestException as e:
        logger.error("Decolecta: error de conexión al consultar %s: %s", dni, e)
        return False, {"message": "No se pudo conectar con el servicio de DNI."}, 502

    if respuesta.status_code == 200:
        try:
            data = respuesta.json()
        except ValueError:
            return False, {"message": "Respuesta inválida del servicio de DNI."}, 502

        nombres, ape_paterno, ape_materno = _normalizar_respuesta_dni(data, dni)
        if not nombres:
            return False, {"message": "No se encontraron datos para ese DNI."}, 404
        return True, {
            "dni": dni,
            "nombres": nombres,
            "apePaterno": ape_paterno,
            "apeMaterno": ape_materno,
            "nombreCompleto": " ".join(p for p in (nombres, ape_paterno, ape_materno) if p),
        }, 200

    if respuesta.status_code in (401, 403):
        logger.warning("Decolecta: token inválido o sin permisos (status %s)", respuesta.status_code)
        return False, {"message": "Token de Decolecta inválido o sin permisos."}, 502
    if respuesta.status_code == 404:
        return False, {"message": "DNI no encontrado en RENIEC."}, 404
    if respuesta.status_code == 429:
        return False, {"message": "Límite de consultas alcanzado. Intenta más tarde."}, 429

    logger.warning("Decolecta: respuesta inesperada %s para el DNI %s", respuesta.status_code, dni)
    return False, {"message": "Error al consultar el DNI."}, 502


@app.route("/api/consultar-dni/<dni>")
def consultar_dni(dni):
    """Consulta el DNI en Decolecta y devuelve nombres y apellidos."""
    dni = (dni or "").strip()
    if not re.fullmatch(r"\d{8}", dni):
        return jsonify({"success": False, "message": "El DNI debe tener 8 dígitos."}), 400

    ok, payload, status = consultar_dni_api(dni)
    if not ok:
        return jsonify({"success": False, "message": payload.get("message", "Error.")}), status

    return jsonify({"success": True, **payload}), 200


@app.route("/api/consultar_dni/<dni>")
def consultar_dni_legacy(dni):
    """Alias compatible con la ruta antigua (guion bajo)."""
    return consultar_dni(dni)


MAX_INTENTOS   = 5                                           
TIEMPO_BAN_MIN = 15                         
TIEMPO_VENTANA = 10                                                           

                                                 
                                                                                         
registro_ips = defaultdict(lambda: {
    "intentos":       0,
    "primer_intento": None,
    "baneado_hasta":  None
})


def esta_baneada(ip: str) -> tuple[bool, int]:
    """
    Verifica si una IP está baneada.
    Retorna (True, minutos_restantes) o (False, 0)
    """
    datos = registro_ips[ip]

    if datos["baneado_hasta"] is None:
        return False, 0

    ahora = datetime.now()
    if ahora < datos["baneado_hasta"]:
        restantes = int((datos["baneado_hasta"] - ahora).total_seconds() / 60) + 1
        return True, restantes

                            
    registro_ips[ip] = {"intentos": 0, "primer_intento": None, "baneado_hasta": None}
    return False, 0


def registrar_intento_fallido(ip: str) -> tuple[bool, int]:
    """
    Registra un intento fallido de login.
    Retorna (baneada_ahora, intentos_restantes)
    """
    datos  = registro_ips[ip]
    ahora  = datetime.now()
    ventana = timedelta(minutes=TIEMPO_VENTANA)

                                                      
    if datos["primer_intento"] and (ahora - datos["primer_intento"]) > ventana:
        datos["intentos"]       = 0
        datos["primer_intento"] = None

                                    
    if datos["primer_intento"] is None:
        datos["primer_intento"] = ahora

    datos["intentos"] += 1

                        
    if datos["intentos"] >= MAX_INTENTOS:
        datos["baneado_hasta"] = ahora + timedelta(minutes=TIEMPO_BAN_MIN)
        logger.info(f"[BAN] IP {ip} baneada hasta {datos['baneado_hasta']}")
        return True, 0

    restantes = MAX_INTENTOS - datos["intentos"]
    return False, restantes


def limpiar_ip(ip: str):
    registro_ips[ip] = {"intentos": 0, "primer_intento": None, "baneado_hasta": None}


def enviar_recordatorios_app():
    try:
        from recordatorios import enviar_recordatorios 
        enviar_recordatorios()
    except Exception as e:
        logger.exception(f"Error en el envio automatico de recordatorios: {e}")


def iniciar_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        enviar_recordatorios_app,
        trigger="cron",
        hour=8,
        minute=0,
        id="recordatorios_diarios",
        name="Enviar recordatorios de citas diariamente",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler de recordatorios iniciado (ejecucion diaria a las 08:00)")


def _asegurar_esquema_perfil():
    """Aplica (idempotente) las columnas requeridas por el perfil / Google OAuth."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telefono VARCHAR(30)")
        cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS direccion VARCHAR(255)")
        cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS perfil_completo BOOLEAN DEFAULT TRUE")
        cursor.execute("UPDATE usuarios SET perfil_completo = TRUE WHERE perfil_completo IS NULL")
        cursor.execute(
            "ALTER TABLE citas ADD COLUMN IF NOT EXISTS sede VARCHAR(150) "
            "DEFAULT 'Sede Principal - El Tambo, Huancayo'"
        )
        cursor.execute(
            "ALTER TABLE citas ADD COLUMN IF NOT EXISTS prioridad VARCHAR(30) "
            "DEFAULT 'Normal'"
        )
        cursor.execute(
            "ALTER TABLE especialidades ADD COLUMN IF NOT EXISTS adelanto "
            "NUMERIC(10,2) DEFAULT 0"
        )
        cursor.execute(
            "ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS adelanto NUMERIC(10,2)"
        )
        # --- Gestión de tratamientos: duración, estado (soft delete) y fecha ---
        cursor.execute(
            "ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS duracion_minutos INTEGER"
        )
        cursor.execute(
            "ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE"
        )
        cursor.execute(
            "ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS created_at "
            "TIMESTAMP DEFAULT NOW()"
        )
        cursor.execute(
            "UPDATE tratamientos SET activo = TRUE WHERE activo IS NULL"
        )
        cursor.execute("ALTER TABLE pagos ADD COLUMN IF NOT EXISTS gateway VARCHAR(20)")
        cursor.execute(
            "ALTER TABLE pagos ADD COLUMN IF NOT EXISTS transaccion_id VARCHAR(120)"
        )
        cursor.execute("ALTER TABLE pagos ADD COLUMN IF NOT EXISTS payload TEXT")
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_pagos_transaccion "
            "ON pagos (transaccion_id)"
        )
        cursor.execute(
            "ALTER TABLE citas ADD COLUMN IF NOT EXISTS adelanto NUMERIC(10,2) DEFAULT 0"
        )
        # --- Yape manual: datos del voucher y estado de verificación ---------
        cursor.execute(
            "ALTER TABLE citas ADD COLUMN IF NOT EXISTS nro_operacion VARCHAR(50)"
        )
        cursor.execute(
            "ALTER TABLE citas ADD COLUMN IF NOT EXISTS voucher_url TEXT"
        )
        cursor.execute(
            "ALTER TABLE citas ADD COLUMN IF NOT EXISTS metodo_pago VARCHAR(30)"
        )
        # 'pendiente_verificacion' (22 chars) excede VARCHAR(20): ampliar.
        cursor.execute(
            "ALTER TABLE citas ALTER COLUMN estado_pago TYPE VARCHAR(30)"
        )
        conn.commit()
        # El CHECK original no contemplaba 'pendiente_verificacion' ni el estado
        # 'rechazado' que ya existe en producción; se recrea admitiendo ambos.
        # Se aísla en su propio try para que un fallo aquí no revierta columnas.
        try:
            cursor.execute("""
                DO $$
                DECLARE c record;
                BEGIN
                    FOR c IN
                        SELECT conname FROM pg_constraint
                        WHERE conrelid = 'citas'::regclass AND contype = 'c'
                          AND pg_get_constraintdef(oid) LIKE '%estado_pago%'
                    LOOP
                        EXECUTE format('ALTER TABLE citas DROP CONSTRAINT %I', c.conname);
                    END LOOP;
                    ALTER TABLE citas ADD CONSTRAINT citas_estado_pago_check
                        CHECK (estado_pago IN (
                            'pendiente', 'adelanto', 'pagado',
                            'rechazado', 'pendiente_verificacion'
                        ));
                END $$;
            """)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"No se pudo actualizar el CHECK de estado_pago: {e}")
        conn.close()
        logger.info("Esquema verificado (perfil, citas y pagos)")
    except Exception as e:
        logger.error(f"No se pudo verificar el esquema de perfil: {e}")


_asegurar_esquema_perfil()


# ═══════════════════════════════════════════════════════════════
#  Funciones portadas de feature/mejoras-sistema
#  (auditoria, horarios, historial clinico, Google Calendar)
# ═══════════════════════════════════════════════════════════════


@app.route("/admin/validar_pago/<int:cita_id>", methods=["POST"])
@admin_required
def validar_pago(cita_id):
    accion = request.form.get("accion")

    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, estado_pago FROM citas WHERE id = %s", (cita_id,))
        cita = cur.fetchone()
        if not cita:
            flash("Cita no encontrada", "danger")
            return redirect(url_for("admin_facturacion"))

        if accion == "aprobar":
            cur.execute("UPDATE citas SET estado_pago = 'pagado', estado = 'confirmada' WHERE id = %s", (cita_id,))
            conn.commit()
            _log_auditoria("aprobar_pago", detalle=f"cita #{cita_id}")
            flash("Pago aprobado y cita confirmada", "success")
        elif accion == "rechazar":
            cur.execute("UPDATE citas SET estado_pago = 'pendiente', comprobante = NULL WHERE id = %s", (cita_id,))
            conn.commit()
            _log_auditoria("rechazar_pago", detalle=f"cita #{cita_id}")
            flash("Pago rechazado. El paciente debera subir un nuevo comprobante.", "warning")

    return redirect(url_for("admin_facturacion"))


@app.route("/admin/personal/crear", methods=["GET", "POST"])
@admin_required
def admin_crear_odontologo():
    with db_connection() as conn:
        cur = conn.cursor()

        if request.method == "POST":
            dni = request.form.get("dni", "").strip()
            nombre = request.form.get("nombre", "").strip()
            apepaterno = request.form.get("apepaterno", "").strip()
            apematerno = request.form.get("apematerno", "").strip()
            correo = request.form.get("correo", "").strip()
            especialidades_ids = request.form.getlist("especialidades")

            if not all([dni, nombre, apepaterno, correo]):
                flash("Completa todos los campos obligatorios", "danger")
                return redirect(url_for("admin_crear_odontologo"))

            try:
                cur.execute("""
                    INSERT INTO usuarios (tipo_documento, numero_documento, nombre,
                        apepaterno, apematerno, correo, contrasenia, id_rol, estado)
                    VALUES ('DNI', %s, %s, %s, %s, %s, %s, 3, 'ACTIVO')
                    RETURNING id
                """, (dni, nombre, apepaterno, apematerno or None, correo,
                      bcrypt.generate_password_hash(dni).decode("utf-8")))
                nuevo_id = cur.fetchone()["id"]

                for esp_id in especialidades_ids:
                    cur.execute("""
                        INSERT INTO odontologo_especialidad (odontologo_id, especialidad_id)
                        VALUES (%s, %s) ON CONFLICT DO NOTHING
                    """, (nuevo_id, esp_id))

                conn.commit()
                _log_auditoria("crear_odontologo", detalle=f"odontologo #{nuevo_id}")
                flash("Odontologo registrado correctamente", "success")
                return redirect(url_for("admin_personal"))
            except Exception:
                conn.rollback()
                flash("Error al registrar odontologo. Verifica que el DNI no este duplicado.", "danger")
                return redirect(url_for("admin_crear_odontologo"))

        cur.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
        especialidades = cur.fetchall()

    return render_template("admin_crear_odontologo.html", especialidades=especialidades)


@app.route("/admin/horarios", methods=["GET", "POST"])
@admin_required
def admin_horarios():
    with db_connection() as conn:
        cur = conn.cursor()

        if request.method == "POST":
            odontologo_id = request.form.get("odontologo_id")
            dia_semana = request.form.get("dia_semana")
            hora_inicio = request.form.get("hora_inicio")
            hora_fin = request.form.get("hora_fin")

            if not all([odontologo_id, dia_semana, hora_inicio, hora_fin]):
                flash("Completa todos los campos", "danger")
                return redirect(url_for("admin_horarios"))

            try:
                cur.execute("""
                    INSERT INTO horarios (odontologo_id, dia_semana, hora_inicio, hora_fin)
                    VALUES (%s, %s, %s, %s)
                """, (odontologo_id, dia_semana, hora_inicio, hora_fin))
                conn.commit()
                _log_auditoria("crear_horario", detalle=f"odontologo #{odontologo_id} - {dia_semana}")
                flash("Horario registrado", "success")
            except Exception:
                conn.rollback()
                flash("Error al registrar horario", "danger")
            return redirect(url_for("admin_horarios"))

        cur.execute("""
            SELECT h.*, u.nombre || ' ' || COALESCE(u.apepaterno,'') AS odontologo_nombre
            FROM horarios h
            JOIN usuarios u ON h.odontologo_id = u.id
            ORDER BY h.dia_semana, h.hora_inicio
        """)
        horarios = cur.fetchall()

        cur.execute("""
            SELECT u.id, u.nombre || ' ' || COALESCE(u.apepaterno,'') AS nombre
            FROM usuarios u
            WHERE u.id IN (SELECT DISTINCT odontologo_id FROM horarios)
               OR u.id IN (SELECT DISTINCT odontologo_id FROM odontologo_especialidad)
            ORDER BY u.nombre
        """)
        odontologos = cur.fetchall()

    return render_template("admin_horarios.html", horarios=horarios, odontologos=odontologos)


@app.route("/admin/horarios/eliminar/<int:id>", methods=["POST"])
@admin_required
def eliminar_horario(id):
    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM horarios WHERE id = %s", (id,))
        conn.commit()
    _log_auditoria("eliminar_horario", detalle=f"horario #{id}")
    flash("Horario eliminado", "success")
    return redirect(url_for("admin_horarios"))


@app.route("/admin/historial/<int:paciente_id>")
@admin_required
def admin_historial(paciente_id):
    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.nombre, u.apepaterno, u.apematerno, u.numero_documento, u.correo
            FROM usuarios u WHERE u.id = %s AND u.id_rol = 2
        """, (paciente_id,))
        paciente = cur.fetchone()

        if not paciente:
            flash("Paciente no encontrado", "danger")
            return redirect(url_for("admin_pacientes"))

        cur.execute("""
            SELECT c.id, e.nombre AS especialidad, c.fecha, c.hora, c.estado,
                   c.diagnostico, c.observaciones,
                   COALESCE(u2.nombre || ' ' || COALESCE(u2.apepaterno,''), 'Sin asignar') AS odontologo
            FROM citas c
            JOIN especialidades e ON c.especialidad_id = e.id
            LEFT JOIN usuarios u2 ON c.odontologo_id = u2.id
            WHERE c.paciente_id = %s
            ORDER BY c.fecha DESC
        """, (paciente_id,))
        historial_citas = cur.fetchall()

        cur.execute("""
            SELECT hc.id, hc.fecha, hc.diagnostico, hc.observaciones, hc.tratamiento,
                   e.nombre AS especialidad,
                   COALESCE(u.nombre || ' ' || COALESCE(u.apepaterno,''), '') AS odontologo
            FROM historial_clinico hc
            LEFT JOIN citas c ON hc.cita_id = c.id
            LEFT JOIN especialidades e ON c.especialidad_id = e.id
            LEFT JOIN usuarios u ON c.odontologo_id = u.id
            WHERE hc.paciente_id = %s
            ORDER BY hc.fecha DESC
        """, (paciente_id,))
        historial_clinico = cur.fetchall()

    return render_template("admin_historial.html", paciente=paciente,
                           historial_citas=historial_citas, historial_clinico=historial_clinico)


@app.route("/admin/historial/<int:paciente_id>/registrar", methods=["POST"])
@admin_required
def registrar_historial(paciente_id):
    diagnostico = request.form.get("diagnostico", "").strip()
    observaciones = request.form.get("observaciones", "").strip()
    tratamiento = request.form.get("tratamiento", "").strip()
    cita_id = request.form.get("cita_id") or None

    if not diagnostico:
        flash("El diagnostico es obligatorio", "danger")
        return redirect(url_for("admin_historial", paciente_id=paciente_id))

    with db_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO historial_clinico (paciente_id, cita_id, fecha, diagnostico, observaciones, tratamiento)
                VALUES (%s, %s, NOW(), %s, %s, %s)
            """, (paciente_id, cita_id, diagnostico, observaciones or None, tratamiento or None))
            conn.commit()
            _log_auditoria("registrar_historial", detalle=f"paciente #{paciente_id}")
            flash("Historial clinico registrado", "success")
        except Exception:
            conn.rollback()
            flash("Error al registrar historial", "danger")

    return redirect(url_for("admin_historial", paciente_id=paciente_id))


@app.route("/admin/auditoria")
@admin_required
def admin_auditoria():
    page = request.args.get("page", 1, type=int)
    per_page = 30
    offset = (page - 1) * per_page

    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM auditoria")
        total = cur.fetchone()["n"]
        total_pages = max(1, (total + per_page - 1) // per_page)

        cur.execute("""
            SELECT a.id, a.accion, a.detalle, a.ip, a.created_at,
                   COALESCE(u.nombre || ' ' || COALESCE(u.apepaterno,''), 'Sistema') AS usuario
            FROM auditoria a
            LEFT JOIN usuarios u ON a.usuario_id = u.id
            ORDER BY a.created_at DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        registros = cur.fetchall()

    return render_template("admin_auditoria.html", registros=registros, page=page, total_pages=total_pages)


# ── Google Calendar (integracion opcional; degrada si no hay credenciales) ──

def _get_calendar_service():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds_path = os.getenv("GOOGLE_CALENDAR_CREDENTIALS")
        if creds_path and os.path.exists(creds_path):
            creds = service_account.Credentials.from_service_account_file(
                creds_path,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            return build('calendar', 'v3', credentials=creds)

        from google.oauth2.credentials import Credentials as UserCreds
        token_file = os.path.join(app.root_path, "gmail_token.json")
        if os.path.exists(token_file):
            import json
            with open(token_file) as f:
                data = json.load(f)
            creds = UserCreds(
                token=data.get("token"),
                refresh_token=data.get("refresh_token"),
                token_uri=data.get("token_uri"),
                client_id=data.get("client_id"),
                client_secret=data.get("client_secret"),
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            from google.auth.transport.requests import Request
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return build('calendar', 'v3', credentials=creds)

    except Exception as e:
        logger.error(f"Error al crear servicio Google Calendar: {e}")
    return None


def sincronizar_cita_calendar(cita_id, especialidad, fecha, hora, paciente_nombre):
    service = _get_calendar_service()
    if not service:
        return False

    try:
        cal_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
        hora_str = str(hora)[:5]
        fecha_obj = datetime.strptime(str(fecha), "%Y-%m-%d") if isinstance(fecha, str) else fecha
        hora_parts = hora_str.split(":")
        start_dt = fecha_obj.replace(hour=int(hora_parts[0]), minute=int(hora_parts[1]))
        end_dt = start_dt + timedelta(hours=1)

        event = {
            'summary': f'{especialidad} - {paciente_nombre}',
            'description': f'Cita dental - {especialidad}\nPaciente: {paciente_nombre}\nID: #{cita_id}',
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'America/Lima',
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'America/Lima',
            },
        }

        created_event = service.events().insert(calendarId=cal_id, body=event).execute()
        logger.info(f"Cita #{cita_id} sincronizada con Google Calendar: {created_event.get('htmlLink')}")
        return True
    except Exception as e:
        logger.error(f"Error al sincronizar cita #{cita_id} con Google Calendar: {e}")
        return False


def eliminar_evento_calendar(event_id):
    service = _get_calendar_service()
    if not service:
        return False
    try:
        cal_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
        service.events().delete(calendarId=cal_id, eventId=event_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error al eliminar evento de Google Calendar: {e}")
        return False


def crear_tabla_auditoria():
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS auditoria (
                    id SERIAL PRIMARY KEY,
                    usuario_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
                    accion VARCHAR(100) NOT NULL,
                    detalle TEXT,
                    ip VARCHAR(45),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            conn.commit()
    except Exception as e:
        logger.error(f"Error al crear tabla auditoria: {e}")


crear_tabla_auditoria()


if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    iniciar_scheduler()
                                                                                      
    try:
        enviar_recordatorios_app()
    except Exception as e:
        logger.error(f"Error en la pasada inmediata de recordatorios: {e}")


if __name__ == '__main__':
    app.run(debug=True)
