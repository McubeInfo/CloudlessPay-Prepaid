# from mongoengine import connect
from flask_jwt_extended import JWTManager
import os

MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://akash:jXEQJVnnByx7pwbK@cloudlesspayfree.rwl0a.mongodb.net/cloudlesspayfree')

jwt = JWTManager()
