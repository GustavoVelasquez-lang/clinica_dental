import logging
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import wraps

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from authlib.common.security import generate_token
from authlib.integrations.flask_client import OAuth
from db import db_connection
from dotenv import dotenv_values, load_dotenv, set_key
from email_utils import enviar_comprobante_admin, enviar_confirmacion_cita
from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   session, url_for, abort)
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

load_dotenv()

app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32).hex())
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_DEBUG", "0") == "0",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
    WTF_CSRF_ENABLED=True,
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)

csrf = CSRFProtect(app)
bcrypt = Bcrypt(app)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024


def _log_auditoria(accion, usuario_id=None, detalle=None):
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


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _flash_error(msg):
    flash(msg, "danger")


def _flash_success(msg):
    flash(msg, "success")


@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if os.environ.get("FLASK_DEBUG", "0") == "0":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.context_processor
def inject_admin_context():
    if session.get("rol") != "admin":
        return {}
    try:
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM citas WHERE estado = 'pendiente'")
            pendientes = cur.fetchone()["n"]
            return {"citas_pendientes": pendientes}
    except Exception:
        return {"citas_pendientes": 0}


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        if session.get("rol") != "admin":
            flash("Acceso denegado", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.route("/")
def inicio():
    if session.get("rol") == "admin":
        return redirect(url_for("admin_dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    ip = request.remote_addr
    baneada, minutos = esta_baneada(ip)
    if baneada:
        flash(f"IP bloqueada. Intenta en {minutos} minutos", "danger")
        return render_template("login.html")

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("clave", "")

        if not usuario or not clave:
            flash("Completa todos los campos", "danger")
            return redirect(url_for("login"))

        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT u.*, COALESCE(r.nombre, 'paciente') AS rol
                FROM usuarios u
                LEFT JOIN roles r ON u.id_rol = r.id
                WHERE u.numero_documento = %s
            """, (usuario,))
            user = cur.fetchone()

        if not user or not bcrypt.check_password_hash(user["contrasenia"], clave):
            baneada, restantes = registrar_intento_fallido(ip)
            if baneada:
                flash("Demasiados intentos. IP bloqueada 15 min", "danger")
            else:
                flash(f"Credenciales incorrectas ({restantes} intentos restantes)", "danger")
            return redirect(url_for("login"))

        if user["estado"] != "ACTIVO":
            flash("Usuario inactivo. Contacta al administrador.", "danger")
            return redirect(url_for("login"))

        limpiar_ip(ip)

        session.permanent = True
        session["usuario_id"] = user["id"]
        session["nombre"] = user["nombre"]
        session["rol"] = user["rol"]

        _log_auditoria("login", user["id"])

        if user["rol"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("inicio"))

    return render_template("login.html")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        dni = request.form.get("dni", "").strip()
        nombre = request.form.get("nombre", "").strip()
        apePaterno = request.form.get("apePaterno", "").strip()
        apeMaterno = request.form.get("apeMaterno", "").strip()
        correo = request.form.get("correo", "").strip()
        clave = request.form.get("clave", "")
        confirmar = request.form.get("confirmar", "")

        if not all([dni, nombre, apePaterno, apeMaterno, correo, clave, confirmar]):
            flash("Completa todos los campos", "danger")
            return redirect(url_for("registro"))

        if not re.match(r"^\d{8}$", dni):
            flash("El DNI debe contener 8 digitos", "danger")
            return redirect(url_for("registro"))

        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", correo):
            flash("Correo electronico invalido", "danger")
            return redirect(url_for("registro"))

        if len(clave) < 8:
            flash("La contraseña debe tener al menos 8 caracteres", "danger")
            return redirect(url_for("registro"))

        if not re.search(r"[A-Z]", clave) or not re.search(r"\d", clave):
            flash("La contraseña debe tener al menos 1 mayuscula y 1 numero", "danger")
            return redirect(url_for("registro"))

        if clave != confirmar:
            flash("Las contrasenas no coinciden", "danger")
            return redirect(url_for("registro"))

        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM usuarios WHERE numero_documento = %s OR correo = %s",
                (dni, correo)
            )
            if cur.fetchone():
                flash("DNI o correo ya registrado", "warning")
                return redirect(url_for("registro"))

            clave_hash = bcrypt.generate_password_hash(clave).decode("utf-8")
            cur.execute("""
                INSERT INTO usuarios (tipo_documento, numero_documento, nombre,
                    apePaterno, apeMaterno, correo, contrasenia, id_rol)
                VALUES (%s,%s,%s,%s,%s,%s,%s,2)
            """, ("DNI", dni, nombre, apePaterno, apeMaterno, correo, clave_hash))
            conn.commit()

        _flash_success("Cuenta creada correctamente. Ahora puedes iniciar sesion.")
        return redirect(url_for("login"))

    return render_template("registro.html")


@app.route("/logout")
def logout():
    _log_auditoria("logout")
    session.clear()
    return redirect(url_for("login"))


@app.route("/nosotros")
def nosotros():
    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre FROM especialidades")
        especialidades = cur.fetchall()
    return render_template("nosotros.html", especialidades=especialidades)


@app.route("/tratamientos")
def tratamientos():
    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM especialidades")
        especialidades = cur.fetchall()
    return render_template("especialidades.html", especialidades=especialidades)


@app.route("/buscar")
def buscar_especialidad():
    query = request.args.get("q", "").strip()
    if not query:
        return redirect(url_for("inicio"))

    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM especialidades
            WHERE nombre ILIKE %s OR descripcion ILIKE %s
        """, (f"%{query}%", f"%{query}%"))
        resultados = cur.fetchall()

    if resultados:
        return render_template("resultados_busqueda.html", resultados=resultados, query=query)
    flash("No se encontro la especialidad", "danger")
    return redirect(url_for("inicio"))


@app.route("/agendar", methods=["GET", "POST"])
@login_required
def agendar():
    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre FROM especialidades")
        especialidades = cur.fetchall()

        cur.execute("""
            SELECT u.id, u.nombre || ' ' || COALESCE(u.apepaterno,'') AS nombre
            FROM usuarios u
            WHERE u.id_rol = 3 OR u.id IN (SELECT DISTINCT odontologo_id FROM horarios)
            ORDER BY u.nombre
        """)
        odontologos = cur.fetchall()

        if request.method == "POST":
            fecha_str = request.form.get("fecha")
            especialidad_id = request.form.get("especialidad")
            hora = request.form.get("hora")
            odontologo_id = request.form.get("odontologo_id") or None
            mensaje = request.form.get("mensaje", "").strip()

            if not all([fecha_str, especialidad_id, hora]):
                flash("Completa todos los campos requeridos", "danger")
                return redirect(url_for("agendar"))

            try:
                fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Fecha invalida", "danger")
                return redirect(url_for("agendar"))

            manana = date.today() + timedelta(days=1)
            if fecha < manana:
                flash("Solo puedes agendar desde manana", "danger")
                return redirect(url_for("agendar"))

            if session.get("rol") != "paciente":
                flash("Solo pacientes pueden agendar citas", "danger")
                return redirect(url_for("inicio"))

            cur.execute("""
                SELECT id FROM citas
                WHERE especialidad_id = %s AND fecha = %s AND hora = %s
                  AND estado NOT IN ('cancelada', 'cancelado')
            """, (especialidad_id, fecha, hora))
            if cur.fetchone():
                flash("Esa hora ya esta ocupada", "danger")
                return redirect(url_for("agendar"))

            cur.execute("""
                INSERT INTO citas
                (paciente_id, especialidad_id, fecha, hora, odontologo_id, estado, estado_pago, mensaje)
                VALUES (%s, %s, %s, %s, %s, 'pendiente', 'pendiente', %s)
                RETURNING id
            """, (session["usuario_id"], especialidad_id, fecha, hora, odontologo_id, mensaje or None))
            cita_id = cur.fetchone()["id"]
            conn.commit()

            try:
                cur.execute("""
                    SELECT u.nombre, u.apepaterno, u.apematerno, u.correo,
                           e.nombre AS especialidad
                    FROM usuarios u
                    JOIN especialidades e ON e.id = %s
                    WHERE u.id = %s
                """, (especialidad_id, session["usuario_id"]))
                paciente = cur.fetchone()
                if paciente and paciente["correo"]:
                    nombre_pac = f"{paciente['nombre']} {paciente['apepaterno']} {paciente['apematerno']}".strip()
                    enviar_confirmacion_cita(
                        destinatario=paciente["correo"],
                        nombre_paciente=nombre_pac,
                        especialidad=paciente["especialidad"],
                        fecha=str(fecha),
                        hora=str(hora)[:5],
                    )
            except Exception as e:
                logger.error(f"Error al enviar confirmacion: {e}")

            _log_auditoria("agendar_cita", detalle=f"cita #{cita_id}")
            flash("Cita registrada. Realiza el adelanto para confirmar.", "success")
            return redirect(url_for("pago", cita_id=cita_id))

    return render_template("agendar_cita.html", especialidades=especialidades, odontologos=odontologos)


@app.route("/pago/<int:cita_id>", methods=["GET", "POST"])
@login_required
def pago(cita_id):
    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.id, c.fecha, c.hora, c.estado, c.comprobante, c.adelanto,
                   e.nombre AS especialidad
            FROM citas c
            JOIN especialidades e ON c.especialidad_id = e.id
            WHERE c.id = %s AND c.paciente_id = %s
        """, (cita_id, session["usuario_id"]))
        cita = cur.fetchone()

    if not cita:
        flash("Cita no encontrada", "danger")
        return redirect(url_for("mis_citas"))

    config = dotenv_values()
    yape_numero = config.get("YAPE_NUMERO", "956536766")
    yape_nombre = config.get("YAPE_NOMBRE", "Clinica Dental")
    yape_qr = config.get("YAPE_QR", "static/img/qr_yape.png")
    adelanto_monto = config.get("ADELANTO_MONTO", "20.00")

    if request.method == "POST":
        if "comprobante" not in request.files:
            flash("Debes seleccionar un archivo", "danger")
            return redirect(url_for("pago", cita_id=cita_id))

        archivo = request.files["comprobante"]
        if archivo.filename == "":
            flash("Debes seleccionar un archivo", "danger")
            return redirect(url_for("pago", cita_id=cita_id))

        if not archivo or not _allowed_file(archivo.filename):
            flash("Formato no valido. Usa PNG, JPG, JPEG, GIF o WEBP", "danger")
            return redirect(url_for("pago", cita_id=cita_id))

        filename = secure_filename(f"cita_{cita_id}_{archivo.filename}")
        upload_dir = os.path.join(app.root_path, "static", "comprobantes")
        os.makedirs(upload_dir, exist_ok=True)
        ruta = os.path.join(upload_dir, filename)
        archivo.save(ruta)

        ruta_rel = f"static/comprobantes/{filename}"
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE citas SET comprobante = %s WHERE id = %s", (ruta_rel, cita_id))
            conn.commit()

            cur.execute("""
                SELECT u.nombre, u.apePaterno, u.apeMaterno, u.correo AS correo_paciente
                FROM usuarios u WHERE u.id = %s
            """, (session["usuario_id"],))
            paciente = cur.fetchone()

            nombre_pac = f"{paciente['nombre']} {paciente['apepaterno']} {paciente['apematerno']}".strip()
            enviar_comprobante_admin(
                nombre_paciente=nombre_pac,
                especialidad=cita["especialidad"],
                fecha=str(cita["fecha"]),
                hora=str(cita["hora"])[:5],
                comprobante_path=os.path.join(app.root_path, ruta_rel),
            )

        _log_auditoria("subir_comprobante", detalle=f"cita #{cita_id}")
        flash("Comprobante enviado. Espera la confirmacion del administrador.", "success")
        return redirect(url_for("mis_citas"))

    if yape_qr.startswith("http"):
        yape_qr_url = yape_qr
    else:
        qr_filename = yape_qr.replace("static/", "")
        yape_qr_url = url_for("static", filename=qr_filename)
    return render_template("pago.html", cita=cita, yape_numero=yape_numero,
                           yape_nombre=yape_nombre, yape_qr=yape_qr_url,
                           adelanto_monto=adelanto_monto)


@app.route("/mis_citas")
@login_required
def mis_citas():
    page = request.args.get("page", 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM citas WHERE paciente_id = %s", (session["usuario_id"],))
        total = cur.fetchone()["n"]
        total_pages = max(1, (total + per_page - 1) // per_page)

        cur.execute("""
            SELECT c.id, e.nombre AS especialidad, c.fecha, c.hora, c.estado,
                   COALESCE(c.odontologo_id, 0) AS odontologo_id
            FROM citas c
            JOIN especialidades e ON c.especialidad_id = e.id
            WHERE c.paciente_id = %s
            ORDER BY c.fecha DESC, c.hora DESC
            LIMIT %s OFFSET %s
        """, (session["usuario_id"], per_page, offset))
        citas = cur.fetchall()

    return render_template("mis_citas.html", citas=citas, page=page, total_pages=total_pages)


@app.route("/mi_cuenta")
@login_required
def mi_cuenta():
    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.tipo_documento, u.numero_documento, u.nombre,
                   u.apePaterno, u.apeMaterno, u.correo,
                   COALESCE(r.nombre, 'paciente') AS rol,
                   u.estado, u.fecha_registro
            FROM usuarios u
            LEFT JOIN roles r ON u.id_rol = r.id
            WHERE u.id = %s
        """, (session["usuario_id"],))
        usuario = cur.fetchone()

        cur.execute("""
            SELECT c.id, e.nombre AS especialidad, c.fecha, c.hora, c.estado
            FROM citas c
            JOIN especialidades e ON c.especialidad_id = e.id
            WHERE c.paciente_id = %s
            ORDER BY c.fecha DESC
        """, (session["usuario_id"],))
        citas = cur.fetchall()

    return render_template("mi_cuenta.html", usuario=usuario, citas=citas)


@app.route("/cita/<int:cita_id>/cancelar", methods=["POST"])
@login_required
def cancelar_cita(cita_id):
    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE citas SET estado = 'cancelada'
            WHERE id = %s AND paciente_id = %s AND estado NOT IN ('cancelada', 'atendida', 'completada')
        """, (cita_id, session["usuario_id"]))
        if cur.rowcount > 0:
            conn.commit()
            _log_auditoria("cancelar_cita_paciente", detalle=f"cita #{cita_id}")
            flash("Cita cancelada correctamente", "success")
        else:
            flash("No se pudo cancelar la cita", "danger")
    return redirect(url_for("mis_citas"))


@app.route("/cita/<int:cita_id>/reprogramar", methods=["GET", "POST"])
@login_required
def reprogramar_cita(cita_id):
    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.*, e.nombre AS especialidad
            FROM citas c JOIN especialidades e ON c.especialidad_id = e.id
            WHERE c.id = %s AND c.paciente_id = %s
              AND c.estado NOT IN ('cancelada', 'atendida', 'completada')
        """, (cita_id, session["usuario_id"]))
        cita = cur.fetchone()

        if not cita:
            flash("Cita no encontrada o no reprogramable", "danger")
            return redirect(url_for("mis_citas"))

        cur.execute("SELECT id, nombre FROM especialidades")
        especialidades = cur.fetchall()

    if request.method == "POST":
        fecha_str = request.form.get("fecha")
        hora = request.form.get("hora")

        if not fecha_str or not hora:
            flash("Selecciona fecha y hora", "danger")
            return redirect(url_for("reprogramar_cita", cita_id=cita_id))

        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Fecha invalida", "danger")
            return redirect(url_for("reprogramar_cita", cita_id=cita_id))

        if fecha < date.today() + timedelta(days=1):
            flash("La fecha debe ser desde manana", "danger")
            return redirect(url_for("reprogramar_cita", cita_id=cita_id))

        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id FROM citas
                WHERE especialidad_id = %s AND fecha = %s AND hora = %s
                  AND id != %s AND estado NOT IN ('cancelada', 'cancelado')
            """, (cita["especialidad_id"], fecha, hora, cita_id))
            if cur.fetchone():
                flash("Esa hora ya esta ocupada", "danger")
                return redirect(url_for("reprogramar_cita", cita_id=cita_id))

            cur.execute("UPDATE citas SET fecha=%s, hora=%s WHERE id=%s", (fecha, hora, cita_id))
            conn.commit()

        _log_auditoria("reprogramar_cita_paciente", detalle=f"cita #{cita_id}")
        flash("Cita reprogramada correctamente", "success")
        return redirect(url_for("mis_citas"))

    return render_template("reprogramar_cita.html", cita=cita, especialidades=especialidades)


@app.route("/api/citas")
@login_required
def api_citas():
    with db_connection() as conn:
        cur = conn.cursor()
        if session.get("rol") == "admin":
            cur.execute("""
                SELECT c.fecha, c.hora, e.nombre
                FROM citas c
                JOIN especialidades e ON c.especialidad_id = e.id
                WHERE c.estado NOT IN ('cancelada', 'cancelado')
            """)
        else:
            cur.execute("""
                SELECT c.fecha, c.hora, e.nombre
                FROM citas c
                JOIN especialidades e ON c.especialidad_id = e.id
                WHERE c.paciente_id = %s
                  AND c.estado NOT IN ('cancelada', 'cancelado')
            """, (session["usuario_id"],))
        citas = cur.fetchall()

    return jsonify([{"title": c["nombre"], "start": f"{c['fecha']}T{c['hora']}"} for c in citas])


@app.route("/horarios_disponibles", methods=["POST"])
@login_required
def horarios_disponibles():
    data = request.get_json()
    if not data:
        return jsonify([])

    fecha = data.get("fecha")
    especialidad_id = data.get("especialidad")

    if not fecha or not especialidad_id:
        return jsonify([])

    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT hora FROM citas
            WHERE fecha = %s AND especialidad_id = %s
              AND estado NOT IN ('cancelada', 'cancelado')
        """, (fecha, especialidad_id))
        ocupadas = [str(c["hora"]) for c in cur.fetchall()]

    horas_sistema = ["09:00:00", "10:00:00", "11:00:00", "12:00:00", "15:00:00", "16:00:00"]
    disponibles = [h for h in horas_sistema if h not in ocupadas]

    return jsonify(disponibles)


