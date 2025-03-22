import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'clave_por_defecto')
    JWT_SECRET = os.getenv('JWT_SECRET', 'jwt_por_defecto')
    JWT_ALGORITHM = 'HS256'
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
