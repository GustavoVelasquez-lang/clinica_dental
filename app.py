import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import wraps

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from authlib.common.security import generate_token
from authlib.integrations.flask_client import OAuth
from db import get_connection
from dotenv import dotenv_values, load_dotenv
from email_utils import enviar_comprobante_admin
from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   session, url_for)
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = Flask(__name__)
app.secret_key = "clave_secreta_segura"
bcrypt = Bcrypt(app)
# -------------------------------
# DECORADOR: LOGIN REQUERIDO
# -------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.route("/agendar", methods=["GET", "POST"])
@login_required
def agendar():

    conn = get_connection()
    cursor = conn.cursor()

    # 🔥 traer especialidades
    cursor.execute("SELECT id, nombre FROM especialidades")
    especialidades = cursor.fetchall()

    if request.method == "POST":

        fecha_str = request.form.get("fecha")
        especialidad_id = request.form.get("especialidad")
        hora = request.form.get("hora")

        # ❌ validar fecha vacía
        if not fecha_str:
            flash("❌ Debes seleccionar una fecha", "danger")
            return redirect(url_for("agendar"))

        # ❌ convertir fecha
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            flash("❌ Fecha inválida", "danger")
            return redirect(url_for("agendar"))

        # ❌ solo desde mañana
        mañana = date.today() + timedelta(days=1)
        if fecha < mañana:
            flash("❌ Solo puedes agendar desde mañana", "danger")
            return redirect(url_for("agendar"))
        if session["rol"] != "paciente":
            flash("❌ Solo pacientes pueden agendar citas", "danger")
            return redirect(url_for("inicio"))

        # 🔥 VALIDAR DISPONIBILIDAD (CLAVE DEL SISTEMA)
        cursor.execute("""
            SELECT id FROM citas
            WHERE especialidad_id = %s AND fecha = %s AND hora = %s
        """, (especialidad_id, fecha, hora))

        ocupado = cursor.fetchone()

        if ocupado:
            flash("❌ Esa hora ya está ocupada", "danger")
            return redirect(url_for("agendar"))

        # 💾 INSERTAR CITA
        cursor.execute("""
            INSERT INTO citas 
            (paciente_id, especialidad_id, fecha, hora, estado, estado_pago)
            VALUES (%s, %s, %s, %s, 'pendiente', 'pendiente')
            RETURNING id
        """, (
            session["usuario_id"],
            especialidad_id,
            fecha,
            hora
        ))

        cita_id = cursor.fetchone()["id"]
        conn.commit()
        conn.close()

        flash("✅ Cita registrada, ahora realiza el adelanto", "success")

        return redirect(url_for("pago", cita_id=cita_id))

    conn.close()
    return render_template("agendar_cita.html", especialidades=especialidades)


