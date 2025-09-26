from flask import Flask, render_template, send_from_directory
from controller.chatbot_controller import chatbot_bp
from controller.user_controller import user_bp
from controller.auth_controller import auth_bp
from controller.admin_controller import admin_bp
from controller.file_management_controller import file_bp
from controller.admin_hr_controller import admin_hr_bp

from flask_cors import CORS
import os
from utils.user.chat_utils import get_response_from_multiple_sources       
from utils.aws_client import bedrock_client, session
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv
from models.models_db import db, ConversationLog
from config.database import Config
import redis
from utils.redis_client import redis_client 
from datetime import timedelta
from flasgger import Swagger

app = Flask(__name__)

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "VHA API",
        "description": "API documentation for VHA Backend",
        "version": "1.0.0"
    },
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT Authorization header using the Bearer scheme. Example: 'Bearer {token}'"
        }
    },
    "security": [{"Bearer": []}]
}

swagger = Swagger(app, template=swagger_template)

app.register_blueprint(chatbot_bp)
app.register_blueprint(user_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(file_bp)
app.register_blueprint(admin_hr_bp)

CORS(app, origins=["http://localhost:3000", "https://vime.vinova.sg"], supports_credentials=True)

print(f"FE_HOST: {os.getenv('FE_HOST')}")
app.config.from_object(Config)
db.init_app(app)
with app.app_context():
    db.create_all()
    
    try:
        from utils.admin.global_config import initialize_default_global_configs
        initialize_default_global_configs()
        print("[INFO] Global configuration initialized successfully")
    except Exception as e:
        print(f"[WARNING] Failed to initialize global config: {e}")

load_dotenv()
app.redis_client = redis_client
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES")))  
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES")))  
jwt = JWTManager(app)
@app.route("/test-cors", methods=["GET"])
def test_cors():
    return {"message": "CORS working!"}

@app.route("/test-redis", methods=["GET"])
def test_redis():
    try:
        from utils.redis_client import redis_client
        redis_client.set("test_key", "test_value", ex=60)
        value = redis_client.get("test_key")
        return {"message": "Redis working!", "value": value}
    except Exception as e:
        return {"message": "Redis error!", "error": str(e)}

@app.route("/test-auth", methods=["GET"])
def test_auth():
    try:
        from utils.admin.session_utils import require_session
        from utils.admin.auth_utils import require_admin, require_member_or_admin
        from flask import g
        
        @require_session
        @require_member_or_admin
        def test_function():
            return {"user": g.user}
        
        return {"message": "Auth decorators imported successfully"}
    except Exception as e:
        return {"message": "Auth error!", "error": str(e)}
if __name__ == "__main__":
     app.run(host="0.0.0.0", port=3001, debug=True)