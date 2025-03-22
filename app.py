from flask import Flask, request, render_template
from flask_pymongo import PyMongo
from config import Config
import os

# Registrar blueprints
from routes.auth_routes import auth_bp
from routes.admin_routes import admin_bp
from routes.ventanilla_routes import ventanilla_bp

app = Flask(__name__)
app.config.from_object(Config)

# Inicializar la conexión a MongoDB
mongo = PyMongo(app)
app.mongo = mongo

# Registrar blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(ventanilla_bp)

@app.before_request
def require_login():
    allowed_endpoints = ['auth.login', 'auth.register']
    
    if request.endpoint is None:
        return render_template('login.html')
    
    if request.endpoint in allowed_endpoints or (request.endpoint.startswith('static')):
        return

    token = request.cookies.get('token')
    if not token:
        return render_template('login.html')

# Solo se usa para desarrollo local
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
