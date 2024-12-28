from flask import jsonify, session
from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity
from functools import wraps
from requests.auth import HTTPBasicAuth
import requests
from models import RevokedToken, APILog
from flask import request
import json
from models import User
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def email_template(title, content):
    """Generate an email body with a consistent design."""
    return f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px;">
            <div style="max-width: 600px; margin: auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);">
                <div style="background: #007bff; color: white; padding: 20px; text-align: center;">
                    <h1 style="margin: 0; font-size: 24px;">{title}</h1>
                </div>
                <div style="padding: 20px; line-height: 1.6; color: #333;">
                    {content}
                </div>
                <div style="text-align: center; background: #f4f4f4; padding: 10px;">
                    <p style="margin: 0; font-size: 12px; color: #777;">
                        This is an automated message. Please do not reply to this email.
                    </p>
                </div>
            </div>
        </body>
    </html>
    """


def send_email(subject, recipient_email, body):
    """Send an email using SMTP."""
    smtp_host = os.environ.get('SMTP_HOST')  # SMTP host
    smtp_port = int(os.environ.get('SMTP_PORT'))  # SMTP port
    smtp_user = os.environ.get('SMTP_USER')  # Email username
    smtp_password = os.environ.get('SMTP_PASSWORD')  # Email password

    if not all([smtp_host, smtp_port, smtp_user, smtp_password]):
        raise ValueError("SMTP environment variables are not set properly.")
    print(smtp_host, smtp_port, smtp_user, smtp_password)
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = recipient_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'html'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, recipient_email, msg.as_string())
    except Exception as e:
        raise Exception(f"Failed to send email: {e}")
    
def token_required(fn):
    @wraps(fn)
    def decorated_function(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except Exception as e:
            print(f"JWT Verification Failed: {str(e)}")
            return jsonify({"error": "Token verification failed", "message": str(e)}), 401

        current_user = get_jwt_identity()
        jti = get_jwt().get("jti")

        if is_token_revoked(jti):
            return jsonify({"error": "Token has been revoked"}), 401

        return fn(current_user, *args, **kwargs)
    return decorated_function


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'User not logged in'}), 401
        return f(*args, **kwargs)
    return decorated_function


def is_token_revoked(jti):
    token = RevokedToken.objects(jti=jti).first()
    return token is not None

def add_token_to_blacklist(jti):
    revoked_token = RevokedToken(jti=jti)
    revoked_token.save() 

def validate_razorpay_credentials(key_id, key_secret):
    url = "https://api.razorpay.com/v1/payments"
    response = requests.get(url, auth=HTTPBasicAuth(key_id, key_secret))
    
    return response.status_code == 200

def identify_client(user_agent):
    """Identify the client based on the User-Agent string."""
    if 'Postman' in user_agent:
        return 'Postman'
    elif 'curl' in user_agent:
        return 'cURL'
    elif 'Chrome' in user_agent:
        return 'Google Chrome'
    elif 'Firefox' in user_agent:
        return 'Mozilla Firefox'
    elif 'Safari' in user_agent and 'Chrome' not in user_agent:
        return 'Apple Safari'
    elif 'Edge' in user_agent:
        return 'Microsoft Edge'
    else:
        return 'Unknown Client'

def log_api_request(endpoint, email, response_data, status):
    """Helper function to log API request."""
    domain = request.headers.get('Origin', 'unknown domain')
    user_agent = request.headers.get('User-Agent', 'Unknown')
    platform_info = identify_client(user_agent)
    
    user = User.objects(email=email).first()

    log_entry = APILog(
        endpoint=endpoint,
        user=user.id if user else None,  
        domain=domain,
        platform=platform_info,
        response=json.dumps(response_data) if isinstance(response_data, dict) else str(response_data),
        status=status
    )
    log_entry.save()
