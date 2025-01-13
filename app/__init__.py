from flask import Flask
from flask_cors import CORS
from app.config import jwt, MONGO_URI
from mongoengine import connect, connection

def create_app():
    
    app = Flask(__name__)
    app.config.from_prefixed_env()
    CORS(app) 
    
    try:
        connect(host=MONGO_URI)
        if connection.get_connection():
            app.logger.info("Database connected successfully.")
    except Exception as e:
        app.logger.error(f"Database connection failed: {e}")
        raise e
    
    jwt.init_app(app)
    
    
    from app.create_orders import order_bp
    from app.auth import auth_bp
    from app.main import main_bp
    from app.logs import logs_bp
    from app.settings import settings_bp
    
    app.register_blueprint(order_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(logs_bp, url_prefix='/api')
    app.register_blueprint(settings_bp, url_prefix='/settings')
    
    import models
    
    return app