@app.route("/pago/<int:cita_id>", methods=["GET", "POST"])
@login_required
def pago(cita_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, c.fecha, c.hora, c.estado, c.comprobante,
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

    config = dotenv_values()
    yape_numero = config.get("YAPE_NUMERO", "956536766")
    yape_nombre = config.get("YAPE_NOMBRE", "Clinica Dental")
    yape_qr = config.get("YAPE_QR", "static/img/qr_yape.png")

    if request.method == "POST":
        if "comprobante" not in request.files:
            flash("Debes seleccionar un archivo", "danger")
            return redirect(url_for("pago", cita_id=cita_id))

        archivo = request.files["comprobante"]

        if archivo.filename == "":
            flash("Debes seleccionar un archivo", "danger")
            return redirect(url_for("pago", cita_id=cita_id))

        if archivo:
            filename = secure_filename(f"cita_{cita_id}_{archivo.filename}")
            upload_dir = os.path.join(app.root_path, "static", "comprobantes")
            os.makedirs(upload_dir, exist_ok=True)
            ruta = os.path.join(upload_dir, filename)
            archivo.save(ruta)

            ruta_rel = f"static/comprobantes/{filename}"
            cursor.execute("UPDATE citas SET comprobante = %s WHERE id = %s", (ruta_rel, cita_id))
            conn.commit()

            cursor.execute("""
                SELECT u.nombre, u.apePaterno, u.apeMaterno, u.correo AS correo_paciente
                FROM usuarios u WHERE u.id = %s
            """, (session["usuario_id"],))
            paciente = cursor.fetchone()

            nombre_pac = f"{paciente['nombre']} {paciente['apePaterno']} {paciente['apeMaterno']}".strip()

            enviar_comprobante_admin(
                nombre_paciente=nombre_pac,
                especialidad=cita["especialidad"],
                fecha=str(cita["fecha"]),
                hora=str(cita["hora"])[:5],
                comprobante_path=os.path.join(app.root_path, ruta_rel),
            )

            conn.close()
            flash("Comprobante enviado correctamente. Espera la confirmacion del administrador.", "success")
            return redirect(url_for("mis_citas"))

    conn.close()
    if yape_qr.startswith("http"):
        yape_qr_url = yape_qr
    else:
        qr_filename = yape_qr.replace("static/", "")
        yape_qr_url = url_for("static", filename=qr_filename)
    return render_template("pago.html", cita=cita, yape_numero=yape_numero, yape_nombre=yape_nombre, yape_qr=yape_qr_url)


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        dni = request.form["dni"]
        nombre = request.form["nombre"]
        apePaterno = request.form["apePaterno"]
        apeMaterno = request.form["apeMaterno"]
        correo = request.form["correo"]
        clave = request.form["clave"]
        confirmar = request.form["confirmar"]

        if clave != confirmar:
            flash("❌ Las contraseñas no coinciden", "danger")
            return redirect(url_for("registro"))
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM usuarios WHERE numero_documento = %s OR correo = %s",
            (dni, correo)
        )
        existe = cursor.fetchone()
        if existe:
            conn.close()
            flash("⚠️ DNI o correo ya registrado", "warning")
            return redirect(url_for("registro"))
        
        clave_hash = bcrypt.generate_password_hash(clave).decode("utf-8")


        cursor.execute("""
            INSERT INTO usuarios (
                tipo_documento,
                numero_documento,
                nombre,
                apePaterno,
                apeMaterno,
                correo,
                contrasenia,
                id_rol
            )   
            VALUES (%s,%s,%s,%s,%s,%s,%s,2)
        """, (
            "DNI",
            dni,
            nombre,
            apePaterno,
            apeMaterno,
            correo,
            clave_hash
        ))  

        conn.commit()
        conn.close()

    return render_template("registro.html")


@app.route("/logout")
def logout():
    session.clear()  # 🔥 borra toda la sesión
    return redirect(url_for("login"))


