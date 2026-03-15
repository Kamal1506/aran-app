from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models.user import db
from datetime import datetime

emergency_bp = Blueprint('emergency', __name__)

@emergency_bp.route('/trigger_sos', methods=['POST'])
@login_required
def trigger_sos():
    try:
        data = request.get_json()
        
        # Get emergency location
        emergency_lat = data.get('lat')
        emergency_lng = data.get('lng')
        
        # In a real application, you would:
        # 1. Send SMS to emergency contacts
        # 2. Notify authorities
        # 3. Log the emergency event
        
        print(f"🚨 EMERGENCY ALERT! User: {current_user.phone}")
        print(f"📍 Location: {emergency_lat}, {emergency_lng}")
        
        return jsonify({
            'status': 'success',
            'message': 'Emergency alert sent! Help is on the way.',
            'alert_id': 'EMG_' + str(current_user.id) + '_' + str(int(datetime.now().timestamp()))
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@emergency_bp.route('/save_emergency_contact', methods=['POST'])
@login_required
def save_emergency_contact():
    try:
        data = request.get_json()
        contact = data.get('contact')
        
        current_user.emergency_contact = contact
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Emergency contact saved!'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500