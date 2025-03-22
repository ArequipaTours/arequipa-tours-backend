import jwt
import datetime
from functools import wraps
from bson.objectid import ObjectId
from flask import Blueprint, request, flash, redirect, url_for, current_app, render_template, jsonify, send_file
from config import Config
from datetime import datetime, timedelta
import pytz
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4  # Solo referencia; usaremos tamaño personalizado


ventanilla_bp = Blueprint('ventanilla', __name__, url_prefix='/ventanilla')

def ventanilla_required(f):
    """
    Decorador que:
      - Lee la cookie 'token'
      - Decodifica el JWT
      - Verifica que el rol sea 'ventanilla'
      - Inserta en request.user_payload los datos del token
      - En caso de error (token inválido/expirado o rol incorrecto), redirige al login.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.cookies.get('token')
        if not token:
            flash("No se encontró el token, inicia sesión por favor.", "danger")
            return redirect(url_for('auth.login'))
        
        try:
            payload = jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            flash("Tu sesión ha expirado, inicia sesión nuevamente.", "warning")
            return redirect(url_for('auth.login'))
        except jwt.InvalidTokenError:
            flash("Token inválido. Inicia sesión nuevamente.", "danger")
            return redirect(url_for('auth.login'))
        
        if payload.get('rol') != 'ventanilla':
            flash("No tienes permisos para acceder (se requiere rol 'ventanilla').", "danger")
            return redirect(url_for('auth.login'))
        
        request.user_payload = payload
        return f(*args, **kwargs)
    return decorated_function


@ventanilla_bp.route('/dashboard')
@ventanilla_required
def cajero_dashboard():
    """
    Muestra el dashboard para el usuario de ventanilla.
    Se filtra por el origen asignado al usuario por defecto, pero se permite
    un filtro opcional "origen" para que el usuario pueda buscar viajes de otros orígenes.
    Para el cajero de "El Alto", se muestran viajes con origen "El Alto" o 
    aquellos de "La Paz" con parada_intermedia "El Alto" (excluyendo los que ya tienen papeleta generada).
    Además, si se filtra por "El Alto" se suma +0.5 hora a la hora de viajes de "La Paz" con parada_intermedia "El Alto".
    """
    mongo = current_app.mongo
    user_payload = request.user_payload
    user_id = user_payload.get('user_id')

    user_doc = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not user_doc:
        flash("No se encontró el usuario en la base de datos.", "danger")
        return redirect(url_for('auth.logout'))
    
    default_origen = user_doc.get('origen')
    selected_origen = request.args.get('origen', default_origen).strip()
    
    bolivia_tz = pytz.timezone("America/La_Paz")
    now_bo = datetime.now(bolivia_tz)
    today_str = now_bo.strftime("%Y-%m-%d")
    current_time = now_bo.strftime("%H:%M")

    # Para mostrar la fecha en texto (ej. "20 de marzo 2025")
    months = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo",
        6: "junio", 7: "julio", 8: "agosto", 9: "septiembre",
        10: "octubre", 11: "noviembre", 12: "diciembre"
    }
    current_date = f"{now_bo.day} de {months[now_bo.month]} {now_bo.year}"

    destino = request.args.get('destino', '').strip()
    fecha_filter = request.args.get('fecha', '').strip() or today_str
    hora_filter = request.args.get('hora', '').strip()

    # Construir la consulta excluyendo viajes cerrados
    if selected_origen == "El Alto":
        query = {
            "$and": [
                {"$or": [
                    {"origen": "El Alto"},
                    {"origen": "La Paz", "parada_intermedia": "El Alto"}
                ]},
                {"fecha": fecha_filter},
                {"$or": [
                    {"papeletaElAlto": {"$exists": False}},
                    {"papeletaElAlto": False}
                ]}
            ]
        }
    else:
        query = {
            "$and": [
                {"origen": selected_origen},
                {"fecha": fecha_filter},
                {"$or": [
                    {"papeleta": {"$exists": False}},
                    {"papeleta": False}
                ]}
            ]
        }

    if destino:
        query["destino"] = {"$regex": destino, "$options": "i"}
    if hora_filter:
        query["hora"] = hora_filter

    travels_cursor = mongo.db.viajes.find(query).sort("hora", 1)
    travels = list(travels_cursor)

    # Ajustar hora +0.5 h si es El Alto intermedio
    if selected_origen == "El Alto":
        for v in travels:
            if v.get("origen") == "La Paz" and v.get("parada_intermedia") == "El Alto":
                v["origen"] = "El Alto"
                try:
                    dt_hora = datetime.strptime(v.get("hora", ""), "%H:%M")
                    dt_plus = dt_hora + timedelta(hours=0.5)
                    v["hora"] = dt_plus.strftime("%H:%M")
                except:
                    pass

    return render_template(
        'dashboard_ventanilla.html',
        user=user_doc,
        travels=travels,
        current_time=current_time,
        current_date=current_date
    )


@ventanilla_bp.route('/vender/<viaje_id>', methods=['GET'])
@ventanilla_required
def vender_boletos(viaje_id):
    """
    Carga la información del viaje para la venta de boletos.
    Antes de cargar la vista, se verifica que el viaje no esté cerrado para el tipo de venta correspondiente.
    Si ya está cerrado, se redirige al dashboard con el mensaje "Viaje ya cerrado".
    """
    mongo = current_app.mongo

    try:
        viaje = mongo.db.viajes.find_one({"_id": ObjectId(viaje_id)})
    except Exception as e:
        flash("ID de viaje inválido.", "danger")
        return redirect(url_for('ventanilla.cajero_dashboard'))

    if not viaje:
        flash("No se encontró el viaje solicitado.", "danger")
        return redirect(url_for('ventanilla.cajero_dashboard'))

   # Verificar si el viaje ya está cerrado solo para el origen correspondiente
    user_payload = request.user_payload
    user_doc = mongo.db.users.find_one({"_id": ObjectId(user_payload.get("user_id"))})
    user_origin = user_doc.get("origen", "").strip().lower()
    viaje_origen = viaje.get("origen", "").strip().lower()

    # Si el viaje es desde La Paz y el usuario está vendiendo para La Paz
    if viaje_origen == "la paz" and user_origin == "la paz":
        if viaje.get("estado") == "generado" and viaje.get("papeleta") is True:
            flash("Viaje ya cerrado. No se pueden vender más boletos desde La Paz.", "danger")
        return redirect(url_for('ventanilla.cajero_dashboard'))

    # Si el viaje es desde El Alto y el usuario está vendiendo para El Alto
    elif viaje_origen == "el alto" and user_origin == "el alto":
        if viaje.get("estado_el_alto") == "generado" and viaje.get("papeletaElAlto") is True:
            flash("Viaje ya cerrado. No se pueden vender más boletos desde El Alto.", "danger")
        return redirect(url_for('ventanilla.cajero_dashboard'))

# En cualquier otro caso, permitir la venta

    
    user_payload = request.user_payload
    user_doc = mongo.db.users.find_one({"_id": ObjectId(user_payload.get("user_id"))})
    

    viaje['_id'] = str(viaje['_id'])

    # Procesar asientos del bus
    seats = viaje.get("bus", {}).get("estructura_asientos", [])
    for s in seats:
        s["floor"] = int(s.get("floor", 1))
        s["row"]   = int(s.get("row", 0))
        s["col"]   = int(s.get("col", 0))
        s["status"] = "ocupado" if s.get("status", "").lower() == "ocupado" else "disponible"

    floors = {}
    for seat in seats:
        floor = seat["floor"]
        if floor not in floors:
            floors[floor] = {"normal": [], "extra": []}
        if seat.get("isExtra", False):
            floors[floor]["extra"].append(seat)
        else:
            floors[floor]["normal"].append(seat)

    for fl in floors:
        floors[fl]["normal"].sort(key=lambda s: (s["row"], s["col"]))
    sorted_floors = sorted(floors.items(), key=lambda x: x[0], reverse=True)

    return render_template(
        'venta_boletos.html',
        viaje=viaje,
        sorted_floors=sorted_floors,
        user=user_doc
        
    )

@ventanilla_bp.route('/confirmar_impresion/<viaje_id>', methods=['POST'])
@ventanilla_required
def confirmar_impresion(viaje_id):
    """
    Confirma la compra de asientos (boletos) de forma atómica para evitar duplicados:
      - Recibe JSON con { asientos: [...], payment, carril, subOrigen }.
      - Verifica que el viaje no esté cerrado.
      - Para cada asiento, usa find_one_and_update con un filtro que obliga
        a que el asiento NO esté ocupado todavía. Si algún asiento falla,
        retorna error 409 ("Asiento ya fue ocupado").
      - Si todos los asientos se pueden 'ocupar', se inserta el documento
        de venta en la colección 'ventas'.
      - Retorna { success, venta_id } si todo OK, o un error si algo falla.

    NUEVA LÓGICA:
      - subOrigen se determina por el toggle del front-end.
      - Si subOrigen = "El Alto" (case-insensitive) y el viaje es La Paz -> El Alto,
        se asigna venta_doc["subOrigen"] = "El Alto".
      - De lo contrario, no se asigna subOrigen y se mantiene el origen real.
    """
    mongo = current_app.mongo

    data = request.get_json()
    sub_origen_val = data.get("subOrigen", "").strip()

    # 1) Buscar el viaje
    try:
        viaje = mongo.db.viajes.find_one({"_id": ObjectId(viaje_id)})
    except:
        return jsonify({"success": False, "msg": "ID de viaje inválido"}), 400

    if not viaje:
        return jsonify({"success": False, "msg": "Viaje no encontrado"}), 404

    if sub_origen_val.lower() == "el alto":
        if viaje.get("estado_el_alto") == "generado" and viaje.get("papeletaElAlto") is True:
            return jsonify({"success": False, "msg": "Viaje ya cerrado para El Alto"}), 409
    else:
        if viaje.get("estado") == "generado" and viaje.get("papeleta") is True:
            return jsonify({"success": False, "msg": "Viaje ya cerrado para La Paz"}), 409


    # 3) Leer el JSON del front-end
    data = request.get_json() or {}
    asientos_carrito = data.get("asientos", [])
    payment_method = data.get("payment", None)
    carril_value = data.get("carril", "").strip()
    sub_origen_val = data.get("subOrigen", "").strip()  # <-- Toggle

    # Validaciones
    if not asientos_carrito:
        return jsonify({"success": False, "msg": "No hay asientos en el carrito"}), 400
    if not payment_method:
        return jsonify({"success": False, "msg": "Debe seleccionar un medio de pago"}), 400
    if not carril_value:
        return jsonify({"success": False, "msg": "El campo 'carril' es obligatorio"}), 400

    # 4) Obtener datos del usuario (solo para "origen_venta" y "vendido_por")
    user_payload = request.user_payload
    user_id = user_payload.get('user_id')
    user_doc = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not user_doc:
        return jsonify({"success": False, "msg": "Usuario no encontrado"}), 400

    user_origen = user_doc.get("origen")  # Se usa en 'origen_venta'

    # 5) Determinar subOrigen SI el toggle dice "El Alto" Y el viaje coincide con (La Paz -> El Alto)
    sub_origen = None
    if (sub_origen_val.lower() == "el alto" and
        viaje.get("origen") == "La Paz" and
        viaje.get("parada_intermedia") == "El Alto"):
        sub_origen = "El Alto"

    # 6) Calcular total
    total = 0
    try:
        for asiento in asientos_carrito:
            total += float(asiento.get("price", 0))
    except:
        return jsonify({"success": False, "msg": "Precio inválido en alguno de los asientos"}), 400

    # 7) Ocupar los asientos de forma atómica
    from pymongo import ReturnDocument
    for asiento_data in asientos_carrito:
        seat_num = asiento_data.get("seatName")
        if not seat_num:
            return jsonify({"success": False, "msg": "Falta el número de asiento"}), 400

        result = mongo.db.viajes.find_one_and_update(
            {
                "_id": ObjectId(viaje_id),
                "bus.estructura_asientos": {
                    "$elemMatch": {
                        "seatNumber": seat_num,
                        "status": {"$ne": "ocupado"}
                    }
                }
            },
            {
                "$set": {
                    "bus.estructura_asientos.$.status": "ocupado"
                }
            },
            return_document=ReturnDocument.AFTER
        )

        if not result:
            return jsonify({"success": False,
                            "msg": f"Asiento {seat_num} ya está ocupado"}), 409

    # 8) Insertar la venta
    bus_info = viaje.get("bus", {})
    venta_doc = {
        "viaje_id": ObjectId(viaje_id),
        "fecha_venta": datetime.utcnow(),
        "asientos": asientos_carrito,
        "payment": payment_method,
        "total": total,
        "vendido_por": user_doc.get("nombre"),
        "origen_venta": user_origen,             # <-- Se mantiene
        "origen": viaje.get("origen"),           # Origen real del viaje
        "destino": viaje.get("destino"),
        "fecha_viaje": viaje.get("fecha"),
        "hora_viaje": viaje.get("hora"),
        "placa_bus": bus_info.get("placa", "N/A"),
        "carril": carril_value
    }
    if sub_origen:
        venta_doc["subOrigen"] = sub_origen

    result_insert = mongo.db.ventas.insert_one(venta_doc)
    new_sale_id = str(result_insert.inserted_id)

    return jsonify({
        "success": True,
        "msg": "Compra confirmada y boletos impresos",
        "venta_id": new_sale_id
    }), 200

@ventanilla_bp.route('/boletos/pdf/<venta_id>', methods=['GET'])
def generar_pdf_boletos(venta_id):
    """
    Genera un PDF con diseño tipo 'factura/boleta' en ancho 80 mm,
    altura variable (cada boleto se corta con PageBreak).

    Lógica diferenciada:
      - Si la venta tiene subOrigen (después de quitar espacios y en minúsculas)
        igual a "elalto", se asigna origen "El Alto" y se suma 30 min a la hora de salida.
      - Se muestra el valor real de "carril" en la tabla.
    """
    import os
    from io import BytesIO
    from flask import send_file
    from bson.objectid import ObjectId
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Image,
        PageBreak, Table, TableStyle
    )
    from reportlab.lib.pagesizes import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib import colors
    from datetime import datetime, timedelta

    mongo = current_app.mongo

    # 1) Buscar la venta
    venta_doc = mongo.db.ventas.find_one({"_id": ObjectId(venta_id)})
    if not venta_doc:
        return "Venta no encontrada", 404

    # 2) Extraer datos principales
    asientos      = venta_doc.get("asientos", [])
    origen_viaje  = venta_doc.get("origen", "N/A")
    destino_viaje = venta_doc.get("destino", "N/A")
    fecha_salida  = venta_doc.get("fecha_viaje", "N/A")
    hora_salida   = venta_doc.get("hora_viaje", "N/A")
    placa_bus     = venta_doc.get("placa_bus", "N/A")
    operario      = venta_doc.get("vendido_por", "N/A")
    suc_operario  = venta_doc.get("origen_venta", "N/A")

    # Recuperar subOrigen y carril
    sub_origen_val = venta_doc.get("subOrigen", "").strip()
    carril_value   = venta_doc.get("carril", "N/A")

    # Lógica diferenciada: Si el campo subOrigen (sin espacios y en minúsculas) es "elalto",
    # se interpreta que la venta se realizó desde El Alto.
    if sub_origen_val.replace(" ", "").lower() == "elalto":
        origen_viaje = "El Alto"
        try:
            dt_original = datetime.strptime(f"{fecha_salida} {hora_salida}", "%Y-%m-%d %H:%M")
            dt_plus = dt_original + timedelta(minutes=30)
            hora_salida = dt_plus.strftime("%H:%M")
        except:
            pass

    # 3) Configurar ancho 80 mm, alto 150 mm
    PAGE_WIDTH  = 80 * mm
    PAGE_HEIGHT = 155 * mm
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        leftMargin=5*mm,
        rightMargin=5*mm,
        topMargin=5*mm,
        bottomMargin=5*mm
    )

    # Estilos
    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle(
        'normal',
        fontName='Helvetica',
        fontSize=8,
        leading=10
    )
    style_bold_center = ParagraphStyle(
        'bold_center',
        parent=style_normal,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        fontSize=9
    )
    style_center = ParagraphStyle(
        'center',
        parent=style_normal,
        alignment=TA_CENTER
    )
    style_right_bold = ParagraphStyle(
        'right_bold',
        parent=style_normal,
        alignment=TA_RIGHT,
        fontName='Helvetica-Bold'
    )

    # Logo
    logo_path = os.path.join(current_app.root_path, 'static', 'images', 'arequipa.png')

    story = []

    # 4) Generar un boleto por cada asiento
    for asiento in asientos:
        pasajero    = asiento.get("passengerName", "N/A")
        ci_doc      = asiento.get("ci", "N/A")
        asiento_num = asiento.get("seatName", "N/A")
        precio      = asiento.get("price", "0.00")

        # ENCABEZADO (Logo y Título)
        try:
            img = Image(logo_path, width=50*mm, height=15*mm)
            img.hAlign = 'CENTER'
            story.append(img)
        except:
            pass

        story.append(Paragraph("COMPROBANTE DE BOLETO", style_bold_center))
        story.append(Spacer(1, 3))

        # Empresa y sucursal
        story.append(Paragraph("L. SINDICAL AREQUIPA", style_bold_center))
        story.append(Paragraph(f"SUC: {origen_viaje}", style_center))
        story.append(Spacer(1, 4))

        # Datos del pasajero
        data_pasajero = [
            [Paragraph("<b>NOMBRE:</b>", style_normal), Paragraph(pasajero, style_normal)],
            [Paragraph("<b>DOCUMENTO:</b>", style_normal), Paragraph(ci_doc, style_normal)]
        ]
        table_pasajero = Table(data_pasajero, colWidths=[
            (PAGE_WIDTH-10*mm)*0.4,
            (PAGE_WIDTH-10*mm)*0.6
        ])
        table_pasajero.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1, colors.black),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
        ]))
        story.append(table_pasajero)
        story.append(Spacer(1, 4))

        # CUADRO "CANT | DESCRIPCION | PRECIO | TOTAL BS."
        data_descripcion = [
            [
                Paragraph("<b>CANT</b>", style_normal),
                Paragraph("<b>DESCRIPCION</b>", style_normal),
                Paragraph("<b>PRECIO</b>", style_normal),
                Paragraph("<b>TOTAL BS.</b>", style_normal)
            ],
            ["1", "PASAJE(S)", precio, precio]
        ]
        table_desc = Table(data_descripcion, colWidths=[
            (PAGE_WIDTH-10*mm)*0.15,
            (PAGE_WIDTH-10*mm)*0.35,
            (PAGE_WIDTH-10*mm)*0.20,
            (PAGE_WIDTH-10*mm)*0.30
        ])
        table_desc.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1, colors.black),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.black),
            ('ALIGN', (2,0), (3,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
        ]))
        story.append(table_desc)
        story.append(Spacer(1, 6))

        # RECOMENDACIONES
        story.append(Paragraph("No se aceptan cambios ni devoluciones.", style_center))
        story.append(Paragraph("Estar 30 minutos antes de la salida.", style_center))
        story.append(Spacer(1, 6))

        # DATOS DEL VIAJE (incluye carril real)
        data_viaje = [
            [Paragraph("<b>FECHA DE SALIDA:</b>", style_normal), Paragraph(fecha_salida, style_normal)],
            [Paragraph("<b>HORA DE SALIDA:</b>", style_normal), Paragraph(hora_salida, style_normal)],
            [Paragraph("<b>ORIGEN:</b>", style_normal), Paragraph(origen_viaje, style_normal)],
            [Paragraph("<b>DESTINO:</b>", style_normal), Paragraph(destino_viaje, style_normal)],
            [Paragraph("<b>BUS:</b>", style_normal), Paragraph(placa_bus, style_normal)],
            [Paragraph("<b>CARRIL:</b>", style_normal), Paragraph(carril_value, style_normal)]
        ]
        table_viaje = Table(data_viaje, colWidths=[
            (PAGE_WIDTH-10*mm)*0.4,
            (PAGE_WIDTH-10*mm)*0.6
        ])
        table_viaje.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1, colors.black),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'TOP')
        ]))
        story.append(table_viaje)
        story.append(Spacer(1, 6))

        # ASIENTO + info pasajero (otra vez)
        seat_info = f"Asiento:({asiento_num}) {pasajero} CI:{ci_doc}"
        story.append(Paragraph(seat_info, style_normal))
        story.append(Spacer(1, 6))

        # DATOS DEL PERSONAL
        data_operario = [
            [Paragraph("<b>Vendido por:</b>", style_normal), Paragraph(operario, style_normal)],
            [Paragraph("<b>Origen Operario:</b>", style_normal), Paragraph(suc_operario, style_normal)]
        ]
        table_op = Table(data_operario, colWidths=[
            (PAGE_WIDTH-10*mm)*0.4,
            (PAGE_WIDTH-10*mm)*0.6
        ])
        table_op.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1, colors.black),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
        ]))
        story.append(table_op)
        story.append(Spacer(1, 8))

        # Forzar corte de la impresora (cada asiento = una "página")
        story.append(PageBreak())

    # 5) Construir PDF
    doc.build(story)
    pdf_buffer.seek(0)
    
    return send_file(pdf_buffer, mimetype='application/pdf')
