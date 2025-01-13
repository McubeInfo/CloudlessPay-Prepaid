from flask import request, jsonify, session, render_template, redirect, url_for
from . import auth_bp
from models import User, Wallet
from flask_jwt_extended import create_access_token
from marshmallow import ValidationError
import uuid
from utils.utils import *
import random
import string

# A dictionary to store OTPs temporarily
otp_store = {}

def generate_otp(length=6):
    """Generate a random OTP."""
    return ''.join(random.choices(string.digits, k=length))
    
@auth_bp.post('/send-otp')
def send_otp():
    """Generate and send OTP to user's email."""
    try:
        data = request.get_json()
        email = data.get('email')
        if not email:
            return jsonify({"error": "Email is required"}), 400

        user = User.objects(email=email).first()
        if user:
            return jsonify({"error": "User already registered"}), 403

        # Generate OTP
        otp = generate_otp()
        otp_store[email] = otp
        
        subject = "Verify Your Email for CloudlessPay"
        body = email_template(
            title="Verify Your Email Address",
            content=f"""
                <p>Hi {data.get('username')},</p>
                <p>Thank you for signing up for <b>CloudlessPay</b>. To complete your signup process, please verify your email address by entering the following One-Time Password (OTP):</p>
                <h2 style="text-align: center; color: #007bff;">{otp}</h2>
                <p>This OTP is valid for the next <b>10 minutes</b>. Please do not share this code with anyone.</p>
                <p>If you did not request this, please ignore this email or contact our support team by reply to this mail.</p>
                <p>Best Regards,</p>
                <p>The CloudlessPay Team</p>
            """
        )
        send_email(subject, email, body)


        return jsonify({"message": "OTP sent to email"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@auth_bp.post('/verify-otp')
def verify_otp():
    """Verify OTP and register user."""
    try:
        data = request.get_json()
        email = data.get('email')
        otp = data.get('otp')

        if not email or not otp:
            return jsonify({"error": "Email and OTP are required"}), 400

        # Validate OTP
        if email not in otp_store or otp_store[email] != otp:
            return jsonify({"error": "Invalid OTP"}), 403

        # Register the user
        new_user = User(
            username=data.get('username'),
            email=email
        )
        new_user.set_hashed_password(password=data.get('password'))
        new_user.save()

        # Clean up OTP store
        del otp_store[email]
        
        subject = "Welcome to CloudlessPay - You've Got 200 Free Credits!"
        body = email_template(
            title="Welcome to CloudlessPay!",
            content=f"""
                <p>Hi {data.get('username')},</p>
                <p>We’re excited to have you on board! As a welcome gift, we've credited <b>₹200</b> to your wallet to get you started.</p>
                <p>You can use these credits to explore our services and experience all that we have to offer.</p>
                <p><b>Here’s what you can do next:</b></p>
                <ul>
                    <li><a href="https://cloudlesspayment.com/docs/razorpay" style="color: #007bff;">Start Exploring Services</a></li>
                    <li><a href="https://cloudlesspayment.com/docs/settings" style="color: #007bff;">Check Your Wallet Balance</a></li>
                </ul>
                <p>If you have any questions, feel free to reply to this email.</p>
                <p>Thank you for joining us. We can’t wait to see what you accomplish!</p>
                <p>Best Regards,</p>
                <p>The CloudlessPay Team</p>
            """
        )
        send_email(subject, email, body)


        return jsonify({"message": "User successfully registered"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.get('/authorize')
def loginPage():
    if 'user' not in session:
        return render_template('login.html')
    else:
        return render_template('razorpay.html')

@auth_bp.post('/login')
def login():
    try:
        data = request.get_json()

        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Missing email or password or captcha'}), 400

        user = User.objects(email=data.get('email')).first()

        if not user:
            return jsonify({'error': 'Invalid email or password'}), 401

        if not user.check_password(password=data.get('password')):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        session['user'] = {
            'id': str(user.id),
            'email': user.email,
            'name': user.username
        }

        return jsonify({'message': 'Login Successfully', 'redirect': '/docs/app'}), 200

    except ValidationError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route('/set-credentials', methods=['POST', 'OPTIONS'])
@login_required
def set_razorpay_credentials():
    if request.method == 'OPTIONS':
        return '', 200
    current_user = session.get('user')
    
    if not current_user:
        return jsonify({'error': 'User not logged in'}), 401
    
    user = User.objects(email=current_user['email']).first()
    
    data = request.get_json()
    
    razorpay_key_id = data.get('key_id')
    razorpay_key_secret = data.get('key_secret')
    
    if not validate_razorpay_credentials(razorpay_key_id, razorpay_key_secret):
        return jsonify({"error": "Invalid Razorpay credentials"}), 401

    if not razorpay_key_id or not razorpay_key_secret:
        return jsonify({"error": "Both key_id and key_secret are required"}), 400

    user.set_razorpay_credentials(razorpay_key_id, razorpay_key_secret)
    user.save()
    
    return jsonify({'message': 'Razorpay credentials saved successfully'}), 200

@auth_bp.get('/create-access-token')
@login_required
def generate_access_token():
    current_user = session.get('user')
    
    if not current_user:
        return jsonify({'error': 'User not logged in'}), 401
    
    user = User.objects(email=current_user['email']).first()
    
    wallet = Wallet.objects(user=user).first()
    if not wallet or wallet.credits <= 0:
        return jsonify({"error": "Insufficient credits to generate an API access token.", "message": "Please recharge your account to continue using the API."}), 400
    
    '''user_credits = UserCredits.objects(user=user.id).first()
    
    if user_credits and user_credits.credits <= 0:
        return jsonify({
            'error': 'Insufficient credits to generate an API access token.',
            'message': 'Please recharge your account to continue using the API.',
            'recharge_link': url_for('recharge_page')  # Adjust with your actual recharge page URL
        }), 403'''
    
    if not user.razorpay_key_id or not user.razorpay_key_secret:
        return jsonify({'error': 'Razorpay credentials must be set before generating an access token'}), 400
    
    if not validate_razorpay_credentials(user.razorpay_key_id, user.get_razorpay_key_secret()):
        return jsonify({"error": "Invalid Razorpay credentials"}), 401
    
    if user.access_token:
        return jsonify({'error': 'Access token already exists. Delete it before creating a new one.'}), 403

    jti = str(uuid.uuid4())
    access_token = create_access_token(identity=current_user['email'], expires_delta=False, additional_claims={"jti": jti})
    user.access_token = access_token
    user.jti = jti
    user.save()
    
    return jsonify({'message': 'New Access Token Generated', 'access_token': access_token}), 200


@auth_bp.delete('/delete-access-token')
@login_required
def delete_access_token():
    
    current_user = session.get('user')
    
    if not current_user:
        return jsonify({'error': 'User not logged in'}), 401
    
    user = User.objects(email=current_user['email']).first()

    if user.access_token:
        add_token_to_blacklist(user.jti)
        user.access_token = None
        user.jti = None
        user.save()
        
        return jsonify({"message": "Access token deleted successfully"}), 200

    return jsonify({"error": "No access token found"}), 400

@auth_bp.get('/get-access-token')
@login_required
def get_access_token():
    try:
        current_user = session.get('user')
        user = User.objects(email=current_user['email']).first()
        
        wallet = Wallet.objects(user=user).first()
        if not wallet or wallet.credits <= 0:
            return jsonify({"error": "Insufficient credits, We can't able to proceed with your request.", "message": "Please recharge your account to continue using the API."}), 400
        
        access_token = user.access_token
        if not access_token:
            return jsonify({"error": "Access token not found, Please generate the access token and try again."}), 400
        return jsonify({'access_token': access_token}), 200
    except Exception as e:
        return jsonify({'error': e})

@auth_bp.get('/logout')
def logout():
    session.pop('user', None)
    return render_template('home.html')