"""Seed idempotente: registro inicial de tratamientos de Clinica SELEDENT.

Uso:
    python seed_tratamientos.py

Vincula cada tratamiento con su especialidad (por nombre, con creación
automática si no existe) y hace upsert por (id_especialidad, nombre).
Ejecutarlo varias veces no genera duplicados.
"""
import unicodedata

from db import get_connection


def _norm(texto):
    """Normaliza a minúsculas sin acentos para comparar nombres."""
    texto = (texto or "").strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


GRUPOS = [
    {
        "especialidad": "Odontología General / Preventiva",
        "candidatos": ["odontologia general", "odontologia general / preventiva"],
        "descripcion": "Prevención, diagnóstico y tratamiento integral de tu salud bucal.",
        "tratamientos": [
            {
                "nombre": "Evaluación General / Primera Consulta",
                "precio": 50.00, "adelanto": 50.00, "duracion": 30,
                "descripcion": "Diagnóstico inicial y plan de tratamiento personalizado.",
            },
            {
                "nombre": "Profilaxis Dental (Limpieza Bucal)",
                "precio": 80.00, "adelanto": 30.00, "duracion": 45,
                "descripcion": "Eliminación de placa y sarro para mantener dientes y encías sanos.",
            },
            {
                "nombre": "Curación con Resina Estética",
                "precio": 70.00, "adelanto": 30.00, "duracion": 40,
                "descripcion": "Restauración de caries con resina del color natural del diente.",
            },
            {
                "nombre": "Extracción Dental Simple",
                "precio": 90.00, "adelanto": 30.00, "duracion": 45,
                "descripcion": "Retiro de una pieza dental dañada o infectada sin complicaciones.",
            },
        ],
    },
    {
        "especialidad": "Estética Dental",
        "candidatos": ["estetica dental"],
        "descripcion": "Mejoramos tu sonrisa con blanqueamiento, carillas y diseños personalizados.",
        "tratamientos": [
            {
                "nombre": "Blanqueamiento Dental LED",
                "precio": 250.00, "adelanto": 50.00, "duracion": 60,
                "descripcion": "Aclarado del tono dental con luz LED, con resultados visibles.",
            },
        ],
    },
    {
        "especialidad": "Ortodoncia",
        "candidatos": ["ortodoncia"],
        "descripcion": "Alineamos tus dientes con brackets y alineadores para una sonrisa armoniosa.",
        "tratamientos": [
            {
                "nombre": "Instalación de Brackets",
                "precio": 800.00, "adelanto": 100.00, "duracion": 60,
                "descripcion": "Colocación de brackets para iniciar el tratamiento de ortodoncia.",
            },
        ],
    },
    {
        "especialidad": "Endodoncia",
        "candidatos": ["endodoncia"],
        "descripcion": "Tratamiento de conductos que salva piezas dentales infectadas o muy dañadas.",
        "tratamientos": [
            {
                "nombre": "Tratamiento de Conducto (Endodoncia)",
                "precio": 200.00, "adelanto": 50.00, "duracion": 60,
                "descripcion": "Elimina la infección del nervio dental y preserva la pieza.",
            },
        ],
    },
    {
        "especialidad": "Radiología",
        "candidatos": ["radiologia", "diagnostico por imagenes", "radiologia e imagen 3d"],
        "descripcion": "Radiología y procedimientos guiados por imágenes para diagnóstico y tratamiento.",
        "tratamientos": [
            {
                "nombre": "Radiografía Dental Periapical",
                "precio": 30.00, "adelanto": 30.00, "duracion": 15,
                "descripcion": "Imagen de la pieza dental y su raíz para un diagnóstico preciso.",
            },
            {
                "nombre": "Angioplastia y Colocación de Stent",
                "precio": 1500.00, "adelanto": 400.00, "duracion": 60,
                "descripcion": "Apertura de arterias obstruidas mediante balón y colocación de malla metálica (stent) guiada por fluoroscopia o tomografía.",
            },
            {
                "nombre": "Embolización Vascular (Aneurismas / Miomas)",
                "precio": 1800.00, "adelanto": 500.00, "duracion": 90,
                "descripcion": "Oclusión selectiva de vasos sanguíneos con coils o sustancias embolizantes para tratar aneurismas o reducir miomas.",
            },
            {
                "nombre": "Quimioembolización",
                "precio": 2200.00, "adelanto": 600.00, "duracion": 90,
                "descripcion": "Inyección directa de quimioterapia y agentes oclusivos en las arterias que nutren lesiones tumorales.",
            },
            {
                "nombre": "Drenaje Percutáneo de Abscesos y Colecciones",
                "precio": 450.00, "adelanto": 120.00, "duracion": 45,
                "descripcion": "Evacuación guiada por ecografía o tomografía de colecciones infectadas mediante catéter percutáneo.",
            },
            {
                "nombre": "Infiltración y Bloqueo del Dolor Guiado por Imágenes",
                "precio": 250.00, "adelanto": 60.00, "duracion": 30,
                "descripcion": "Inyección precisa de antiinflamatorios y analgésicos en articulaciones o columna vertebral para el alivio del dolor crónico.",
            },
            {
                "nombre": "Ablación por Radiofrecuencia / Microondas",
                "precio": 1600.00, "adelanto": 450.00, "duracion": 60,
                "descripcion": "Destrucción térmica localizada de tumores mediante aguja especial guiada por imágenes tomográficas o ecográficas.",
            },
            {
                "nombre": "Radioterapia de Haz Externo / Braquiterapia",
                "precio": 2000.00, "adelanto": 500.00, "duracion": 60,
                "descripcion": "Planificación y aplicación de radiación ionizante milimétrica dirigida para tratamiento de tumores o colocación de fuentes radiactivas internas.",
            },
        ],
    },
    {
        "especialidad": "Implantología",
        "candidatos": ["implantologia"],
        "descripcion": "Reposición de piezas dentales con implantes de titanio y prótesis fijas.",
        "tratamientos": [
            {
                "nombre": "Implante Unitario",
                "precio": 1200.00, "adelanto": 300.00, "duracion": 60,
                "descripcion": "Reemplazo de un solo diente mediante un implante y una corona independiente. No desgasta los dientes vecinos.",
            },
            {
                "nombre": "Puente sobre Implantes",
                "precio": 2800.00, "adelanto": 700.00, "duracion": 90,
                "descripcion": "Reposición de varias piezas seguidas mediante un puente fijo anclado a implantes, sin desgastar dientes sanos.",
            },
            {
                "nombre": "Prótesis Híbrida (All-on-4 / All-on-6)",
                "precio": 6500.00, "adelanto": 1500.00, "duracion": 120,
                "descripcion": "Rehabilitación completa de una arcada sobre 4 o 6 implantes estratégicamente colocados. Dentadura fija que no se mueve.",
            },
            {
                "nombre": "Sobredentadura sobre Implantes",
                "precio": 3500.00, "adelanto": 800.00, "duracion": 90,
                "descripcion": "Prótesis completa sujeta a los implantes con sistema de anclaje (retech o barras). Estable y removible para una fácil limpieza.",
            },
        ],
    },
    {
        "especialidad": "Cirugía Oral",
        "candidatos": ["cirugia oral"],
        "descripcion": "Procedimientos quirúrgicos de la cavidad bucal y los maxilares.",
        "tratamientos": [
            {
                "nombre": "Extracción de Muela del Juicio (Tercer Molar)",
                "precio": 250.00, "adelanto": 50.00, "duracion": 45,
                "descripcion": "Procedimiento para extraer molares retenidos, impactados en el hueso o que causan dolor e infecciones.",
            },
            {
                "nombre": "Extracción Dental Compleja / Exodoncia",
                "precio": 150.00, "adelanto": 40.00, "duracion": 40,
                "descripcion": "Retirada de dientes destruidos por caries profundas, fracturados, supernumerarios o por indicación ortodóntica.",
            },
            {
                "nombre": "Injerto Óseos y Elevación de Seno Maxilar",
                "precio": 900.00, "adelanto": 250.00, "duracion": 60,
                "descripcion": "Regeneración del volumen de hueso perdido en los maxilares para permitir la colocación segura de implantes.",
            },
            {
                "nombre": "Apicectomía (Cirugía Endodóntica)",
                "precio": 600.00, "adelanto": 150.00, "duracion": 60,
                "descripcion": "Eliminación quirúrgica de la punta de la raíz dental y del tejido infectado tras el fallo de una endodoncia previa.",
            },
            {
                "nombre": "Frenectomía (Labial o Lingual)",
                "precio": 200.00, "adelanto": 50.00, "duracion": 30,
                "descripcion": "Reubicación o corte de frenillos que afectan el habla, la movilidad de la lengua o generan separación dental.",
            },
            {
                "nombre": "Biopsia Bukal y Análisis Patológico",
                "precio": 300.00, "adelanto": 80.00, "duracion": 30,
                "descripcion": "Toma de muestra de tejido bucal en encía, lengua o mejilla para estudio histopatológico en laboratorio.",
            },
            {
                "nombre": "Drenaje de Absceso y Enucleación de Quiste Maxilar",
                "precio": 350.00, "adelanto": 100.00, "duracion": 45,
                "descripcion": "Apertura y descontaminación de infecciones agudas, o remoción quirúrgica de sacos quísticos en los maxilares.",
            },
        ],
    },
    {
        "especialidad": "Periodoncia",
        "candidatos": ["periodoncia"],
        "descripcion": "Tratamiento de las encías y los tejidos de soporte dental.",
        "tratamientos": [
            {
                "nombre": "Profilaxis Dental Profunda",
                "precio": 90.00, "adelanto": 30.00, "duracion": 30,
                "descripcion": "Limpieza profesional especializada para eliminar la placa bacteriana y el sarro superficial por encima de la línea de la encía.",
            },
            {
                "nombre": "Raspado y Alisado Radicular (Curetaje)",
                "precio": 200.00, "adelanto": 50.00, "duracion": 60,
                "descripcion": "Limpieza profunda de sarro y bacterias debajo de la encía dentro de las bolsas periodontales, alisando la raíz para favorecer su re-adherencia.",
            },
            {
                "nombre": "Cirugía de Colgajo Periodontal",
                "precio": 550.00, "adelanto": 150.00, "duracion": 60,
                "descripcion": "Levantamiento temporal de la encía para acceder a raíces profundas, limpiar infección avanzada y suturar el tejido en su posición correcta.",
            },
            {
                "nombre": "Injerto de Tejido Blando (Cirugía Plástica Periodontal)",
                "precio": 700.00, "adelanto": 200.00, "duracion": 60,
                "descripcion": "Colocación de tejido del paladar para cubrir raíces expuestas por recesión gingival, reduciendo sensibilidad y mejorando la estética.",
            },
            {
                "nombre": "Injertos Óseos y Regeneración Tisular Guiada (RTG)",
                "precio": 950.00, "adelanto": 300.00, "duracion": 90,
                "descripcion": "Uso de materiales biológicos y membranas para rellenar defectos óseos y estimular la regeneración de tejidos de soporte perdidos.",
            },
            {
                "nombre": "Mantenimiento Periodontal",
                "precio": 100.00, "adelanto": 30.00, "duracion": 30,
                "descripcion": "Sesión de control y limpieza periódica programada (cada 3 a 6 meses) para supervisar la salud de las encías y evitar recaídas.",
            },
        ],
    },
    {
        "especialidad": "Odontopediatría",
        "candidatos": ["odontopediatria"],
        "descripcion": "Odontología para niños: prevención y tratamiento de la salud bucal infantil.",
        "tratamientos": [
            {
                "nombre": "Profilaxis Infantil y Aplicación de Flúor",
                "precio": 70.00, "adelanto": 20.00, "duracion": 30,
                "descripcion": "Limpieza dental para niños, enseñanza de cepillado y aplicación de barniz/gel de flúor para fortalecer el esmalte contra las caries.",
            },
            {
                "nombre": "Sellantes de Fosas y Fisuras (por pieza)",
                "precio": 50.00, "adelanto": 15.00, "duracion": 20,
                "descripcion": "Recubrimiento protector de resina en los surcos profundos de molares para evitar la acumulación de placa y la formación de caries.",
            },
            {
                "nombre": "Obturación Pediátrica (Cura y Resina)",
                "precio": 80.00, "adelanto": 20.00, "duracion": 30,
                "descripcion": "Eliminación de caries en dientes temporales o permanentes jóvenes y restauración estética con resina del color del diente.",
            },
            {
                "nombre": "Corona Pediátrica (Acero Inoxidable / Estética)",
                "precio": 180.00, "adelanto": 50.00, "duracion": 45,
                "descripcion": "Colocación de funda o corona infantil para proteger y restaurar la función de un diente temporal con gran destrucción.",
            },
            {
                "nombre": "Pulpotomía / Pulpectomía (Endodoncia Infantil)",
                "precio": 120.00, "adelanto": 30.00, "duracion": 45,
                "descripcion": "Tratamiento del nervio en dientes de leche afectados por caries profundas para prevenir dolor, infecciones y extracciones prematuras.",
            },
            {
                "nombre": "Mantenedor de Espacio (Fijo o Removible)",
                "precio": 250.00, "adelanto": 70.00, "duracion": 45,
                "descripcion": "Aparato diseñado para conservar la brecha de un diente de leche perdido prematuramente y permitir la correcta erupción del definitivo.",
            },
            {
                "nombre": "Atención Infantil con Sedación Consciente (Óxido Nitroso)",
                "precio": 200.00, "adelanto": 50.00, "duracion": 45,
                "descripcion": "Manejo de conducta y relajación con gas de la risa para pacientes pediátricos temerosos o ansiosos durante el procedimiento.",
            },
        ],
    },
    {
        "especialidad": "Rehabilitación Oral",
        "candidatos": ["rehabilitacion oral"],
        "descripcion": "Restauración de la función y estética dental con coronas, puentes y prótesis.",
        "tratamientos": [
            {
                "nombre": "Corona Dental (Circonio / Porcelana / Metal-Porcelana)",
                "precio": 450.00, "adelanto": 100.00, "duracion": 60,
                "descripcion": "Funda a medida que recubre un diente muy destruido o debilitado para devolverle su forma, fuerza y apariencia estética.",
            },
            {
                "nombre": "Puente Dental Fijo (por unidad o pieza)",
                "precio": 400.00, "adelanto": 100.00, "duracion": 60,
                "descripcion": "Estructura fija que se apoya en los dientes vecinos sanos para cubrir el espacio de uno o más dientes ausentes.",
            },
            {
                "nombre": "Carillas de Porcelana / Resina (Veneers)",
                "precio": 500.00, "adelanto": 120.00, "duracion": 60,
                "descripcion": "Láminas estéticas adheridas a la parte frontal de los dientes para corregir la forma, color, tamaño y alineación.",
            },
            {
                "nombre": "Incrustación Dental (Inlay / Onlay / Overlay)",
                "precio": 300.00, "adelanto": 80.00, "duracion": 45,
                "descripcion": "Restauración rígida a medida para cavidades o destrucciones extensas donde una resina convencional no es suficiente.",
            },
            {
                "nombre": "Prótesis Parcial Removible (Metálica / Flexible / Acrílica)",
                "precio": 450.00, "adelanto": 100.00, "duracion": 45,
                "descripcion": "Aparato removible para reemplazar varios dientes perdidos, sujetándose a las piezas dentales mediante retenedores estéticos o metálicos.",
            },
            {
                "nombre": "Prótesis Total / Dentadura Completa (por arcada)",
                "precio": 600.00, "adelanto": 150.00, "duracion": 60,
                "descripcion": "Rehabilitación acrílica completa diseñada para pacientes que han perdido la totalidad de sus dientes en una o ambas arcadas.",
            },
            {
                "nombre": "Diseño de Sonrisa Digital (Smile Design) y Rehabilitación Integral",
                "precio": 250.00, "adelanto": 50.00, "duracion": 45,
                "descripcion": "Planificación digital y clínica personalizada para transformar la estética y funcionalidad de la dentadura mediante carillas, coronas y alineación.",
            },
            {
                "nombre": "Férula Miorelajante / Placa Neuromiorrelajante (Anti-Bruxismo)",
                "precio": 280.00, "adelanto": 70.00, "duracion": 45,
                "descripcion": "Aparato de acrílico rígido a medida para proteger los dientes del desgaste nocturno, relajar los músculos masticatorios y aliviar la ATM.",
            },
        ],
    },
]


