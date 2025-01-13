from mongoengine import Document, fields, CASCADE, signals
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
from uuid import uuid4
from datetime import datetime
import os


class User(Document):
    meta = {'collection': 'users'}
    
    id = fields.StringField(primary_key=True, default=lambda: str(uuid4()))
    username = fields.StringField(required=True, max_length=150)
    email = fields.EmailField(required=True, unique=True)
    password = fields.StringField(required=True)
    razorpay_key_id = fields.StringField()
    razorpay_key_secret = fields.StringField()
    access_token = fields.StringField()
    jti = fields.StringField()
    billing_address = fields.DictField()
    created_at = fields.DateTimeField(default=datetime.now)
    updated_at = fields.DateTimeField()
    is_active = fields.BooleanField(default=True)

    def set_hashed_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def set_razorpay_credentials(self, key_id, key_secret):
        if not os.environ.get('SECRET_KEY'):
            raise ValueError("SECRET_KEY is not set in the environment variables.")
        self.razorpay_key_id = key_id
        cipher_suite = Fernet(str(os.environ.get('SECRET_KEY')).encode())
        self.razorpay_key_secret = cipher_suite.encrypt(key_secret.encode()).decode()

    def get_razorpay_key_secret(self):
        if not self.razorpay_key_secret:
            return None
        cipher_suite = Fernet(str(os.environ.get('SECRET_KEY')).encode())
        return cipher_suite.decrypt(self.razorpay_key_secret.encode()).decode()

    def set_billing_address(self, address_data):
        self.billing_address = address_data
        self.save()
        
    def get_billing_address(self):
        return self.billing_address or {}

class RevokedToken(Document):
    meta = {'collection': 'revoked_tokens'}
    
    id = fields.SequenceField(primary_key=True)
    jti = fields.StringField(required=True, unique=True)
    revoked_at = fields.DateTimeField(default=datetime.now)


class Wallet(Document):
    user = fields.ReferenceField(User, reverse_delete_rule=CASCADE)
    credits = fields.FloatField(default=200.0)  # Initial free credits
    last_updated = fields.DateTimeField(default=datetime.now())

    def to_json(self):
        return {
            "user_id": str(self.user.id),
            "credits": self.credits,
            "last_updated": self.last_updated.isoformat(),
        }

    def add_credits(self, amount):
        """Add credits to the wallet."""
        self.credits += amount
        self.last_updated = datetime.now()
        self.save()

    def deduct_credits(self, amount):
        """Deduct credits if sufficient balance exists."""
        if self.credits < amount:
            raise ValueError("Insufficient credits")
        self.credits -= amount
        self.last_updated = datetime.now()
        self.save()

    def has_sufficient_credits(self, amount):
        """Check if wallet has enough credits."""
        return self.credits >= amount

class PaymentHistory(Document):
    user = fields.ReferenceField(User, reverse_delete_rule=CASCADE)
    transaction_id = fields.StringField(required=True, unique=True) 
    amount = fields.FloatField(required=True)
    payment_date = fields.DateTimeField(default=datetime.now)
    payment_method = fields.StringField(required=True)
    status = fields.StringField(choices=["Pending", "Completed", "Failed", "Refunded"], default="Completed")

    def to_json(self):
        """Converts the model instance into a JSON-friendly format."""
        return {
            "transaction_id": self.transaction_id,
            "user_id": str(self.user.id),
            "amount": self.amount,
            "payment_date": self.payment_date.isoformat(),
            "payment_method": self.payment_method,
            "status": self.status,
        }

    @classmethod
    def get_by_user(cls, user):
        """Fetch all payment history for a given user, ordered by payment date."""
        return cls.objects(user=user).order_by("-payment_date")


class APILog(Document):
    meta = {'collection': 'api_logs'}
    
    user = fields.ReferenceField(User, reverse_delete_rule=CASCADE)
    log_time = fields.DateTimeField(default=datetime.now)
    endpoint = fields.StringField(max_length=120)
    domain = fields.StringField(max_length=120)
    platform = fields.StringField(max_length=50)
    response = fields.StringField()
    status = fields.StringField(default="success")
    
    def to_json(self):
        return {
            "user_id": str(self.user.id),
            "endpoint": self.endpoint,
            "domain": self.domain,
            "platform": self.platform,
            "response": self.response,
            "status": self.status,
            "log_time": self.log_time.isoformat(),
        }
    
    @classmethod
    def log_api_call(cls, user, endpoint, domain, platform, response, status):
        """Log an API call made by a user."""
        log = cls(
            user=user,
            log_time=datetime.now(),
            endpoint=endpoint,
            domain=domain,
            platform=platform,
            response=response,
            status=status,
        )
        log.save()


def create_wallet(sender, document, **kwargs):
    """Auto-create a wallet when a new user is created."""
    if not Wallet.objects(user=document).first():
        Wallet(user=document).save()


signals.post_save.connect(create_wallet, sender=User)