"""
Script autónomo para enviar recordatorios de citas.
Puede ejecutarse manualmente o programarse con Windows Task Scheduler
(ejecución diaria recomendada a las 8:00 AM).

Uso:
    python recordatorios.py
"""

import logging
import sys
from datetime import date, timedelta

from db import get_connection
from email_utils import enviar_recordatorio_cita

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def crear_tabla_recordatorios():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recordatorios (
            id SERIAL PRIMARY KEY,
            cita_id INT NOT NULL REFERENCES citas(id) ON DELETE CASCADE,
            dias_antes INT NOT NULL,
            enviado TIMESTAMP DEFAULT now(),
            CONSTRAINT unique_recordatorio UNIQUE (cita_id, dias_antes)
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Tabla 'recordatorios' verificada/creada correctamente")


def enviar_recordatorios():
    crear_tabla_recordatorios()
    hoy = date.today()
    conn = get_connection()
    cursor = conn.cursor()

    for dias_antes in (3, 2, 1):
        fecha_cita = hoy + timedelta(days=dias_antes)
        logger.info(f"Buscando citas para {fecha_cita} (T-{dias_antes})")

        cursor.execute("""
            SELECT c.id, c.fecha, c.hora,
                   u.nombre, u.apePaterno, u.apeMaterno, u.correo,
                   e.nombre AS especialidad
            FROM citas c
            JOIN usuarios u ON c.paciente_id = u.id
            JOIN especialidades e ON c.especialidad_id = e.id
            WHERE c.fecha = %s
              AND c.estado NOT IN ('cancelado', 'atendido', 'completada')
              AND NOT EXISTS (
                  SELECT 1 FROM recordatorios r
                  WHERE r.cita_id = c.id AND r.dias_antes = %s
              )
        """, (fecha_cita, dias_antes))

        citas = cursor.fetchall()

        for cita in citas:
            nombre_completo = f"{cita['nombre']} {cita['apePaterno']} {cita['apeMaterno']}".strip()
            fecha_str = cita['fecha'].strftime("%d/%m/%Y") if hasattr(cita['fecha'], 'strftime') else str(cita['fecha'])
            hora_str = str(cita['hora'])[:5]

            logger.info(f"Enviando recordatorio T-{dias_antes} a {cita['correo']} para cita #{cita['id']}")

            exito = enviar_recordatorio_cita(
                destinatario=cita['correo'],
                nombre_paciente=nombre_completo,
                especialidad=cita['especialidad'],
                fecha=fecha_str,
                hora=hora_str,
                dias_antes=dias_antes,
            )

            if exito:
                cursor.execute("""
                    INSERT INTO recordatorios (cita_id, dias_antes)
                    VALUES (%s, %s)
                """, (cita['id'], dias_antes))
                conn.commit()
                logger.info(f"Recordatorio T-{dias_antes} registrado para cita #{cita['id']}")
            else:
                logger.error(f"Fallo al enviar recordatorio T-{dias_antes} para cita #{cita['id']}")

    conn.close()
    logger.info("Proceso de recordatorios finalizado")


if __name__ == "__main__":
    try:
        enviar_recordatorios()
    except Exception as e:
        logger.exception(f"Error en el proceso de recordatorios: {e}")
        sys.exit(1)
