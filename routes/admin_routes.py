from flask import Blueprint, render_template, request, current_app, redirect, url_for, flash, jsonify, Response
import jwt
from functools import wraps
from werkzeug.security import generate_password_hash
from bson.objectid import ObjectId
from datetime import datetime
import json
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from io import BytesIO


admin_bp = Blueprint('admin', __name__)

# Decorador para endpoints accesibles por administradores y superadmin
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('token')
        if not token:
            return redirect(url_for('auth.login'))
        try:
            payload = jwt.decode(
                token,
                current_app.config['JWT_SECRET'],
                algorithms=[current_app.config['JWT_ALGORITHM']]
            )
        except jwt.ExpiredSignatureError:
            return redirect(url_for('auth.login'))
        except jwt.InvalidTokenError:
            return redirect(url_for('auth.login'))
        # Permite roles 'administrador' y 'superadmin'
        if payload.get('rol') not in ['administrador', 'superadmin']:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

# Decorador para endpoints exclusivos de superadmin
def superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('token')
        if not token:
            return redirect(url_for('auth.login'))
        try:
            payload = jwt.decode(
                token,
                current_app.config['JWT_SECRET'],
                algorithms=[current_app.config['JWT_ALGORITHM']]
            )
        except jwt.ExpiredSignatureError:
            return redirect(url_for('auth.login'))
        except jwt.InvalidTokenError:
            return redirect(url_for('auth.login'))
        # Solo permite rol 'superadmin'
        if payload.get('rol') != 'superadmin':
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

# Dashboard para Administrador (accesible por admin y superadmin)
@admin_bp.route('/dashboard/admin')
@admin_required
def admin_dashboard():
    """
    Dashboard que muestra la tabla de viajes filtrados por 
    (origen, destino, hora, fecha) con fecha de hoy por defecto,
    y las tarjetas con conteos de personal y buses.
    """
    from datetime import datetime
    import pytz

    mongo = current_app.mongo

    # Contar total de 'drivers' (personal)
    drivers_count = mongo.db.drivers.count_documents({})

    # Contar total de 'buses'
    buses_count = mongo.db.buses.count_documents({})

    # Obtener parámetros GET
    origen = request.args.get('origen', '').strip()
    destino = request.args.get('destino', '').strip()
    hora_param = request.args.get('hora', '').strip()
    fecha_param = request.args.get('fecha', '').strip()

    # Manejo de la fecha actual (si no ingresan nada)
    if not fecha_param:
        # Hora local de Bolivia (UTC-4)
        # Si no usas pytz, puedes simplemente restar 4h o 
        # usar datetime.now() directamente si te da la hora local.
        bolivia_tz = pytz.timezone("America/La_Paz")
        now_bo = datetime.now(bolivia_tz)
        fecha_param = now_bo.strftime('%Y-%m-%d')

    # Construimos el query
    query_params = {}
    if origen:
        query_params["origen"] = {"$regex": origen, "$options": "i"}
    if destino:
        query_params["destino"] = {"$regex": destino, "$options": "i"}
    # Filtro por fecha exacta
    query_params["fecha"] = fecha_param
    # Filtro por hora exacta (opcional)
    if hora_param:
        query_params["hora"] = hora_param

    # Consulta
    travels_today = list(mongo.db.viajes.find(query_params).sort("hora", 1))

    return render_template(
        "dashboard_admin.html",
        drivers_count=drivers_count,
        buses_count=buses_count,
        travels_today=travels_today,
        origen=origen,
        destino=destino,
        hora=hora_param,
        fecha=fecha_param
    )

@admin_bp.route('/qr/upload', methods=['POST'])
@admin_required
def upload_qr():
    """
    Sube la imagen del QR en binario a la colección 'qr'.
    Guarda la fecha de expiración. Reemplaza el anterior.
    """
    mongo = current_app.mongo

    qr_file = request.files.get('qrFile')
    expiration_str = request.form.get('qrExpiration')

    if not qr_file or not expiration_str:
        flash("Falta archivo o fecha de expiración.", "danger")
        return redirect(url_for('admin.admin_dashboard'))

    file_data = qr_file.read()
    if not file_data:
        flash("El archivo de imagen está vacío.", "danger")
        return redirect(url_for('admin.admin_dashboard'))

    mimetype = qr_file.mimetype or 'image/png'

    doc = {
        "image_data": file_data,
        "content_type": mimetype,
        "expiration": expiration_str,
        "created_at": datetime.utcnow()
    }

    # Elimina el QR anterior (mantener solo 1 doc)
    mongo.db.qr.delete_many({})
    mongo.db.qr.insert_one(doc)

    flash("¡QR actualizado correctamente!", "success")
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/qr/current', methods=['GET'])
@admin_required
def get_current_qr():
    """
    Retorna JSON con {success, qr_url, expiration} si hay QR.
    'qr_url' es 'data:image/...;base64,...' para un <img>.
    """
    mongo = current_app.mongo
    doc = mongo.db.qr.find_one({})
    if not doc:
        return jsonify({"success": False}), 200

    image_data = doc.get("image_data")
    if not image_data:
        return jsonify({"success": False}), 200

    b64_data = base64.b64encode(image_data).decode('utf-8')
    content_type = doc.get("content_type", "image/png")
    qr_url = f"data:{content_type};base64,{b64_data}"

    expiration = doc.get("expiration", "")
    return jsonify({
        "success": True,
        "qr_url": qr_url,
        "expiration": expiration
    }), 200


# Dashboard exclusivo para Superadmin
@admin_bp.route('/dashboard/superadmin')
@superadmin_required
def superadmin_dashboard():
    return render_template('dashboard_superadmin.html')

# Endpoint para registrar choferes/relevos (drivers)
# Se decida que esta funcionalidad sea exclusiva para el superadmin,
# por lo que se utiliza el decorador @superadmin_required.
@admin_bp.route('/drivers/register', methods=['GET', 'POST'])
@admin_required
def register_driver():
    if request.method == 'GET':
        return render_template('add_driver.html')
    
    # Recoger los datos del formulario
    nombre = request.form.get('nombre')
    ci = request.form.get('CI')
    telefono = request.form.get('telefono')
    rol = request.form.get('rol')  # "chofer" o "relevo"
    numero_licencia = request.form.get('numero_licencia')
    fecha_nacimiento = request.form.get('fecha_nacimiento')
    categoria_licencia = request.form.get('categoria_licencia')
    fecha_emision_licencia = request.form.get('fecha_emision_licencia')
    fecha_expiracion_licencia = request.form.get('fecha_expiracion_licencia')
    
    # Validar que todos los campos estén completos
    if not all([
        nombre, ci, telefono, rol, numero_licencia, fecha_nacimiento,
        categoria_licencia, fecha_emision_licencia, fecha_expiracion_licencia
    ]):
        return render_template('add_driver.html', error="Todos los campos son requeridos.")
    
    mongo = current_app.mongo
    # Verificar que no exista ya un driver con el mismo número de licencia
    existing_driver = mongo.db.drivers.find_one({'numero_licencia': numero_licencia})
    if existing_driver:
        return render_template('add_driver.html', error="Ya existe un chofer/relevo con ese número de licencia.")
    
    driver_data = {
        "nombre": nombre,
        "CI": ci,
        "telefono": telefono,
        "rol": rol,  # "chofer" o "relevo"
        "estado": "activo",  # Por defecto
        "numero_licencia": numero_licencia,

        "fecha_nacimiento": fecha_nacimiento,
        "categoria_licencia": categoria_licencia,
        "fecha_emision_licencia": fecha_emision_licencia,
        "fecha_expiracion_licencia": fecha_expiracion_licencia
    }
    
    mongo.db.drivers.insert_one(driver_data)
    return render_template('add_driver.html', success="Chofer/Relevo registrado correctamente.")
