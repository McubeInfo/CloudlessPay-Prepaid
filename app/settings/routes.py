from flask import request, jsonify, session, render_template
from . import settings_bp
from models import User, Wallet, PaymentHistory
from utils.utils import *
from datetime import datetime, timedelta
import razorpay
import os
from dotenv import load_dotenv
load_dotenv()
from dateutil.relativedelta import relativedelta
from mongoengine import Q

RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

@settings_bp.post('/add-credits')
@login_required
def add_credits():
    current_user = session.get('user')
    user_name = current_user['email']
    user = User.objects(email=user_name).first()

    try:
        data = request.get_json()
        amount_to_recharge = int(data.get('amount'))  # amount to add to the wallet

        if not amount_to_recharge or amount_to_recharge <= 0:
            return jsonify({"error": "Invalid amount provided."}), 400
        
        # Create a payment order in Razorpay
        order = razorpay_client.order.create({
            'amount': amount_to_recharge * 100,  # Razorpay expects amount in paise
            'currency': 'INR',
            'payment_capture': 1
        })

        # Send order details to the frontend for payment
        return jsonify({
            'message': "Payment order created successfully.",
            'order_id': order['id'],
            'amount': amount_to_recharge * 100,
            'razorpay_key_id': os.environ.get('RAZORPAY_KEY_ID')
        }), 200

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": f"An error occurred during the recharge process. {e}"}), 500


@settings_bp.post('/payment-success')
@login_required
def payment_success():
    current_user = session.get('user')
    user_name = current_user['email']
    user = User.objects(email=user_name).first()

    try:
        data = request.get_json()
        
        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")
        amount = data.get("amount")
        
        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature, amount]):
            return jsonify({"error": "Missing required fields"}), 400
        
        try:
            razorpay_client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature
            })
        except razorpay.errors.SignatureVerificationError:
            return jsonify({"error": "Payment verification failed"}), 400
        
        payment_details = razorpay_client.payment.fetch(razorpay_payment_id)
        payment_method = payment_details.get('method', 'Unknown')
        
        # Get user's wallet and update credits
        wallet = Wallet.objects(user=user).first()
        if not wallet:
            return jsonify({"error": "Wallet not found"}), 404

        amount /= 100
        wallet.add_credits(amount)  # Assuming this method updates the wallet credits
        
        # Save payment history
        PaymentHistory(
            user=user,
            amount=amount,
            payment_date=datetime.now(),
            payment_method=payment_method,
            transaction_id=razorpay_payment_id
        ).save()
        
        # Send confirmation email
        subject = "Payment Successful - Your Wallet Has Been Credited"
        body = email_template(
            title="Payment Successful",
            content=f"""
                <p>Hi {user.username},</p>
                <p>Your payment of ₹{amount} has been successfully processed.</p>
                <p><b>Transaction ID:</b> {razorpay_payment_id}</p>
                <p><b>New Wallet Balance:</b> ₹{wallet.credits}</p>
                <p>Thank you for using our services!</p>
            """
        )
        send_email(subject, user.email, body)
        
        return jsonify({
            "message": "Payment verified and wallet updated",
            "new_balance": wallet.credits
        }), 200
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": f"An error occurred while processing payment. {e}"}), 500


@settings_bp.post('/save_billing_address')
@login_required
def save_billing_address():
    current_user = session.get('user')
    
    user_name = current_user['email']
    user = User.objects(email=user_name).first()

    data = request.get_json()
    
    user.set_billing_address({
        'company_name': data['company_name'],
        'phone': data['phone'],
        'email': data['email'],
        'address': data['address'],
        'country': data['country'],
        'state': data['state'],
        'city': data['city'],
        'pincode': data['pincode'],
        'gst_registered': data['gst_registered'],
        'gst_number': data['gst_number'],
    })
    
    user.save()
    
    return jsonify({"message": "Billing address saved successfully."}), 200

@settings_bp.get('/get_billing_address')
@login_required
def get_bill_address():
    current_user = session.get('user')
    
    user_name = current_user['email']
    user = User.objects(email=user_name).first()
    
    return jsonify({"message": "Billing addresses retrieved successfully.", "billings": user.get_billing_address()}), 200


