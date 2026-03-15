from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models.user import db
from datetime import datetime

location_bp = Blueprint('location', __name__)

@location_bp.route('/save_home_location', methods=['POST'])
@login_required
def save_home_location():
    try:
        data = request.get_json()
        
        current_user.home_lat = data.get('lat')
        current_user.home_lng = data.get('lng')
        current_user.home_address = data.get('address')
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Home location saved successfully!'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@location_bp.route('/get_home_location')
@login_required
def get_home_location():
    return jsonify({
        'home_lat': current_user.home_lat,
        'home_lng': current_user.home_lng,
        'home_address': current_user.home_address
    })

@location_bp.route('/get_current_location')
@login_required
def get_current_location():
    # This would typically get location from frontend
    # For now, return a mock response
    return jsonify({
        'current_lat': 13.0827,  # Chennai coordinates
        'current_lng': 80.2707
    })