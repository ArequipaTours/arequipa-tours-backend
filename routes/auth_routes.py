from flask import Blueprint, request, render_template, make_response, current_app, url_for, redirect
import jwt
import datetime
from config import Config
from werkzeug.security import check_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    # Procesar datos del formulario de login
    carnet = request.form.get('carnet')
    password = request.form.get('password')
    
    if not carnet or not password:
        return render_template('login.html', error="Faltan credenciales")
    
    mongo = current_app.mongo
    # Consultar el usuario en la colección "users"
    user = mongo.db.users.find_one({'carnet': carnet})
    if not user:
        return render_template('login.html', error="Credenciales inválidas")
    
    # Verificar la contraseña encriptada
    if not check_password_hash(user.get('password'), password):
        return render_template('login.html', error="Credenciales inválidas")
    
    # Crear el payload del token con expiración de 1 hora
    payload = {
        'user_id': str(user['_id']),
        'carnet': user['carnet'],
        'nombre': user['nombre'],
        'rol': user['rol'],
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }
    
    token = jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    
    # Redirigir al dashboard correspondiente según el rol
    if user['rol'] == 'superadmin':
        response = redirect(url_for('admin.superadmin_dashboard'))
    elif user['rol'] == 'administrador':
        response = redirect(url_for('admin.admin_dashboard'))
    else:
        response = redirect(url_for('ventanilla.cajero_dashboard'))
    
    response.set_cookie('token', token, httponly=True, samesite='Lax')
    return response

@auth_bp.route('/logout')
def logout():
    response = redirect(url_for('auth.login'))
    response.delete_cookie('token')
    return response