@app.route("/api/consultar_dni/<dni>")
def consultar_dni(dni):
    if not dni.isdigit() or len(dni) != 8:
        return jsonify({"success": False, "message": "El DNI debe contener exactamente 8 digitos"}), 400

    token = os.getenv("DNI_API_TOKEN", "").strip().strip('"').strip("'")
    if not token:
        return jsonify({"success": False, "message": "Error de configuracion en el servidor"}), 500

    url = f"https://api.factiliza.com/v1/dni/info/{dni}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers, timeout=8)
        res_json = response.json()
        if response.status_code == 200 and res_json.get("status") == 200:
            datos = res_json.get("data", {})
            return jsonify({
                "success": True,
                "data": {
                    "nombres": datos.get("nombres", ""),
                    "apellido_paterno": datos.get("apellido_paterno", ""),
                    "apellido_materno": datos.get("apellido_materno", "")
                }
            })
        return jsonify({"success": False, "message": "No se encontraron datos para este DNI"}), 404
    except Exception:
        logger.error("Error al conectar con la API Factiliza")
        return jsonify({"success": False, "message": "Error al conectar con el servidor"}), 500


MAX_INTENTOS = 5
TIEMPO_BAN_MIN = 15
TIEMPO_VENTANA = 10

registro_ips = defaultdict(lambda: {"intentos": 0, "primer_intento": None, "baneado_hasta": None})