# Nuevo endpoint para que el superadmin cree usuarios (administrador y ventanilla)
@admin_bp.route('/users/register', methods=['GET', 'POST'])
@superadmin_required
def register_user():
    if request.method == 'GET':
        return render_template('add_user.html')
    
    # Recoger datos del formulario
    carnet = request.form.get('carnet')
    nombre = request.form.get('nombre')
    password = request.form.get('password')
    rol = request.form.get('rol')  # Solo se permitirá 'administrador' o 'ventanilla'
    
    if not carnet or not nombre or not password or not rol:
        return render_template('add_user.html', error="Todos los campos son requeridos.")
    
    # No permitir crear un usuario con rol 'superadmin'
    if rol == 'superadmin':
        return render_template('add_user.html', error="No se puede crear usuario con rol superadmin.")
    
    mongo = current_app.mongo
    existing_user = mongo.db.users.find_one({'carnet': carnet})
    if existing_user:
        return render_template('add_user.html', error="El número de carnet ya está registrado.")
    
    hashed_password = generate_password_hash(password)
    new_user = {
        "carnet": carnet,
        "nombre": nombre,
        "password": hashed_password,
        "rol": rol,
        "estado": "activo"
    }
    mongo.db.users.insert_one(new_user)
    return render_template('add_user.html', success="Usuario registrado correctamente.")



# Listar todos los drivers en una tabla
@admin_bp.route('/drivers/list', methods=['GET'])
@admin_required
def list_drivers():
    mongo = current_app.mongo
    drivers = list(mongo.db.drivers.find())
    return render_template('list_drivers.html', drivers=drivers)

# Editar un driver (CI no se puede modificar)
@admin_bp.route('/drivers/edit/<driver_id>', methods=['GET', 'POST'])
@admin_required
def edit_driver(driver_id):
    mongo = current_app.mongo
    driver = mongo.db.drivers.find_one({'_id': ObjectId(driver_id)})
    if not driver:
        return "Driver no encontrado", 404
    
    if request.method == 'GET':
        return render_template('edit_driver.html', driver=driver)
    
    # Recoger datos del formulario (CI no se actualiza)
    updated_data = {
        "nombre": request.form.get('nombre'),
        "telefono": request.form.get('telefono'),
        "rol": request.form.get('rol'),
        "numero_licencia": request.form.get('numero_licencia'),
        "edad": request.form.get('edad'),
        "fecha_nacimiento": request.form.get('fecha_nacimiento'),
        "categoria_licencia": request.form.get('categoria_licencia'),
        "fecha_emision_licencia": request.form.get('fecha_emision_licencia'),
        "fecha_expiracion_licencia": request.form.get('fecha_expiracion_licencia'),
        "estado": request.form.get('estado')
    }
    mongo.db.drivers.update_one({'_id': ObjectId(driver_id)}, {"$set": updated_data})
    return redirect(url_for('admin.list_drivers'))

# Eliminar un driver
@admin_bp.route('/drivers/delete/<driver_id>', methods=['POST'])
@admin_required
def delete_driver(driver_id):
    mongo = current_app.mongo
    mongo.db.drivers.delete_one({'_id': ObjectId(driver_id)})
    return redirect(url_for('admin.list_drivers'))


@admin_bp.route('/buses/list', methods=['GET'])
@admin_required
def list_buses():
    mongo = current_app.mongo
    buses = list(mongo.db.buses.find())
    return render_template('lista_buses.html', buses=buses)

@admin_bp.route('/buses/delete/<bus_id>', methods=['POST'])
@admin_required
def delete_bus(bus_id):
    mongo = current_app.mongo
    try:
        mongo.db.buses.delete_one({'_id': ObjectId(bus_id)})
        flash("Bus eliminado correctamente", "success")
    except Exception as e:
        flash("Error al eliminar el bus: " + str(e), "danger")
    return redirect(url_for('admin.list_buses'))


 

@admin_bp.route('/papeletas/list', methods=['GET'])
@admin_required
def list_papeletas():
    """
    Lista los viajes y, si el viaje es de La Paz, genera una fila adicional 
    con sub-origen El Alto (+1 hora).
    IMPORTANTE: ahora también incluye v["papeleta"] y v["estado"] 
    para habilitar o deshabilitar el botón "Imprimir".
    """
    mongo = current_app.mongo
    
    # Leer todos los viajes
    viajes = list(mongo.db.viajes.find())
    
    papeletas_rows = []
    
    for v in viajes:
        viaje_id = str(v.get("_id", ""))
        origen = v.get("origen", "N/A")
        destino = v.get("destino", "N/A")
        fecha_str = v.get("fecha", "N/A")  # "YYYY-MM-DD"
        hora_str  = v.get("hora", "N/A")   # "HH:MM"

        chofer_nombre = "N/A"
        chofer_id = v.get("chofer_id")
        if chofer_id:
            chofer_doc = mongo.db.drivers.find_one({"_id": chofer_id})
            if chofer_doc:
                chofer_nombre = chofer_doc.get("nombre", "N/A")

        bus_doc = v.get("bus", {})
        bus_placa = bus_doc.get("placa", "N/A")
        
        # Estado del viaje
        estado = v.get("estado", "pendiente")

        # <-- LO IMPORTANTE -->
        # Recupera el bool "papeleta" (True/False). Si no existe, asume False
        papeleta_flag = v.get("papeleta", False)

        # Fila principal
        row_main = {
            "chofer": chofer_nombre,
            "bus": bus_placa,
            "origen": origen,
            "destino": destino,
            "fecha": fecha_str,
            "hora": hora_str,
            "estado": estado,
            "viaje_id": viaje_id,
            "papeleta": papeleta_flag
        }
        papeletas_rows.append(row_main)
        
        # Sub-viaje si origen == "La Paz"
        if origen == "La Paz":
            fecha_sub, hora_sub = sumar_una_hora(fecha_str, hora_str)
            row_sub = {
                "chofer": chofer_nombre,
                "bus": bus_placa,
                "origen": "El Alto",
                "destino": destino,
                "fecha": fecha_sub,
                "hora": hora_sub,
                "estado": estado,
                "viaje_id": viaje_id + "_ElAlto",
                "papeleta": papeleta_flag
            }
            papeletas_rows.append(row_sub)
    
    return render_template("papeletas_list.html", papeletas=papeletas_rows)


def sumar_una_hora(fecha_str, hora_str):
    """
    Suma 1 hora a la combinación fecha_str (YYYY-MM-DD) y hora_str (HH:MM).
    """
    from datetime import datetime, timedelta
    if fecha_str == "N/A" or hora_str == "N/A":
        return (fecha_str, hora_str)
    try:
        dt_original = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        return (fecha_str, hora_str)
    dt_suma = dt_original + timedelta(hours=1)
    return (dt_suma.strftime("%Y-%m-%d"), dt_suma.strftime("%H:%M"))