@settings_bp.route("/payment-history", methods=["GET"])
@login_required
def payment_history():
    try:
        start = int(request.args.get('start', 0))  # Pagination start
        length = int(request.args.get('length', 10))  # Page size
        search_value = request.args.get('search[value]', '')  # Search keyword
        order_column_index = int(request.args.get('order[0][column]', 0))  # Column index
        order_direction = request.args.get('order[0][dir]', 'asc')  # Sort direction

        # Map column indices to field names in the PaymentHistory model
        columns_map = {
            0: 'payment_date',
            1: 'transaction_id',
            2: 'amount',
            3: 'status',
        }

        # Determine sorting column
        order_column = columns_map.get(order_column_index, 'payment_date')  # Default to payment_date
        order_by = f"-{order_column}" if order_direction == 'desc' else order_column

        # Current user
        current_user = session.get('user')
        user_email = current_user.get('email')
        user = User.objects(email=user_email).first()

        if not user:
            return jsonify({"error": "User not found"}), 404

        # Base query for PaymentHistory
        payment_query = PaymentHistory.objects(user=user)

        # Apply search filter
        if search_value:
            payment_query = payment_query.filter(
                Q(transaction_id__icontains=search_value) |
                Q(status__icontains=search_value)
            )

        # Total records before filtering
        total_records = PaymentHistory.objects(user=user).count()

        # Filtered records count
        filtered_records = payment_query.count()

        # Apply sorting and pagination
        payment_query = payment_query.order_by(order_by).skip(start).limit(length)

        # Format data for DataTables
        data = [{
            "payment_date": payment.payment_date.strftime("%d-%m-%Y") if isinstance(payment.payment_date, datetime) 
    else datetime.strptime(payment.payment_date, '%Y-%m-%dT%H:%M:%S.%f').strftime("%d-%m-%Y"),
            "transaction_id": payment.transaction_id,
            "amount": f"₹{payment.amount:.2f}",
            "status": payment.status,
            "payment_method": payment.payment_method,
        } for payment in payment_query]

        return jsonify({
            "draw": int(request.args.get('draw', 1)),  # DataTables draw counter
            "recordsTotal": total_records,
            "recordsFiltered": filtered_records,
            "data": data,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

  
# ----------------------------------------------------------------
# Credits routes
# ----------------------------------------------------------------

@settings_bp.route("/get_credits", methods=["GET"])
@login_required
def get_user_credits():
    current_user = session.get('user')
    user_name = current_user['email']
    user = User.objects(email=user_name).first()
    
    if not user:
        return jsonify({"error": "Invalid or Login expired"}), 403

    wallet = Wallet.objects(user=user).first()
    if not wallet:
        return jsonify({"error": "Wallet not found"}), 404

    # Calculate total credits used this month
    current_date = datetime.now()
    start_of_month = current_date.replace(day=1)
    end_of_month = (start_of_month + relativedelta(months=1)).replace(day=1) - timedelta(seconds=1)

    total_credits_used = APILog.objects(
        user=user,
        log_time__gte=start_of_month,
        log_time__lte=end_of_month,
        status="success"
    ).count()  # Count API calls (1 credit per call)

    return jsonify({
        "total_credits": wallet.credits,
        "credits_used_this_month": total_credits_used
    }), 200
    
    

@settings_bp.route("/get_monthwise_credits", methods=["GET"])
@login_required
def get_users_monthwise_credits():
    current_user = session.get('user')
    user_name = current_user['email']
    user = User.objects(email=user_name).first()
    
    month = request.args.get("month", "this-month")
    
    if not user:
        return jsonify({"error": "Invalid or Login expired"}), 403

    wallet = Wallet.objects(user=user).first()
    if not wallet:
        return jsonify({"error": "Wallet not found"}), 404

    today = datetime.today()
    if month == "this-month":
        start_date = today.replace(day=1)
        end_date = (start_date + relativedelta(months=1)).replace(day=1) - timedelta(seconds=1)
    elif month == "last-month":
        start_date = (today.replace(day=1) - relativedelta(months=1)).replace(day=1)
        end_date = (start_date + relativedelta(months=1)).replace(day=1) - timedelta(seconds=1)
    elif month == "last-previous-month":
        start_date = (today.replace(day=1) - relativedelta(months=2)).replace(day=1)
        end_date = (start_date + relativedelta(months=1)).replace(day=1) - timedelta(seconds=1)
    else:
        return jsonify({"error": "Invalid month selection"}), 400

    total_credits_used = APILog.objects(
        user=user,
        log_time__gte=start_date,
        log_time__lte=end_date,
        status="success"
    ).count()

    return jsonify({
        "selected_month": month,
        "credits_used": total_credits_used,
    }), 200