def esta_baneada(ip):
    datos = registro_ips[ip]
    if datos["baneado_hasta"] is None:
        return False, 0
    ahora = datetime.now()
    if ahora < datos["baneado_hasta"]:
        restantes = int((datos["baneado_hasta"] - ahora).total_seconds() / 60) + 1
        return True, restantes
    registro_ips[ip] = {"intentos": 0, "primer_intento": None, "baneado_hasta": None}
    return False, 0


def registrar_intento_fallido(ip):
    datos = registro_ips[ip]
    ahora = datetime.now()
    ventana = timedelta(minutes=TIEMPO_VENTANA)
    if datos["primer_intento"] and (ahora - datos["primer_intento"]) > ventana:
        datos["intentos"] = 0
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


def limpiar_ip(ip):
    registro_ips[ip] = {"intentos": 0, "primer_intento": None, "baneado_hasta": None}


# ═══════════════════════════════════════
#  ADMIN ROUTES
# ═══════════════════════════════════════

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    hoy = date.today()
    lunes = hoy - timedelta(days=hoy.weekday())
    inicio_mes = hoy.replace(day=1)

    with db_connection() as conn:
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
        esp_donut = [{
            "nombre": r["nombre"],
            "pct": round(r["n"] * 100 / total_tratamientos, 1) if total_tratamientos else 0,
            "color": colores[i % 4],
            "id": f"d{i + 1}"
        } for i, r in enumerate(top_esp)]

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

    return render_template("admin_dashboard.html",
                           citas_hoy=citas_hoy, citas_semana=citas_semana,
                           pacientes_nuevos=pacientes_nuevos, ingresos_mes=ingresos_mes,
                           citas_hoy_lista=citas_hoy_lista,
                           dias_labels=["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"],
                           citas_actual=citas_actual, citas_pasado=citas_pasado,
                           esp_donut=esp_donut, total_tratamientos=total_tratamientos,
                           ingresos_lista=ingresos_lista)