def sumar_una_hora(fecha_str, hora_str):
    """
    Suma 1 hora a la combinación fecha_str (YYYY-MM-DD) y hora_str (HH:MM).
    Si se pasa de medianoche, se incrementa la fecha en +1 día.
    Retorna (fecha_result_str, hora_result_str).
    """
    from datetime import datetime, timedelta
    
    if fecha_str == "N/A" or hora_str == "N/A":
        return (fecha_str, hora_str)
    
    # Combinar
    # Por defecto, se asume que la hora está en formato HH:MM
    # y la fecha en YYYY-MM-DD
    try:
        dt_original = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        # Por si hay error de parseo
        return (fecha_str, hora_str)
    
    dt_suma = dt_original + timedelta(hours=1)
    
    fecha_result_str = dt_suma.strftime("%Y-%m-%d")
    hora_result_str  = dt_suma.strftime("%H:%M")
    return (fecha_result_str, hora_result_str)


from pymongo import ReturnDocument

def get_next_sequence_value(mongo, name):
    """
    Busca en la colección 'counters' un documento con _id = name,
    y le hace $inc a la secuencia en 1.
    Si no existe, lo crea con seq=1.
    Devuelve el valor actualizado.
    """
    doc = mongo.db.counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return doc["seq"]

from pymongo import ReturnDocument

