# from mongoengine import connect
from flask_jwt_extended import JWTManager
import os

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/cloudlesspayprepaid')

# connect(host=MONGO_URI)

jwt = JWTManager()