@app.route("/")
def inicio():
    # 🔥 Si es admin → lo mandas directo al panel
    if session.get("rol") == "admin":
        return redirect(url_for("admin_citas"))

    # 👤 Si es paciente → index normal
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    ip = request.remote_addr  # 🔥 obtener IP

    # 🔒 Verificar si está baneado
    baneada, minutos = esta_baneada(ip)
    if baneada:
        flash(f"🚫 IP bloqueada. Intenta en {minutos} minutos", "danger")
        return render_template("login.html")

    if request.method == "POST":
        usuario = request.form["usuario"]
        clave = request.form["clave"]

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT u.*, COALESCE(r.nombre, 'paciente') AS rol
            FROM usuarios u
            LEFT JOIN roles r ON u.id_rol = r.id
            WHERE u.numero_documento = %s
        """, (usuario,))
        user = cursor.fetchone()
        conn.close()

        # ❌ usuario no existe
        if not user:
            baneada, restantes = registrar_intento_fallido(ip)
            flash(f"❌ Usuario no existe ({restantes} intentos restantes)", "danger")
            return redirect(url_for("login"))

        # ❌ usuario inactivo
        if user["estado"] != "ACTIVO":
            baneada, restantes = registrar_intento_fallido(ip)
            flash("❌ Usuario inactivo", "danger")
            return redirect(url_for("login"))

        # ❌ contraseña incorrecta
        if not bcrypt.check_password_hash(user["contrasenia"], clave):
            baneada, restantes = registrar_intento_fallido(ip)

            if baneada:
                flash("🚫 Demasiados intentos. IP bloqueada 15 min", "danger")
            else:
                flash(f"❌ Contraseña incorrecta ({restantes} intentos restantes)", "danger")

            return redirect(url_for("login"))

        # ✅ LOGIN CORRECTO → limpiar IP
        limpiar_ip(ip)

        session["usuario_id"] = user["id"]
        session["nombre"] = user["nombre"]
        session["rol"] = user["rol"]

        if user["rol"] == "admin":
            return redirect(url_for("admin_citas"))
        else:
            return redirect(url_for("inicio"))

    return render_template("login.html")

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
    lista = [
        {
            "nombre": "Ortodoncia",
            "descripcion": "Corrección de dientes",
            "imagen": "brakets.jpg"
        },
        {
            "nombre": "Endodoncia",
            "descripcion": "Tratamiento de conducto",
            "imagen": "endodoncia.jpg"
        }
    ]

    return render_template("especialidades.html", especialidades=lista)

@app.route("/tratamientos")
def tratamientos():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM especialidades")
    especialidades = cursor.fetchall()

    conn.close()

    return render_template("especialidades.html", especialidades=especialidades)


@app.route("/mis_citas")
@login_required
def mis_citas():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, e.nombre AS especialidad, c.fecha, c.hora, c.estado
        FROM citas c
        JOIN especialidades e ON c.especialidad_id = e.id
        WHERE c.paciente_id = %s
        ORDER BY c.fecha DESC
    """, (session["usuario_id"],))

    citas = cursor.fetchall()
    conn.close()

    return render_template("mis_citas.html", citas=citas)

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

    return render_template("mi_cuenta.html", usuario=usuario, citas=citas)

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

    # 🕒 horario del sistema
    horas_sistema = [
        "09:00:00", "10:00:00", "11:00:00",
        "12:00:00", "15:00:00", "16:00:00"
    ]

    # 🔥 filtrar disponibles
    disponibles = [h for h in horas_sistema if h not in ocupadas]

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
            return redirect(url_for("login"))

        if session.get("rol") != "admin":
            flash("❌ Acceso denegado", "danger")
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated_function