def _asegurar_columnas(cur):
    """Garantiza las columnas usadas por el seed (idempotente)."""
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS precio_base NUMERIC(10,2)")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS adelanto NUMERIC(10,2)")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS duracion_minutos INTEGER")
    cur.execute("ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE")
    cur.execute(
        "ALTER TABLE tratamientos ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()"
    )


def _resolver_especialidad(cur, grupo):
    """Devuelve el id de la especialidad del grupo, creándola si no existe."""
    cur.execute("SELECT id, nombre FROM especialidades")
    filas = cur.fetchall()
    candidatos = [_norm(c) for c in grupo["candidatos"]]

    # Coincidencia exacta normalizada.
    for f in filas:
        if _norm(f["nombre"]) in candidatos:
            return f["id"], False

    # Coincidencia por contención (p. ej. "Odontología General").
    for f in filas:
        nf = _norm(f["nombre"])
        for c in candidatos:
            if c and (c in nf or nf in c):
                return f["id"], False

    # No existe: se crea.
    cur.execute(
        "INSERT INTO especialidades (nombre, descripcion, estado, adelanto) "
        "VALUES (%s, %s, 'activo', 0) RETURNING id",
        (grupo["especialidad"], grupo.get("descripcion")),
    )
    return cur.fetchone()["id"], True


