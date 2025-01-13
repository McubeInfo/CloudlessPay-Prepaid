# from mongoengine import connect
from flask_jwt_extended import JWTManager
import os

MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://akash:jXEQJVnnByx7pwbK@cloudlesspay.rwl0a.mongodb.net/cloudlesspay')

jwt = JWTManager()
