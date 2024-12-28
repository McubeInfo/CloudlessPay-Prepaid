from flask import jsonify
from models import APILog, User
from datetime import datetime, timedelta
from . import logs_bp
from utils.utils import *
from mongoengine import Q
    
@logs_bp.route('/logs', methods=['GET'])
@login_required
def get_logs():
    try:
        start = int(request.args.get('start', 0))  # Pagination start
        length = int(request.args.get('length', 10))  # Page size
        
        # Search keyword
        search_value = request.args.get('search[value]', '')
        
        # Sorting
        order_column_index = int(request.args.get('order[0][column]', 0))  # Column index to sort
        order_direction = request.args.get('order[0][dir]', 'asc')  # Sort direction: asc or desc
        
        # Map column index to field names
        columns_map = {
            0: None,  # S.No (not sortable)
            1: 'log_time',  # Log Time
            2: 'endpoint',  # Log
            3: 'response',  # Response
            4: 'user',  # User By
            5: 'domain'  # Where?
        }
        
        # Get sorting column
        order_column = columns_map.get(order_column_index)
        if order_column:
            order_by = f"-{order_column}" if order_direction == 'desc' else order_column
        else:
            order_by = '-log_time'  # Default sorting by time
        
        # Current user
        current_user = session.get('user')
        email = current_user.get('email')
        user = User.objects(email=email).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Base query
        logs_query = APILog.objects(user=str(user.id))
        
        # Date range filter
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        today = request.args.get('today', 'false').lower() == 'true'
        if today:
            logs_query = logs_query.filter(
                log_time__gte=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            )
        elif start_date and end_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            end_date = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            logs_query = logs_query.filter(log_time__gte=start_date, log_time__lt=end_date)
        
        # Apply search filter (case-insensitive)
        if search_value:
            logs_query = logs_query.filter(
                Q(endpoint__icontains=search_value) |
                Q(response__icontains=search_value) |
                Q(domain__icontains=search_value) |
                Q(platform__icontains=search_value) |
                Q(user__icontains=search_value)
            )
        
        # Total logs (before filtering)
        total_logs = APILog.objects(user=str(user.id)).count()
        
        # Filtered logs count
        filtered_logs = logs_query.count()
        
        # Apply sorting, pagination
        logs_query = logs_query.order_by(order_by).skip(start).limit(length)
        
        # Prepare log data
        log_data = [{
            "id": str(log.id),
            "time": log.log_time.strftime('%Y-%m-%d %H:%M:%S'),
            "endpoint": log.endpoint,
            "user": User.objects(id=log.user.id).first().username if log.user else "Unknown",
            "domain": log.domain,
            "platform": log.platform,
            "response": log.response
        } for log in logs_query]
        
        # Return data in DataTables format
        return jsonify({
            "draw": int(request.args.get('draw', 1)),  # Pass back the draw counter
            "recordsTotal": total_logs,  # Total records in the database
            "recordsFiltered": filtered_logs,  # Total records after filtering
            "data": log_data  # Actual data for the current page
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