@app.route("/admin/citas")
@admin_required
def admin_citas():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, u.nombre AS paciente, e.nombre AS especialidad,
            c.fecha, c.hora, c.estado, c.comprobante
        FROM citas c
        JOIN usuarios u ON c.paciente_id = u.id
        JOIN especialidades e ON c.especialidad_id = e.id
        ORDER BY c.fecha DESC
    """)

    citas = cursor.fetchall()
    conn.close()

    return render_template("admin_citas.html", citas=citas)

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

@app.route("/admin/eliminar/<int:id>")
@admin_required
def eliminar_cita(id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM citas WHERE id = %s", (id,))
    conn.commit()
    conn.close()

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

        return redirect(url_for("admin_citas"))

    cursor.execute("SELECT * FROM citas WHERE id = %s", (id,))
    cita = cursor.fetchone()
    conn.close()

    return render_template("editar_cita.html", cita=cita)



oauth = OAuth(app)


# Carga las variables de entorno
load_dotenv()

# Registro de OAuth
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

    return google.authorize_redirect(
        url_for('authorize_google', _external=True),
        nonce=nonce
    )

@app.route('/authorize/google')
def authorize_google():
    # Recupera el nonce sin forzar el error si expiró en la cookie
    nonce = session.pop('nonce', None)

    try:
        token = google.authorize_access_token()
        
        # Si el nonce existe se valida, si no, se parsea el ID token directamente
        if nonce:
            user = google.parse_id_token(token, nonce=nonce)
        else:
            user = google.parse_id_token(token)

        correo = user['email']

        conn = get_connection()
        cursor = conn.cursor()

        # Consulta insensible a mayúsculas usando LEFT JOIN para evitar fallos si id_rol era nulo
        cursor.execute("""
            SELECT u.id, u.nombre, COALESCE(r.nombre, 'paciente') AS rol
            FROM usuarios u
            LEFT JOIN roles r ON u.id_rol = r.id
            WHERE LOWER(TRIM(u.correo)) = LOWER(TRIM(%s))
        """, (correo,))
        
        usuario_db = cursor.fetchone()
        conn.close()

        if not usuario_db:
            flash("❌ No estás registrado en el sistema.", "danger")
            return redirect(url_for("registro"))

        # Guardar datos en la sesión
        session['usuario_id'] = usuario_db['id']
        session['rol']        = usuario_db['rol']
        session['nombre']     = usuario_db['nombre']

        # Redireccionar según el rol recuperado
        if usuario_db['rol'] == 'admin':
            return redirect(url_for('admin_citas'))
        else:
            return redirect(url_for('inicio'))

    except Exception as e:
        flash(f"Error durante la autenticación: {str(e)}", "danger")
        return redirect(url_for('login'))


@app.route("/api/consultar_dni/<dni>")
def consultar_dni(dni):
    # 1. Validar el formato del DNI
    if not dni.isdigit() or len(dni) != 8:
        return jsonify({"success": False, "message": "El DNI debe contener exactamente 8 dígitos"}), 400

    # 2. Obtener y limpiar el token del .env
    token = os.getenv("DNI_API_TOKEN", "").strip().strip('"').strip("'")
    
    if not token:
        logger.error("No se encontró el token DNI_API_TOKEN en el archivo .env")
        return jsonify({"success": False, "message": "Error de configuración en el servidor"}), 500

    # 3. Configurar Endpoint y Headers según la documentación oficial de Factiliza
    url = f"https://api.factiliza.com/v1/dni/info/{dni}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=8)
        res_json = response.json()

        # 4. Validar la respuesta entregada por Factiliza
        if response.status_code == 200 and res_json.get("status") == 200:
            datos_persona = res_json.get("data", {})
            return jsonify({
                "success": True,
                "data": {
                    "nombres": datos_persona.get("nombres", ""),
                    "apellido_paterno": datos_persona.get("apellido_paterno", ""),
                    "apellido_materno": datos_persona.get("apellido_materno", "")
                }
            })
        else:
            msg = res_json.get("message", "No se encontraron datos para este DNI")
            return jsonify({"success": False, "message": msg}), response.status_code

    except Exception as e:
        logger.error(f"Error al conectar con la API Factiliza: {e}")
        return jsonify({"success": False, "message": f"Error al conectar con la API: {str(e)}"}), 500

# ── Configuración ──────────────────────────────
MAX_INTENTOS   = 5          # intentos fallidos antes del ban
TIEMPO_BAN_MIN = 15         # minutos de ban
TIEMPO_VENTANA = 10         # ventana de tiempo (minutos) para contar intentos

# ── Almacenamiento en memoria ──────────────────
# { "ip": {"intentos": int, "primer_intento": datetime, "baneado_hasta": datetime|None} }
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

    # Ban expirado → limpiar
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

    # Si pasó la ventana de tiempo, reiniciar contador
    if datos["primer_intento"] and (ahora - datos["primer_intento"]) > ventana:
        datos["intentos"]       = 0
        datos["primer_intento"] = None

    # Primer intento en esta ventana
    if datos["primer_intento"] is None:
        datos["primer_intento"] = ahora

    datos["intentos"] += 1

    # ¿Supera el límite?
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


if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    iniciar_scheduler()


if __name__ == '__main__':
    app.run(debug=True)