@app.route("/admin/citas")
@admin_required
def admin_citas():
    page = request.args.get("page", 1, type=int)
    per_page = 15
    offset = (page - 1) * per_page

    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM citas")
        total = cur.fetchone()["n"]
        total_pages = max(1, (total + per_page - 1) // per_page)

        cur.execute("""
            SELECT c.id, u.nombre AS paciente, e.nombre AS especialidad,
                   c.fecha, c.hora, c.estado, c.comprobante, c.estado_pago
            FROM citas c
            JOIN usuarios u ON c.paciente_id = u.id
            JOIN especialidades e ON c.especialidad_id = e.id
            ORDER BY c.fecha DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        citas = cur.fetchall()

    return render_template("admin_citas.html", citas=citas, page=page, total_pages=total_pages)


@app.route("/admin/eliminar/<int:id>", methods=["POST"])
@admin_required
def eliminar_cita(id):
    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM citas WHERE id = %s", (id,))
        conn.commit()
    _log_auditoria("eliminar_cita", detalle=f"cita #{id}")
    flash("Cita eliminada", "success")
    return redirect(url_for("admin_citas"))


@app.route("/admin/editar/<int:id>", methods=["GET", "POST"])
@admin_required
def editar_cita(id):
    with db_connection() as conn:
        cur = conn.cursor()

        if request.method == "POST":
            fecha = request.form.get("fecha")
            hora = request.form.get("hora")
            estado = request.form.get("estado")
            estado_pago = request.form.get("estado_pago", "")

            cur.execute("""
                UPDATE citas SET fecha=%s, hora=%s, estado=%s
                WHERE id=%s
            """, (fecha, hora, estado, id))

            if estado_pago:
                cur.execute("UPDATE citas SET estado_pago=%s WHERE id=%s", (estado_pago, id))

            conn.commit()
            _log_auditoria("editar_cita", detalle=f"cita #{id}")
            flash("Cita actualizada", "success")
            return redirect(url_for("admin_citas"))

        cur.execute("""
            SELECT c.*, e.nombre AS especialidad,
                   u.nombre || ' ' || COALESCE(u.apepaterno,'') AS paciente_nombre
            FROM citas c
            JOIN especialidades e ON c.especialidad_id = e.id
            JOIN usuarios u ON c.paciente_id = u.id
            WHERE c.id = %s
        """, (id,))
        cita = cur.fetchone()

    if not cita:
        flash("Cita no encontrada", "danger")
        return redirect(url_for("admin_citas"))

    return render_template("editar_cita.html", cita=cita)


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


@app.route("/admin/enviar_recordatorios", methods=["POST"])
@admin_required
def admin_enviar_recordatorios():
    from recordatorios import enviar_recordatorios
    try:
        enviar_recordatorios()
        flash("Recordatorios enviados correctamente", "success")
    except Exception:
        logger.exception("Error al enviar recordatorios")
        flash("Error al enviar recordatorios. Revisa los logs.", "danger")
    return redirect(url_for("admin_citas"))


@app.route("/admin/recordatorios")
@admin_required
def admin_recordatorios():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM recordatorios")
        total = cur.fetchone()["n"]
        total_pages = max(1, (total + per_page - 1) // per_page)

        cur.execute("""
            SELECT r.id, r.dias_antes, r.enviado,
                   u.nombre, u.apePaterno, u.apeMaterno, u.correo,
                   e.nombre AS especialidad, c.fecha, c.hora
            FROM recordatorios r
            JOIN citas c ON r.cita_id = c.id
            JOIN usuarios u ON c.paciente_id = u.id
            JOIN especialidades e ON c.especialidad_id = e.id
            ORDER BY r.enviado DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        recordatorios = cur.fetchall()

    return render_template("admin_recordatorios.html", recordatorios=recordatorios, page=page, total_pages=total_pages)


@app.route("/admin/pacientes")
@admin_required
def admin_pacientes():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM usuarios WHERE id_rol = 2")
        total = cur.fetchone()["n"]
        total_pages = max(1, (total + per_page - 1) // per_page)

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
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        pacientes = cur.fetchall()

    return render_template("admin_pacientes.html", pacientes=pacientes, page=page, total_pages=total_pages)


@app.route("/admin/paciente/<int:id>/estado", methods=["POST"])
@admin_required
def admin_paciente_estado(id):
    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT estado FROM usuarios WHERE id = %s", (id,))
        u = cur.fetchone()
        if u:
            nuevo = "INACTIVO" if u["estado"] == "ACTIVO" else "ACTIVO"
            cur.execute("UPDATE usuarios SET estado = %s WHERE id = %s", (nuevo, id))
            conn.commit()
            _log_auditoria("cambiar_estado_paciente", detalle=f"paciente #{id} -> {nuevo}")
            flash(f"Estado del paciente actualizado a {nuevo}", "success")
    return redirect(url_for("admin_pacientes"))


@app.route("/admin/tratamientos", methods=["GET", "POST"])
@admin_required
def admin_tratamientos():
    with db_connection() as conn:
        cur = conn.cursor()

        if request.method == "POST":
            accion = request.form.get("accion")

            if accion == "especialidad":
                nombre = request.form.get("nombre", "").strip()
                descripcion = request.form.get("descripcion", "").strip()
                if nombre:
                    cur.execute("""
                        INSERT INTO especialidades (nombre, descripcion)
                        VALUES (%s, %s) ON CONFLICT (nombre) DO NOTHING
                    """, (nombre, descripcion))
                    conn.commit()
                    flash("Especialidad registrada", "success")
                else:
                    flash("Debes indicar el nombre de la especialidad", "danger")

            elif accion == "tratamiento":
                nombre = request.form.get("nombre", "").strip()
                especialidad_id = request.form.get("especialidad_id")
                precio = request.form.get("precio_base")
                descripcion = request.form.get("descripcion", "").strip()
                if nombre and especialidad_id:
                    try:
                        cur.execute("""
                            INSERT INTO tratamientos (id_especialidad, nombre, descripcion, precio_base)
                            VALUES (%s, %s, %s, %s)
                        """, (especialidad_id, nombre, descripcion or None, precio or None))
                        conn.commit()
                        flash("Tratamiento registrado", "success")
                    except Exception:
                        conn.rollback()
                        flash("Error al registrar tratamiento", "danger")
                else:
                    flash("Nombre y especialidad son obligatorios", "danger")

            return redirect(url_for("admin_tratamientos"))

        cur.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
        especialidades = cur.fetchall()

        cur.execute("""
            SELECT t.id_tratamiento, t.nombre, t.descripcion, t.precio_base,
                   e.id AS especialidad_id, e.nombre AS especialidad
            FROM tratamientos t
            JOIN especialidades e ON t.id_especialidad = e.id
            ORDER BY e.nombre, t.nombre
        """)
        tratamientos = cur.fetchall()

        cur.execute("""
            SELECT e.id, e.nombre, e.descripcion, e.estado, COUNT(t.id_tratamiento) AS n_tratamientos
            FROM especialidades e LEFT JOIN tratamientos t ON t.id_especialidad = e.id
            GROUP BY e.id ORDER BY e.nombre
        """)
        lista_especialidades = cur.fetchall()

    return render_template("admin_tratamientos.html",
                           especialidades=especialidades, tratamientos=tratamientos,
                           lista_especialidades=lista_especialidades)


@app.route("/admin/tratamiento/eliminar/<int:id>", methods=["POST"])
@admin_required
def eliminar_tratamiento(id):
    with db_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM tratamientos WHERE id_tratamiento = %s", (id,))
            conn.commit()
            _log_auditoria("eliminar_tratamiento", detalle=f"tratamiento #{id}")
            flash("Tratamiento eliminado", "success")
        except Exception:
            conn.rollback()
            flash("No se pudo eliminar el tratamiento", "danger")
    return redirect(url_for("admin_tratamientos"))


@app.route("/admin/facturacion")
@admin_required
def admin_facturacion():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    with db_connection() as conn:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) AS n FROM pagos")
        total_pagos = cur.fetchone()["n"]

        cur.execute("""
            SELECT p.id, p.tipo, p.monto, p.fecha, u.nombre AS paciente,
                   e.nombre AS especialidad, c.fecha AS fecha_cita,
                   COALESCE(mp.nombre, 'Yape') AS metodo
            FROM pagos p
            JOIN citas c ON p.id_cita = c.id
            JOIN usuarios u ON c.paciente_id = u.id
            JOIN especialidades e ON c.especialidad_id = e.id
            LEFT JOIN comprobantes_pago cp ON cp.id_pago = p.id
            LEFT JOIN metodos_pago mp ON mp.id_metodo_pago = cp.id_metodo_pago
            ORDER BY p.fecha DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        pagos_lista = cur.fetchall()

        cur.execute("SELECT COALESCE(SUM(monto),0) AS total FROM pagos")
        total_pagado = float(cur.fetchone()["total"])

        cur.execute("""
            SELECT c.id, u.nombre AS paciente, e.nombre AS especialidad,
                   c.fecha, c.hora, c.adelanto, c.estado_pago, c.comprobante
            FROM citas c
            JOIN usuarios u ON c.paciente_id = u.id
            JOIN especialidades e ON c.especialidad_id = e.id
            WHERE c.adelanto > 0 OR c.comprobante IS NOT NULL
            ORDER BY c.fecha DESC
        """)
        adelantos = cur.fetchall()
        total_adelantos = sum(float(r["adelanto"]) for r in adelantos)

    total_pages = max(1, (total_pagos + per_page - 1) // per_page)

    return render_template("admin_facturacion.html",
                           pagos_lista=pagos_lista, total_pagado=total_pagado,
                           adelantos=adelantos, total_adelantos=total_adelantos,
                           page=page, total_pages=total_pages)


@app.route("/admin/personal")
@admin_required
def admin_personal():
    with db_connection() as conn:
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
    return render_template("admin_personal.html", personal=personal)


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
                        apePaterno, apeMaterno, correo, contrasenia, id_rol, estado)
                    VALUES ('DNI', %s, %s, %s, %s, %s, %s, 3, 'ACTIVO')
                """, (dni, nombre, apepaterno, apematerno or None, correo,
                      bcrypt.generate_password_hash(dni).decode("utf-8")))
                odont_id = cur.execute("SELECT currval(pg_get_serial_sequence('usuarios','id'))").fetchone() or None

                cur.execute("SELECT currval(pg_get_serial_sequence('usuarios','id')) AS id")
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
    flash("Horario eliminado", "success")
    return redirect(url_for("admin_horarios"))


@app.route("/admin/inventario", methods=["GET", "POST"])
@admin_required
def admin_inventario():
    with db_connection() as conn:
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
                    except Exception:
                        conn.rollback()
                        flash("Error al agregar producto", "danger")
                else:
                    flash("El nombre del producto es obligatorio", "danger")

            elif accion == "actualizar":
                try:
                    cur.execute("""
                        UPDATE inventario SET cantidad = %s, stock_minimo = %s WHERE id = %s
                    """, (request.form.get("cantidad") or 0,
                          request.form.get("stock_minimo") or 0,
                          request.form.get("id")))
                    conn.commit()
                    flash("Stock actualizado", "success")
                except Exception:
                    conn.rollback()
                    flash("Error al actualizar stock", "danger")

            return redirect(url_for("admin_inventario"))

        cur.execute("SELECT * FROM inventario ORDER BY nombre")
        inventario = cur.fetchall()

        cur.execute("SELECT COALESCE(SUM(cantidad),0) AS total FROM inventario")
        total_items = cur.fetchone()["total"]
        cur.execute("SELECT COALESCE(SUM(cantidad * precio_compra),0) AS total FROM inventario WHERE precio_compra IS NOT NULL")
        valor_stock = float(cur.fetchone()["total"])
        cur.execute("SELECT COUNT(*) AS n FROM inventario WHERE cantidad <= stock_minimo")
        stock_bajo = cur.fetchone()["n"]

    return render_template("admin_inventario.html",
                           inventario=inventario, total_items=total_items,
                           valor_stock=valor_stock, stock_bajo=stock_bajo)


@app.route("/admin/inventario/eliminar/<int:id>", methods=["POST"])
@admin_required
def eliminar_inventario(id):
    with db_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM inventario WHERE id = %s", (id,))
            conn.commit()
            _log_auditoria("eliminar_inventario", detalle=f"producto #{id}")
            flash("Producto eliminado", "success")
        except Exception:
            conn.rollback()
            flash("Error al eliminar producto", "danger")
    return redirect(url_for("admin_inventario"))


@app.route("/admin/reportes")
@admin_required
def admin_reportes():
    with db_connection() as conn:
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

    return render_template("admin_reportes.html",
                           citas_por_estado=citas_por_estado, citas_por_mes=citas_por_mes,
                           ingresos_por_especialidad=ingresos_por_especialidad,
                           pacientes_por_mes=pacientes_por_mes,
                           total_citas=total_citas, total_pacientes=total_pacientes,
                           total_ingresos=total_ingresos)


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


@app.route("/admin/config", methods=["GET", "POST"])
@admin_required
def admin_config():
    env_path = os.path.join(app.root_path, ".env")

    if request.method == "POST":
        acciones = {
            "YAPE_NUMERO": request.form.get("yape_numero", "").strip(),
            "YAPE_NOMBRE": request.form.get("yape_nombre", "").strip(),
            "YAPE_QR": request.form.get("yape_qr", "").strip(),
            "ADELANTO_MONTO": request.form.get("adelanto_monto", "").strip(),
        }
        for clave, valor in acciones.items():
            if valor:
                try:
                    set_key(env_path, clave, valor)
                except Exception:
                    flash(f"Error guardando {clave}", "danger")
        _log_auditoria("actualizar_config")
        flash("Configuracion guardada correctamente", "success")
        return redirect(url_for("admin_config"))

    config = dotenv_values(env_path)
    return render_template("admin_config.html",
                           yape_numero=config.get("YAPE_NUMERO", ""),
                           yape_nombre=config.get("YAPE_NOMBRE", ""),
                           yape_qr=config.get("YAPE_QR", ""),
                           adelanto_monto=config.get("ADELANTO_MONTO", "20.00"))


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


# ═══════════════════════════════════════
#  GOOGLE OAUTH
# ═══════════════════════════════════════

oauth = OAuth(app)

google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)


@app.route('/login/google')
def login_google():
    nonce = generate_token()
    session['nonce'] = nonce
    return google.authorize_redirect(
        url_for('authorize_google', _external=True),
        nonce=nonce
    )


@app.route('/authorize/google')
def authorize_google():
    nonce = session.pop('nonce', None)
    try:
        token = google.authorize_access_token()
        if nonce:
            user = google.parse_id_token(token, nonce=nonce)
        else:
            flash("Sesion expirada. Intenta de nuevo.", "danger")
            return redirect(url_for("login"))

        correo = user['email']

        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT u.id, u.nombre, COALESCE(r.nombre, 'paciente') AS rol
                FROM usuarios u
                LEFT JOIN roles r ON u.id_rol = r.id
                WHERE LOWER(TRIM(u.correo)) = LOWER(TRIM(%s))
            """, (correo,))
            usuario_db = cur.fetchone()

        if not usuario_db:
            flash("No estas registrado en el sistema.", "danger")
            return redirect(url_for("registro"))

        session.permanent = True
        session['usuario_id'] = usuario_db['id']
        session['rol'] = usuario_db['rol']
        session['nombre'] = usuario_db['nombre']

        _log_auditoria("login_google", usuario_db['id'])

        if usuario_db['rol'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('inicio'))

    except Exception:
        logger.exception("Error durante autenticacion Google")
        flash("Error durante la autenticacion. Intenta de nuevo.", "danger")
        return redirect(url_for('login'))


# ═══════════════════════════════════════
#  GOOGLE CALENDAR INTEGRATION
# ═══════════════════════════════════════

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


# ═══════════════════════════════════════
#  SCHEDULER
# ═══════════════════════════════════════

def enviar_recordatorios_app():
    try:
        from recordatorios import enviar_recordatorios
        enviar_recordatorios()
    except Exception:
        logger.exception("Error en el envio automatico de recordatorios")


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
    logger.info("Scheduler de recordatorios iniciado (diario a las 08:00)")


if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    iniciar_scheduler()
    try:
        enviar_recordatorios_app()
    except Exception:
        logger.error("Error en la pasada inmediata de recordatorios")


# ═══════════════════════════════════════
#  TABLA AUDITORIA
# ═══════════════════════════════════════

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


if __name__ == '__main__':
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=5000)