def get_next_papeleta_number(mongo):
    """
    Autoincrementa el contador en la colección 'counters'
    para la key '_id' = 'liquidations', y retorna un str con 7 dígitos
    Ej: '0000001', '0000002', etc.
    """
    doc = mongo.db.counters.find_one_and_update(
        {"_id": "liquidations"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    seq_value = doc["seq"]  # Entero actual
    # Convertimos a string con zfill(7)
    return str(seq_value).zfill(7)


@admin_bp.route('/papeleta/liquidacion/generate/<path:viaje_id>', methods=['POST'])
@admin_required
def generate_papeleta_liquidacion(viaje_id):
    """
    Genera un documento en 'liquidations' con:
      * numero_papeleta (7 dígitos)
      * propietario del bus (de la coleccion buses, via placa)
      * detalle_ventas con desglose de asientos por precio
      * total de ingresos, peaje, comision, neto...
    Además:
      - Si el viaje_id acaba con "_ElAlto", se quita ese sufijo, se filtran ventas con subOrigen="El Alto"
        y se marca viaje["papeletaElAlto"] = True, viaje["estado_el_alto"]="generado".
      - Si no tiene el sufijo, se generan ventas principales y se marca "papeleta"=True, estado="generado".
    """

    from bson.objectid import ObjectId
    from datetime import datetime
    mongo = current_app.mongo

    # 1) Ver si ends con _ElAlto => sub_origen
    sub_origen = None
    real_viaje_id = viaje_id
    if viaje_id.endswith("_ElAlto"):
        sub_origen = "ElAlto"
        real_viaje_id = viaje_id.replace("_ElAlto", "")

    data = request.get_json() or {}
    comision_pct = data.get("comision", 0)
    peaje_val = data.get("peaje", 0)

    try:
        comision_pct = float(comision_pct)
        peaje_val = float(peaje_val)
    except:
        return jsonify({"success": False, "msg": "comision o peaje inválido"}), 400

    # 2) Convertir a ObjectId la parte real
    try:
        obj_id = ObjectId(real_viaje_id)
    except:
        return jsonify({"success": False, "msg": f"ID inválido: {viaje_id}"}), 400

    # 3) Buscar el viaje
    viaje = mongo.db.viajes.find_one({"_id": obj_id})
    if not viaje:
        return jsonify({"success": False, "msg": "Viaje no encontrado"}), 404

    # 4) Obtener la placa del bus y propietario
    bus_info = viaje.get("bus", {})
    placa_bus = bus_info.get("placa")
    propietario_bus = "N/A"
    if placa_bus:
        bus_doc = mongo.db.buses.find_one({"placa": placa_bus})
        if bus_doc and "propietario" in bus_doc:
            propietario_bus = bus_doc["propietario"]

    # 5) Obtener el numero de papeleta autoincrementable (7 dígitos)
    numero_papeleta_str = get_next_papeleta_number(mongo)

    # 6) Datos del viaje
    fecha_viaje = viaje.get("fecha", "")
    hora_viaje = viaje.get("hora", "")
    origen_real = viaje.get("origen", "")
    destino = viaje.get("destino", "")

    # 7) Filtrar las ventas:
    #    subOrigen=ElAlto => "subOrigen":"El Alto"
    #    si no => subOrigen ausente o None => "ventas principales"
    query_ventas = {"viaje_id": obj_id}
    if sub_origen == "ElAlto":
        query_ventas["subOrigen"] = "El Alto"
    else:
        query_ventas["$or"] = [
            {"subOrigen": None},
            {"subOrigen": {"$exists": False}}
        ]

    ventas = list(mongo.db.ventas.find(query_ventas))
    if not ventas:
        return jsonify({"success": False, "msg": "No hay ventas para este origen"}), 200

    asientos_totales_vendidos = 0
    total_ingresos = 0.0
    detalle_ventas = []

    for venta in ventas:
        numero_venta = venta.get("numero_venta")
        if not numero_venta:
            numero_venta = str(venta["_id"])[-6:]

        asientos_esta_venta = venta.get("asientos", [])

        # Agrupamos asientos por precio => {"120":2, "100":4}, etc.
        precios_map = {}
        for seat in asientos_esta_venta:
            seat_price = seat.get("price", 0)
            price_str = str(seat_price)
            precios_map[price_str] = precios_map.get(price_str, 0) + 1

        cant_asientos = len(asientos_esta_venta)
        asientos_totales_vendidos += cant_asientos

        # Calcular subtotal de la venta
        subtotal_venta = float(venta.get("total", 0))
        if subtotal_venta == 0 and precios_map:
            subtotal_venta = sum(int(k)*v for k,v in precios_map.items())

        total_ingresos += subtotal_venta

        detalle_ventas.append({
            "numero_venta": numero_venta,
            "precios_vendidos": precios_map,
            "cant_asientos_vendidos": cant_asientos,
            "subtotal_venta_bs": round(subtotal_venta, 2)
        })

    # 8) Calcular comision y neto
    comision_val = round(total_ingresos * (comision_pct / 100), 2)
    neto = round(total_ingresos - comision_val - peaje_val, 2)

    # 9) Construir el documento "liquidation"
    #    Si sub_origen=ElAlto => en la liquidación figurará "origen":"El Alto"
    liquidation_doc = {
        "numero_papeleta": numero_papeleta_str,
        "viaje_id": obj_id,
        "fecha_generado": datetime.utcnow(),

        "fecha_viaje": fecha_viaje,
        "hora_viaje": hora_viaje,
        "origen": "El Alto" if sub_origen == "ElAlto" else origen_real,
        "destino": destino,
        "propietario_bus": propietario_bus,

        "detalle_ventas": detalle_ventas,

        "asientos_totales_vendidos": asientos_totales_vendidos,
        "total_ingresos": round(total_ingresos, 2),
        "comision_pct": comision_pct,
        "comision_val": comision_val,
        "peaje": peaje_val,
        "neto": neto,

        "sub_origen": "El Alto" if sub_origen == "ElAlto" else None
    }

    mongo.db.liquidations.insert_one(liquidation_doc)

    # 10) Actualizar el viaje => sub_origen=ElAlto => papeletaElAlto
    if sub_origen == "ElAlto":
        mongo.db.viajes.update_one(
            {"_id": obj_id},
            {"$set": {
                "papeletaElAlto": True,
                "estado_el_alto": "generado"
            }}
        )
    else:
        mongo.db.viajes.update_one(
            {"_id": obj_id},
            {"$set": {
                "papeleta": True,
                "estado": "generado"
            }}
        )

    # 11) Responder al front
    return jsonify({"success": True, "numero_papeleta": numero_papeleta_str})



@admin_bp.route('/buses/new', methods=['GET', 'POST'])
def new_bus():
    """
    Muestra el formulario de creación de buses (GET) 
    y procesa la creación (POST), 
    guardando en la colección 'buses' de MongoDB.
    """
    if request.method == 'GET':
        # Simplemente renderiza la plantilla
        return render_template('nuevo_bus.html')
    
    # Procesar POST
    try:
        placa = request.form.get('placa')
        modelo = request.form.get('modelo')
        propietario = request.form.get('propietario')
        estado = request.form.get('estado')
        pisos_str = request.form.get('pisos')       # "1" o "2"
        total_asientos = int(request.form.get('totalAsientos', 0))
        
        # 'estructura_asientos' es un JSON con la info de la grilla y asientos extra
        estructura_str = request.form.get('estructura_asientos')
        if estructura_str:
            estructura_asientos = json.loads(estructura_str)
        else:
            estructura_asientos = []
    
    except Exception as e:
        # Si hay error parseando la data
        return render_template('nuevo_bus.html', error=f"Error procesando los datos: {str(e)}")
    
    # Validar placa única
    existing = current_app.mongo.db.buses.find_one({"placa": placa})
    if existing:
        return render_template('nuevo_bus.html', error="Ya existe un bus registrado con esa placa")
    
    # Documento listo para insertar
    bus_doc = {
        "placa": placa,
        "modelo": modelo,
        "capacidad": total_asientos,              # Se guarda total de asientos
        "estructura_asientos": estructura_asientos,  
        "propietario": propietario,
        "estado": estado,
        "pisos": int(pisos_str)                   # Convertir a entero
    }
    
    try:
        current_app.mongo.db.buses.insert_one(bus_doc)
    except Exception as e:
        return render_template('nuevo_bus.html', error=f"Error al guardar en la base de datos: {str(e)}")
    
    # Mostrar mensaje y redirigir a la lista de buses
    flash("Bus registrado correctamente", "success")
    return redirect(url_for("admin.list_buses"))

from bson.objectid import ObjectId
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app

@admin_bp.route('/buses/edit/<bus_id>', methods=['GET', 'POST'])
def edit_bus(bus_id):
    mongo = current_app.mongo
    bus = mongo.db.buses.find_one({'_id': ObjectId(bus_id)})
    if not bus:
        flash("Bus no encontrado", "danger")
        return redirect(url_for('admin.list_buses'))
    
    if request.method == 'GET':
        # Renderizar plantilla de edición con los datos actuales del bus
        return render_template('editar_bus.html', bus=bus)
    
    # Procesamos POST: actualización
    try:
        # Recogemos campos editables (placa se mantiene, no editable)
        modelo = request.form.get('modelo')         # Ej: "VOLVO 9700"
        propietario = request.form.get('propietario')
        estado = request.form.get('estado')         # "disponible", "en mantenimiento", "no operativo"

        update_doc = {
            "modelo": modelo,
            "propietario": propietario,
            "estado": estado
        }
        mongo.db.buses.update_one({'_id': ObjectId(bus_id)}, {"$set": update_doc})
    except Exception as e:
        flash("Error al actualizar: " + str(e), "danger")
        return redirect(url_for('admin.edit_bus', bus_id=bus_id))
    
    flash("Bus actualizado correctamente", "success")
    return redirect(url_for('admin.list_buses'))


@admin_bp.route('/viajes/new', methods=['GET', 'POST'])
@admin_required
def new_viaje():
    mongo = current_app.mongo
    if request.method == 'GET':
        # Recuperar buses y drivers (para chofer, que se usará para chofer y relevo)
        buses = list(mongo.db.buses.find())
        drivers = list(mongo.db.drivers.find({"rol": "Chofer - Relevo"}))
        return render_template('nuevo_viaje.html', buses=buses, drivers=drivers)
    
    try:
        origen = request.form.get('origen')
        destino = request.form.get('destino')
        if origen == destino:
            flash("El origen y destino no pueden ser iguales.", "danger")
            return redirect(url_for('admin.new_viaje'))
        
        fecha = request.form.get('fecha')  # Formato YYYY-MM-DD
        hora = request.form.get('hora')    # Formato HH:MM
        bus_id = request.form.get('bus')
        tipoServicioViaje = request.form.getlist('tipoServicioViaje')
        # Se recoge un único personal (para chofer y relevo)
        personal_id = request.form.get('chofer')
        
        # Recuperar el bus seleccionado
        bus = mongo.db.buses.find_one({"_id": ObjectId(bus_id)})
        if not bus:
            flash("Bus no encontrado.", "danger")
            return redirect(url_for('admin.new_viaje'))
        
        # Recuperar el documento del personal de ventas (chofer/relevo)
        personal_doc = mongo.db.drivers.find_one({"_id": ObjectId(personal_id)}) if personal_id else None
        
        # Copiar la estructura de asientos del bus
        asientos = bus.get("estructura_asientos", [])
        asientos_copiados = [asiento.copy() for asiento in asientos]
        
        # Si el origen es La Paz, se añade una parada intermedia en El Alto con tiempo de traslado de 1 hora
        parada_intermedia = None
        tiempo_translado = None
        if origen == "La Paz":
            parada_intermedia = "El Alto"
            tiempo_translado = "30 minutos"
        
        viaje_doc = {
            "origen": origen,
            "destino": destino,
            "fecha": fecha,
            "hora": hora,
            "bus": {
                "placa": bus.get("placa"),
                "modelo": bus.get("modelo"),
                "pisos": bus.get("pisos"),
                "capacidad": bus.get("capacidad"),
                "estructura_asientos": asientos_copiados
            },
            "tipoServicioViaje": tipoServicioViaje,
            # Se asigna el mismo personal para chofer y relevo
            "chofer_id": ObjectId(personal_id) if personal_id else None,
            "chofer_licencia": personal_doc.get("numero_licencia") if personal_doc else None,
            "relevo_id": ObjectId(personal_id) if personal_id else None,
            "relevo_licencia": personal_doc.get("numero_licencia") if personal_doc else None,
            "parada_intermedia": parada_intermedia,
            "tiempo_translado": tiempo_translado,
            "fecha_registro": datetime.utcnow()
        }
        
        mongo.db.viajes.insert_one(viaje_doc)
    except Exception as e:
        flash("Error al registrar el viaje: " + str(e), "danger")
        return redirect(url_for('admin.new_viaje'))
    
    flash("Viaje registrado correctamente", "success")
    return redirect(url_for("admin.list_travels"))


@admin_bp.app_template_filter('format_date')
def format_date(value):
    from datetime import datetime
    try:
        # Suponiendo que 'value' es una cadena en formato YYYY-MM-DD
        dt = datetime.strptime(value, '%Y-%m-%d')
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        dia_semana = dias[dt.weekday()]
        return f"{dia_semana}, {dt.strftime('%d/%m/%Y')}"
    except Exception as e:
        return value


@admin_bp.route('/travels/list', methods=['GET'])
def list_travels():
    """
    Lista de viajes del día actual por defecto, con búsquedas opcionales.
    Sin paginación, sin "Cargar más".
    """
    from datetime import datetime
    mongo = current_app.mongo
    query_params = {}

    # Búsqueda parcial case-insensitive por 'origen'
    origen = request.args.get('origen', '').strip()
    if origen:
        query_params['origen'] = {"$regex": origen, "$options": "i"}

    # Búsqueda parcial case-insensitive por 'destino'
    destino = request.args.get('destino', '').strip()
    if destino:
        query_params['destino'] = {"$regex": destino, "$options": "i"}

    # Fecha
    fechaDesde = request.args.get('fechaDesde', '').strip()
    fechaHasta = request.args.get('fechaHasta', '').strip()

    # Si no han llenado nada de fecha => fecha de HOY
    if not fechaDesde and not fechaHasta:
        today_str = datetime.now().strftime('%Y-%m-%d')  # "YYYY-MM-DD"
        query_params['fecha'] = today_str
    else:
        # Si hay fechaDesde / fechaHasta, filtramos rango
        date_filter = {}
        if fechaDesde:
            date_filter["$gte"] = fechaDesde
        if fechaHasta:
            date_filter["$lte"] = fechaHasta
        if date_filter:
            query_params['fecha'] = date_filter

    # Consulta sin paginación
    travels = list(mongo.db.viajes.find(query_params).sort('_id', -1))

    return render_template(
        'viajes.html',
        travels=travels,
        origen=origen,
        destino=destino,
        fechaDesde=fechaDesde,
        fechaHasta=fechaHasta
    )



@admin_bp.route('/viajes/delete/<id>', methods=['GE=T', 'POST'])
def delete_viaje(id):
    mongo = current_app.mongo
    try:
        result = mongo.db.viajes.delete_one({"_id": ObjectId(id)})
        if result.deleted_count == 1:
            flash("Viaje eliminado correctamente.", "success")
        else:
            flash("No se encontró el viaje.", "danger")
    except Exception as e:
        flash("Error al eliminar el viaje: " + str(e), "danger")
    return redirect(url_for("admin.list_travels"))




@admin_bp.route('/ver_pasajes/<viaje_id>', methods=['GET'])
@admin_required
def ver_pasajes(viaje_id):
    """
    Visualiza la estructura del bus de un viaje.
    Muestra los asientos agrupados por piso y genera un mapa de pasajeros
    a partir de la información de ventas.
    """
    mongo = current_app.mongo
    viaje = mongo.db.viajes.find_one({"_id": ObjectId(viaje_id)})

    if not viaje:
        flash("Viaje no encontrado", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    # Asegurarse de que el viaje tenga la estructura esperada
    if "bus" in viaje and "estructura_asientos" in viaje["bus"]:
        for seat in viaje["bus"]["estructura_asientos"]:
            if "row" not in seat:
                seat["row"] = 0
            if "col" not in seat:
                seat["col"] = 0
    else:
        viaje["bus"] = {"estructura_asientos": []}

    # Recuperar todas las ventas asociadas a este viaje
    ventas = list(mongo.db.ventas.find({"viaje_id": ObjectId(viaje_id)}))
    
    passenger_map = {}
    for venta in ventas:
        vendedor = venta.get("vendido_por", "Desconocido")
        origen_venta = venta.get("origen_venta", "N/A")
        for asiento in venta.get("asientos", []):
            seat_num = asiento.get("seatName")
            if seat_num:
                asiento["vendido_por"] = vendedor  # Agregar el vendedor al asiento
                asiento["origen_venta"] = origen_venta  # Agregar el origen de venta
                passenger_map[seat_num] = asiento

    # Convertir _id a string para la plantilla
    viaje['_id'] = str(viaje['_id'])

    return render_template("ver_pasajes.html", viaje=viaje, passenger_map=passenger_map)

import os

@admin_bp.route("/lista_pasajeros_pdf/<viaje_id>", methods=["GET"])
def lista_pasajeros_pdf(viaje_id):
    """
    Genera un PDF con tantas filas como asientos tenga el bus + 2 filas extra.
    Cada fila muestra un pasajero (en orden recuperado de 'ventas') o en blanco.
    4 columnas: N°, Nombre Completo, CI/Pass, País.
    Fuerza la descarga.
    """

    mongo = current_app.mongo

    # 1) Buscar el viaje
    viaje = mongo.db.viajes.find_one({"_id": ObjectId(viaje_id)})
    if not viaje:
        flash("Viaje no encontrado", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    # Verificar estructura asientos
    if "bus" not in viaje or "estructura_asientos" not in viaje["bus"]:
        flash("Este viaje no tiene asientos definidos.", "warning")
        return redirect(url_for("admin.admin_dashboard"))

    seats_db = viaje["bus"]["estructura_asientos"]
    # Asegurar row/col
    for seat in seats_db:
        seat.setdefault("row", 0)
        seat.setdefault("col", 0)

    # 2) Conductor, Relevo, Placa
    chofer_id = viaje.get("chofer_id")
    relevo_id = viaje.get("relevo_id")

    chofer_doc = mongo.db.drivers.find_one({"_id": chofer_id}) if chofer_id else None
    relevo_doc = mongo.db.drivers.find_one({"_id": relevo_id}) if relevo_id else None

    chofer_nombre = chofer_doc["nombre"] if chofer_doc else "N/A"
    chofer_lic = chofer_doc["numero_licencia"] if chofer_doc else "N/A"
    relevo_nombre = relevo_doc["nombre"] if relevo_doc else "N/A"
    relevo_lic = relevo_doc["numero_licencia"] if relevo_doc else "N/A"
    bus_placa = viaje["bus"].get("placa", "N/A")

    # 3) Recuperar pasajeros en orden "ventas"
    ventas_cursor = mongo.db.ventas.find({"viaje_id": ObjectId(viaje_id)})
    pasajeros = []
    for venta in ventas_cursor:
        for asiento in venta.get("asientos", []):
            nombre = asiento.get("nombre") or asiento.get("passengerName") or ""
            ci = asiento.get("ci","")
            pais = asiento.get("pais","")
            pasajeros.append({
                "nombre": nombre,
                "ci": ci,
                "pais": pais
            })

    # 4) Nº total de filas = nº asientos + 2 extra
    total_asientos = len(seats_db)
    total_filas = total_asientos + 1

    # 5) Crear buffer
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    c.setTitle("Lista de Pasajeros")

    # Márgenes
    topMargin = 3 * cm
    bottomMargin = 2 * cm
    leftMargin = 2 * cm
    rightMargin = 2 * cm

    # 6) Dibujar encabezado
    current_y = page_height - topMargin

    c.setFont("Helvetica-Bold", 14)
    flota_title = "FLOTA AREQUIPA"
    flota_w = c.stringWidth(flota_title, "Helvetica-Bold", 14)
    c.drawString((page_width - flota_w)/2, current_y, flota_title)

    c.setFont("Helvetica", 11)
    current_y -= 1.0 * cm

    # Conductor / Relevo
    c.drawString(leftMargin, current_y, f"Conductor: {chofer_nombre}")
    c.drawString(page_width - rightMargin - 7*cm, current_y, f"N° Lic: {chofer_lic}")
    current_y -= 0.7*cm

    c.drawString(leftMargin, current_y, f"Relevo: {relevo_nombre}")
    c.drawString(page_width - rightMargin - 7*cm, current_y, f"N° Lic: {relevo_lic}")
    current_y -= 0.7*cm

    # Origen / Destino
    c.drawString(leftMargin, current_y, f"Origen: {viaje.get('origen','N/A')}")
    c.drawString(page_width - rightMargin - 7*cm, current_y, f"Destino: {viaje.get('destino','N/A')}")
    current_y -= 0.7*cm

    # Fecha / Hora
    fecha_str = viaje.get('fecha','N/A')
    hora_str = viaje.get('hora','N/A')
    c.drawString(leftMargin, current_y, f"Fecha: {fecha_str}")
    c.drawString(page_width - rightMargin - 7*cm, current_y, f"Hora Salida: {hora_str}")
    current_y -= 0.7*cm

    # Placa
    c.drawString(leftMargin, current_y, f"Placa: {bus_placa}")
    current_y -= 1.2 * cm

    # Título "LISTA DE PASAJEROS"
    c.setFont("Helvetica-Bold", 14)
    list_title = "LISTA DE PASAJEROS"
    list_w = c.stringWidth(list_title, "Helvetica-Bold", 14)
    c.drawString((page_width - list_w)/2, current_y, list_title)
    current_y -= 1.5 * cm

    # 7) Definir tabla 4 columnas: N°, Nombre, CI, País
    c.setFont("Helvetica-Bold", 10)
    headers = ["N°", "Nombre Completo", "C.I/Pass", "País"]
    col_widths = [1.0, 7.0, 3.0, 2.0]  # cm

    table_width = page_width - leftMargin - rightMargin
    sum_col = sum(col_widths)
    scale_factor = table_width / (sum_col*cm)
    col_positions = [leftMargin]
    for w in col_widths:
        col_positions.append(col_positions[-1] + w*cm*scale_factor)

    row_height = 1.2*cm
    usable_height = current_y - bottomMargin
    rows_per_page = int(usable_height // row_height)

    def draw_headers(c, cy):
        c.setFont("Helvetica-Bold", 10)
        for i, header in enumerate(headers):
            cell_w = col_positions[i+1] - col_positions[i]
            c.rect(col_positions[i], cy, cell_w, row_height, stroke=1, fill=0)
            text_w = c.stringWidth(header, "Helvetica-Bold", 10)
            x_text = col_positions[i] + (cell_w - text_w)/2
            y_text = cy + row_height/2 - 3
            c.drawString(x_text, y_text, header)

    def draw_row(c, cy, row_data):
        c.setFont("Helvetica", 10)
        for i, cell_text in enumerate(row_data):
            cell_w = col_positions[i+1] - col_positions[i]
            c.rect(col_positions[i], cy, cell_w, row_height, stroke=1, fill=0)
            text_w = c.stringWidth(cell_text, "Helvetica", 10)
            x_text = col_positions[i] + (cell_w - text_w)/2
            y_text = cy + row_height/2 - 3
            c.drawString(x_text, y_text, cell_text)

    # Dibujar la cabecera
    cabecera_y = current_y
    draw_headers(c, cabecera_y)
    current_y = cabecera_y - row_height

    # Función para salto de página
    def new_page():
        c.showPage()
        # Re-dibujar un encabezado mínimo
        new_y = page_height - topMargin
        # Ejemplo muy básico
        c.setFont("Helvetica-Bold", 14)
        flota_w = c.stringWidth(flota_title, "Helvetica-Bold", 14)
        c.drawString((page_width - flota_w)/2, new_y, flota_title)
        new_y -= 2*cm
        c.setFont("Helvetica-Bold", 10)
        draw_headers(c, new_y)
        new_y -= row_height
        return new_y

    # 8) Llenar filas => total_filas
    # pasajeros[] => en orden => para cada fila, si hay un pasajero => se imprime
    # si no => blanco
    index_pasajero = 0
    printed_rows = 0
    row_number = 1

    while printed_rows < total_filas:
        if current_y < bottomMargin:
            current_y = new_page()

        if index_pasajero < len(pasajeros):
            # Tomar el pasajero
            p = pasajeros[index_pasajero]
            nombre = p["nombre"]
            ci = p["ci"]
            pais = p["pais"]
            index_pasajero += 1
        else:
            # Fila vacía
            nombre, ci, pais = "", "", ""

        row_data = [
            str(row_number),
            nombre,
            ci,
            pais
        ]
        draw_row(c, current_y, row_data)
        current_y -= row_height
        row_number += 1
        printed_rows += 1

    # Terminar
    c.showPage()
    c.save()

    pdf_data = buffer.getvalue()
    buffer.close()

    # Guardar
    pdf_dir = os.path.join(current_app.root_path, "static", "pdf")
    if not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir)
    pdf_filename = f"lista_pasajeros_{viaje_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    pdf_path = os.path.join(pdf_dir, pdf_filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_data)

    # Forzar descarga
    response = Response(pdf_data, mimetype="application/pdf")
    response.headers["Content-Disposition"] = f"attachment; filename={pdf_filename}"
    return response



@admin_bp.route('/viajes/editar/<viaje_id>', methods=['GET', 'POST'])
@admin_required
def editar_viaje(viaje_id):
    """
    Permite editar un viaje. Los campos de origen y destino se muestran en modo readonly,
    mientras que se pueden modificar la fecha, hora, tipo de servicio (checkboxes), 
    y, de la información del bus, solo la placa. Además, se permite seleccionar nuevos 
    conductor y relevo.
    """
    mongo = current_app.mongo
    viaje = mongo.db.viajes.find_one({"_id": ObjectId(viaje_id)})
    if not viaje:
        flash("Viaje no encontrado", "danger")
        return redirect(url_for("admin.list_travels"))
    
    # Para seleccionar conductor/relevo, se obtiene la lista de drivers (por ejemplo, con rol "Chofer - Relevo")
    drivers = list(mongo.db.drivers.find({"rol": "Chofer - Relevo"}))
    
    if request.method == "GET":
        return render_template("editar_viaje.html", viaje=viaje, drivers=drivers)
    
    # POST: Recoger los campos editables
    new_fecha = request.form.get("fecha")
    new_hora = request.form.get("hora")
    new_tipoServicio = request.form.getlist("tipoServicioViaje")
    new_placa = request.form.get("placa")
    new_chofer_id = request.form.get("chofer")
    new_relevo_id = request.form.get("relevo")
    
    # Preparar el documento de actualización; solo se actualizan los campos editables
    update_doc = {
        "fecha": new_fecha,
        "hora": new_hora,
        "tipoServicioViaje": new_tipoServicio,
        "bus.placa": new_placa,
    }
    
    # Actualizamos el conductor y relevo si se selecciona alguno
    if new_chofer_id:
        update_doc["chofer_id"] = ObjectId(new_chofer_id)
        chofer_doc = mongo.db.drivers.find_one({"_id": ObjectId(new_chofer_id)})
        update_doc["chofer_licencia"] = chofer_doc.get("numero_licencia") if chofer_doc else None
    if new_relevo_id:
        update_doc["relevo_id"] = ObjectId(new_relevo_id)
        relevo_doc = mongo.db.drivers.find_one({"_id": ObjectId(new_relevo_id)})
        update_doc["relevo_licencia"] = relevo_doc.get("numero_licencia") if relevo_doc else None
    
    mongo.db.viajes.update_one({"_id": ObjectId(viaje_id)}, {"$set": update_doc})
    flash("Viaje actualizado correctamente.", "success")
    return redirect(url_for("admin.list_travels"))


@admin_bp.route('/papeletas/data', methods=['GET'])
@admin_required
def get_papeletas_data():
    """
    Retorna en formato JSON un 'chunk' de viajes/papeletas.
    Parámetros:
      - skip (int)
      - limit (int)
      - origen (str): Filtro por origen (usa regex, pero si es "El Alto" se hace especial)
      - destino (str): Filtro por destino (regex)
      - fecha (str): Filtro exacto en formato YYYY-MM-DD
    """
    from bson.objectid import ObjectId
    mongo = current_app.mongo

    # Tomar skip y limit de la querystring
    try:
        skip = int(request.args.get('skip', 0))
        limit = int(request.args.get('limit', 10))
    except ValueError:
        skip = 0
        limit = 10

    # Leer los nuevos parámetros de búsqueda
    origen_filter = request.args.get('origen', '').strip()
    destino_filter = request.args.get('destino', '').strip()
    fecha_filter = request.args.get('fecha', '').strip()

    # Construir el query
    query = {}
    if origen_filter:
        # Si se busca "El Alto", se quiere que retorne los viajes que sean:
        # - Aquellos cuyo origen sea "El Alto" (ya registrados así)
        # - O aquellos cuyo origen es "La Paz" y cuya parada_intermedia sea "El Alto"
        if origen_filter.lower() == "el alto":
            query["$or"] = [
                {"origen": {"$regex": "^El Alto$", "$options": "i"}},
                {"origen": "La Paz", "parada_intermedia": "El Alto"}
            ]
        else:
            query["origen"] = {"$regex": origen_filter, "$options": "i"}
    if destino_filter:
        query["destino"] = {"$regex": destino_filter, "$options": "i"}
    if fecha_filter:
        query["fecha"] = fecha_filter

    # Buscar en "viajes"
    viajes_cursor = mongo.db.viajes.find(query).sort("_id", -1).skip(skip).limit(limit)
    viajes_list = list(viajes_cursor)

    papeletas_rows = []
    for v in viajes_list:
        viaje_id = str(v.get("_id", ""))
        origen = v.get("origen", "N/A")
        destino = v.get("destino", "N/A")
        fecha_str = v.get("fecha", "N/A")
        hora_str = v.get("hora", "N/A")
        estado = v.get("estado", "pendiente")
        papeleta_flag = v.get("papeleta", False)

        # Recuperar nombre de chofer (si existe)
        chofer_nombre = "N/A"
        chofer_id = v.get("chofer_id")
        if chofer_id:
            driver_doc = mongo.db.drivers.find_one({"_id": chofer_id})
            if driver_doc:
                chofer_nombre = driver_doc.get("nombre", "N/A")

        # Recuperar placa del bus
        bus_doc = v.get("bus", {})
        bus_placa = bus_doc.get("placa", "N/A")

        # Fila principal con datos reales
        row_main = {
            "viaje_id": viaje_id,
            "chofer": chofer_nombre,
            "bus": bus_placa,
            "origen": origen,
            "destino": destino,
            "fecha": fecha_str,
            "hora": hora_str,
            "estado": estado,
            "papeleta": papeleta_flag
        }
        papeletas_rows.append(row_main)

        # Si el origen es "La Paz", se genera una fila adicional para el sub-viaje "El Alto"
        if origen.lower() == "la paz":
            from datetime import datetime, timedelta
            try:
                dt_original = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
                dt_sum = dt_original + timedelta(hours=1)
                fecha_sub = dt_sum.strftime("%Y-%m-%d")
                hora_sub = dt_sum.strftime("%H:%M")
            except Exception:
                fecha_sub = fecha_str
                hora_sub = hora_str

            row_sub = {
                "viaje_id": viaje_id + "_ElAlto",
                "chofer": chofer_nombre,
                "bus": bus_placa,
                "origen": "El Alto",
                "destino": destino,
                "fecha": fecha_sub,
                "hora": hora_sub,
                "estado": estado,
                "papeleta": papeleta_flag,
                "estado_el_alto": v.get("estado_el_alto", "pendiente"),         # 🔴 importante para el JS
                "papeletaElAlto": v.get("papeletaElAlto", False)                # 🔴 importante para el JS

            }
            papeletas_rows.append(row_sub)

    return jsonify({
        "success": True,
        "data": papeletas_rows
    })




























@admin_bp.route("/papeleta/liquidacion/print/<path:viaje_id>", methods=["GET"])
@admin_required
def print_liquidacion(viaje_id):
    """
    Genera un PDF en tamaño carta con:
      - Logo centrado en la parte superior.
      - N° boleta (rojo) debajo del logo.
      - Marca de agua (mismo logo) muy transparente en el centro.
      - Tabla 1: Pasajes combinados (con cabecera).
      - Tabla 2: Totales finales (TOTAL INGRESOS, Descuento, Peaje, TOTAL EGRESOS, LÍQUIDO PAGABLE).
      - Total de asientos vendidos mostrado aparte, debajo de las tablas.
      - Firmas al final, donde la firma de la oficina despachante muestra el origen (por ejemplo, "Oficina Despachante: Cochabamba").
      
      * Se han incrementado los espacios entre secciones.
    """

    from io import BytesIO
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.colors import red, black
    from bson.objectid import ObjectId
    import datetime

    mongo = current_app.mongo

    # --- Manejar sufijo "_ElAlto" ---
    sub_origen = None
    real_viaje_id = viaje_id
    if viaje_id.endswith("_ElAlto"):
        sub_origen = "ElAlto"
        real_viaje_id = viaje_id.replace("_ElAlto", "")

    try:
        obj_id = ObjectId(real_viaje_id)
    except:
        return "ID inválido", 400

    # --- Buscar la liquidación ---
    if sub_origen == "ElAlto":
        liq = mongo.db.liquidations.find_one({"viaje_id": obj_id, "sub_origen": "El Alto"})
    else:
        liq = mongo.db.liquidations.find_one({"viaje_id": obj_id, "sub_origen": None})

    if not liq:
        return "No se encontró la liquidación", 404

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    page_width, page_height = letter  # Aproximadamente 612 x 792 pts

    # =========== Márgenes ===========
    left_margin   = 1.0 * inch
    right_margin  = 1.0 * inch
    top_margin    = 1.5 * inch
    bottom_margin = 1.2 * inch
    usable_width  = page_width - (left_margin + right_margin)

    # =========== Marca de agua (muy transparente) ===========
    try:
        watermark_path = current_app.static_folder + "/images/arequipa.png"
        watermark_img  = ImageReader(watermark_path)
        c.saveState()
        c.setFillGray(0.97)  # Muy claro para simular alta transparencia
        opacity = 0.2  # 0.0 (transparente) a 1.0 (opaco)
        c.setFillAlpha(opacity)
        mark_w = 200
        mark_h = 80
        mark_x = (page_width - mark_w) / 2
        mark_y = (page_height - mark_h) / 2
        c.drawImage(watermark_img, mark_x, mark_y, width=mark_w, height=mark_h, mask='auto')
        c.restoreState()
    except:
        pass

    # =========== Datos de liquidación ===========
    fecha_gen = liq.get("fecha_generado")
    if isinstance(fecha_gen, datetime.datetime):
        fecha_emision_str = fecha_gen.strftime("%d/%m/%Y %H:%M")
    else:
        fecha_emision_str = str(fecha_gen)

    numero_papeleta = liq.get("numero_papeleta", "N/A")
    propietario     = liq.get("propietario_bus", "N/A")
    origen          = liq.get("origen", "N/A")
    destino         = liq.get("destino", "N/A")
    asientos_totales= liq.get("asientos_totales_vendidos", 0)
    total_ingresos  = liq.get("total_ingresos", 0)
    comision_pct    = liq.get("comision_pct", 0)
    comision_val    = liq.get("comision_val", 0)
    peaje_val       = liq.get("peaje", 0)
    neto            = liq.get("neto", 0)
    detalle_ventas  = liq.get("detalle_ventas", [])

    # Combinar precios repetidos (para pasajes)
    combined_prices = {}
    for venta_doc in detalle_ventas:
        pm = venta_doc.get("precios_vendidos", {})
        for p_str, qty in pm.items():
            combined_prices[p_str] = combined_prices.get(p_str, 0) + qty

    # =========== LOGO centrado arriba ===========
    try:
        logo_path = current_app.static_folder + "/images/arequipa.png"
        logo_img = ImageReader(logo_path)
        logo_w = 200
        logo_h = 80
        logo_x = (page_width - logo_w) / 2
        logo_y = page_height - top_margin
        c.drawImage(logo_img, logo_x, logo_y, width=logo_w, height=logo_h,
                    preserveAspectRatio=True, mask='auto')
    except:
        pass

    # =========== N° boleta debajo del logo ===========
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(red)
    # Colocamos 20 pts debajo del logo
    boleta_y = logo_y - 20  
    c.drawRightString(page_width - right_margin, boleta_y, f"N° {numero_papeleta}")
    c.setFillColor(black)

    # =========== Título ===========
    c.setFont("Helvetica-Bold", 16)
    title_y = boleta_y - 30  # mayor separación
    c.drawCentredString(page_width / 2, title_y, "PAPELETA DE LIQUIDACIÓN")

    # =========== Info principal: Fecha, Propietario, Origen/Destino ===========
    c.setFont("Helvetica", 11)
    line_gap = 16
    info_y = title_y - 40  # aumentar separación
    c.drawString(left_margin, info_y,   f"Fecha Emisión: {fecha_emision_str}")
    info_y -= line_gap
    c.drawString(left_margin, info_y,   f"Propietario: {propietario}")
    info_y -= line_gap
    c.drawString(left_margin, info_y,   f"Origen: {origen}  ->  Destino: {destino}")
    info_y -= (line_gap + 20)  # espacio extra antes de la tabla

    # =========== TABLA 1: PASAJES (Precios combinados) ===========
    # Se usan filas: 1 para cabecera + len(combined_prices)
    row_height = 20  # filas más altas para mayor separación
    prices_list = sorted(combined_prices.keys(), key=lambda x: float(x))
    n_rows_1 = 1 + len(prices_list)
    table1_height = n_rows_1 * row_height
    table1_y = info_y
    table1_x = left_margin
    bottom_table1 = table1_y - table1_height

    c.rect(table1_x, bottom_table1, usable_width, table1_height, stroke=1, fill=0)
    # Columna vertical: 70% / 30%
    col1_w = usable_width * 0.7
    col2_w = usable_width * 0.3
    c.line(table1_x + col1_w, bottom_table1, table1_x + col1_w, table1_y)

    # Líneas horizontales para tabla 1
    for i in range(n_rows_1 + 1):
        y_line = bottom_table1 + i * row_height
        c.line(table1_x, y_line, table1_x + usable_width, y_line)

    def draw_row_1(desc, amount, row_i, bold=False):
        y_base = bottom_table1 + (n_rows_1 - row_i - 1) * row_height
        text_y = y_base + 5
        if bold:
            c.setFont("Helvetica-Bold", 10)
        else:
            c.setFont("Helvetica", 10)
        c.drawString(table1_x + 5, text_y, desc)
        c.drawRightString(table1_x + usable_width - 5, text_y, amount)

    # Fila 0: Cabecera de tabla 1
    draw_row_1("DESCRIPCIÓN DE PASAJES", "Bs.", 0, bold=True)
    row_idx_1 = 1
    for p_str in prices_list:
        qty = combined_prices[p_str]
        val = float(p_str)
        sub = val * qty
        desc_line = f"{qty} x {val:.2f}"
        draw_row_1(desc_line, f"{sub:.2f}", row_idx_1)
        row_idx_1 += 1

    # =========== TABLA 2: Totales ===========
    # Queremos 5 filas: 
    # 0: TOTAL INGRESOS
    # 1: Descuento Oficina
    # 2: Peaje
    # 3: TOTAL EGRESOS
    # 4: LÍQUIDO PAGABLE
    row_height_2 = 20  # filas más altas
    n_rows_2 = 5
    table2_height = n_rows_2 * row_height_2
    table2_y = bottom_table1 - 40  # mayor separación entre tablas
    table2_x = left_margin
    bottom_table2 = table2_y - table2_height

    c.rect(table2_x, bottom_table2, usable_width, table2_height, stroke=1, fill=0)
    col1_w2 = usable_width * 0.7
    col2_w2 = usable_width * 0.3
    c.line(table2_x + col1_w2, bottom_table2, table2_x + col1_w2, table2_y)
    for i in range(n_rows_2 + 1):
        yy = bottom_table2 + i * row_height_2
        c.line(table2_x, yy, table2_x + usable_width, yy)

    def draw_row_2(desc, amount, row_i, bold=False):
        y_base = bottom_table2 + (n_rows_2 - row_i - 1) * row_height_2
        text_y = y_base + 5
        if bold:
            c.setFont("Helvetica-Bold", 10)
        else:
            c.setFont("Helvetica", 10)
        c.drawString(table2_x + 5, text_y, desc)
        c.drawRightString(table2_x + usable_width - 5, text_y, amount)

    total_egresos = comision_val + peaje_val
    draw_row_2("TOTAL INGRESOS", f"{total_ingresos:.2f}", 0, bold=True)
    draw_row_2(f"Descuento Oficina ({comision_pct:.1f}%)", f"{comision_val:.2f}", 1)
    draw_row_2("Peaje", f"{peaje_val:.2f}", 2)
    draw_row_2("TOTAL EGRESOS", f"{total_egresos:.2f}", 3, bold=True)
    draw_row_2("LÍQUIDO PAGABLE", f"{neto:.2f}", 4, bold=True)

    # =========== Total de Asientos Vendidos (dato aparte) ===========
    total_asientos_text = f"TOTAL ASIENTOS VENDIDOS: {asientos_totales}"
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(page_width / 2, bottom_table2 - 30, total_asientos_text)

    # =========== Firmas al final ===========
    # Se colocan cerca del margen inferior
    firma_y = bottom_margin  # aproximadamente en el margen inferior
    c.line(left_margin, firma_y, left_margin + 180, firma_y)
    c.setFont("Helvetica", 10)
    # En la firma se muestra el origen, que se usará para la oficina despachante
    c.drawString(left_margin, firma_y - 12, f"Oficina Despachante: {origen}")
    c.line(page_width - right_margin - 180, firma_y, page_width - right_margin, firma_y)
    c.drawRightString(page_width - right_margin, firma_y - 12, "Recibí Conforme")

    c.showPage()
    c.save()
    buffer.seek(0)

    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": 'inline; filename="papeleta_liquidacion.pdf"'}
    )
