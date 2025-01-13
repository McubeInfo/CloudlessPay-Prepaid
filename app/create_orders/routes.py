from flask import request, jsonify
import razorpay.errors
from . import order_bp
from flask_jwt_extended import jwt_required, get_jwt_identity
import razorpay
from models import User, Wallet
from utils.utils import *

@order_bp.post('/create-order')
@token_required
def create_order(current_user):
    current_user = get_jwt_identity()
    email = current_user
    user = User.objects(email=email).first()
    
    if not user.razorpay_key_id or not user.razorpay_key_secret:
        log_api_request("/api/create-order", email, "Razorpay credentials not found for the user", "failure")
        return jsonify({"error": "Razorpay credentials not found for the user"}), 400
    
    key_id = user.razorpay_key_id
    key_secret = user.get_razorpay_key_secret()

    razorpay_client = razorpay.Client(auth=(key_id, key_secret))
    
    data = request.get_json()
    
    actual_amount = data.get('amount', 0)
    
    if not actual_amount or not isinstance(actual_amount, (int, float)) or actual_amount <= 0:
        log_api_request("/api/create-order", email, "Amount is required and must be a positive number", "failure")
        return jsonify({"error": "Invalid Input", "message": "Amount is required and must be a positive number"}), 400
    
    amount = int(actual_amount) * 100
    currency = data.get('currency', 'INR')
    receipt = str(data.get('receipt', 'receipt#1'))
    notes = {key: str(value) for key, value in data.get('notes', {}).items()}
    partial_payment = data.get('partial_payment', False)
    payment_capture = data.get('payment_capture', False) 
    
    first_payment_min_amount = 0
    if partial_payment:
        try:
            first_payment_min_amount = data['first_payment_min_amount']
            if first_payment_min_amount >= actual_amount:
                log_api_request("/api/create-order", email, "First payment minimum amount must be less than total order amount","failure")
                return jsonify({"error": "Invalid Input", "message": "First payment minimum amount must be less than total order amount"}), 400
        except Exception as e:
            log_api_request("/api/create-order", email, "The first_payment_min_amount is required if partial_payment is true.", "failure")
            return jsonify({"error": "Missing Input Parameter", "message": "The first_payment_min_amount is required if partial_payment is true."}), 400
    
    # Check if user has enough credits
    wallet = Wallet.objects(user=user).first()
    if not wallet or wallet.credits <= 0:
        log_api_request("/api/create-order", email, "Insufficient credits", "failure")
        return jsonify({"error": "Insufficient credits", "message": "You don't have enough credits to create this order"}), 400

    payment_data = {
        "amount": amount,
        "currency": currency,
        "receipt": receipt,
        "notes": notes,
        "payment_capture": 1 if payment_capture else 0, 
    }
    

    if partial_payment:
        payment_data["partial_payment"] = True
        payment_data["first_payment_min_amount"] = first_payment_min_amount
    else:
        payment_data.pop('partial_payment', None)
        payment_data.pop('first_payment_min_amount', None)
    
    try:

        order = razorpay_client.order.create(payment_data)

        order['amount'] = int(order['amount']) / 100  # Convert to actual amount
        order['amount_due'] = int(order['amount_due']) / 100  # Convert due amount to actual

        order_response = {"order": order, "message": "Order created successfully"}

        log_api_request("/api/create-order", email, order_response, "success")
        # Deduct 1 credit for this operation
        wallet.update(inc__credits=-1)
        return jsonify(order_response), 201

    except razorpay.errors.BadRequestError as e:
        log_api_request("/auth/create-order", email, str(e), "failure")
        return jsonify({"error": "Razorpay Bad Request", "message": str(e)}), 400

    except Exception as e:
        log_api_request("/auth/create-order", email, str(e), "failure")
        return jsonify({"error": "An unexpected error occurred", "message": str(e)}), 500
            