def main():
    conn = get_connection()
    cur = conn.cursor()
    _asegurar_columnas(cur)

    insertados = actualizados = creadas = 0

    for grupo in GRUPOS:
        esp_id, creada = _resolver_especialidad(cur, grupo)
        if creada:
            creadas += 1
            print(f"  + Especialidad creada: {grupo['especialidad']} (id={esp_id})")

        for t in grupo["tratamientos"]:
            cur.execute(
                "SELECT id_tratamiento FROM tratamientos "
                "WHERE id_especialidad = %s AND lower(nombre) = lower(%s)",
                (esp_id, t["nombre"]),
            )
            existente = cur.fetchone()

            if existente:
                cur.execute(
                    "UPDATE tratamientos SET descripcion=%s, precio_base=%s, "
                    "adelanto=%s, duracion_minutos=%s, activo=TRUE "
                    "WHERE id_tratamiento=%s",
                    (t["descripcion"], t["precio"], t["adelanto"],
                     t["duracion"], existente["id_tratamiento"]),
                )
                actualizados += 1
                print(f"    ~ Actualizado: {t['nombre']}")
            else:
                cur.execute(
                    "INSERT INTO tratamientos (id_especialidad, nombre, descripcion, "
                    "precio_base, adelanto, duracion_minutos, activo) "
                    "VALUES (%s, %s, %s, %s, %s, %s, TRUE)",
                    (esp_id, t["nombre"], t["descripcion"], t["precio"],
                     t["adelanto"], t["duracion"]),
                )
                insertados += 1
                print(f"    + Insertado: {t['nombre']}")

    conn.commit()
    conn.close()
    print(
        f"\nListo. Especialidades creadas: {creadas} | "
        f"Tratamientos insertados: {insertados} | "
        f"actualizados: {actualizados}"
    )


if __name__ == "__main__":
    main()
