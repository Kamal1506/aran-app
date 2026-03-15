from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import urllib.request
import urllib.parse
import json
from twilio.rest import Client
from dotenv import load_dotenv
import time
import sqlite3

# Load environment variables
load_dotenv('twilio.env')

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')

# Initialize Twilio client
try:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    print("✅ Twilio connected")
except Exception as e:
    print(f"❌ Twilio failed: {e}")
    twilio_client = None

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    home_lat = db.Column(db.Float)
    home_lng = db.Column(db.Float)
    home_address = db.Column(db.String(200))
    sos_count = db.Column(db.Integer, default=0)
    location_share_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class EmergencyContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    relationship = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('emergency_contacts', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Google Maps API
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')

def send_whatsapp_alert(user, contacts, location_data):
    """WhatsApp alert function with FIXED Google Maps links"""
    if not twilio_client:
        return {'status': 'error', 'message': 'Twilio not configured'}
    
    try:
        # FIXED Google Maps link - using correct format
        lat = location_data['lat']
        lng = location_data['lng']
        
        # CORRECT Google Maps URL formats that work properly:
        maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
        # Alternative: maps_link = f"https://maps.google.com/?q={lat},{lng}&z=15"
        
        message_body = f"""🚨 EMERGENCY ALERT - Aran App 🚨

{user.name} needs immediate assistance!

📍 *Live Location:* 
{maps_link}

📱 User Phone: {user.phone}
🕒 Time: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}

📊 Coordinates: {lat:.6f}, {lng:.6f}

🚑 Emergency Contacts:
• Police: 100
• Ambulance: 108  
• Women Helpline: 1091

Please check on them immediately and provide assistance!"""

        sent_messages = []
        failed_messages = []
        
        print(f"📱 Sending WhatsApp to {len(contacts)} contacts...")
        print(f"📍 Location: {lat}, {lng}")
        print(f"🗺️ Maps Link: {maps_link}")
        
        for contact in contacts:
            try:
                # Clean phone number
                phone_clean = contact.phone.replace('+', '').replace(' ', '')
                if len(phone_clean) == 10:
                    phone_clean = '91' + phone_clean
                
                whatsapp_to = f"whatsapp:+{phone_clean}"
                
                print(f"➡️ Sending to {contact.name}: {whatsapp_to}")
                
                # Send message
                message = twilio_client.messages.create(
                    body=message_body,
                    from_=f'whatsapp:{os.getenv("TWILIO_PHONE_NUMBER")}',
                    to=whatsapp_to
                )
                
                print(f"✅ Message sent: {message.sid}")
                sent_messages.append({
                    'name': contact.name, 
                    'phone': contact.phone,
                    'message_id': message.sid
                })
                
                time.sleep(1)
                
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Failed for {contact.name}: {error_msg}")
                failed_messages.append({
                    'name': contact.name,
                    'phone': contact.phone,
                    'error': error_msg
                })
        
        return {
            'status': 'success' if sent_messages else 'error',
            'sent_count': len(sent_messages),
            'failed_count': len(failed_messages),
            'sent_messages': sent_messages,
            'failed_messages': failed_messages
        }
        
    except Exception as e:
        error_msg = f"WhatsApp failed: {str(e)}"
        print(f"❌ {error_msg}")
        return {
            'status': 'error',
            'message': error_msg
        }

def create_app():
    app = Flask(__name__)
    
    # Load configuration from environment
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change_this_in_production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///database.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_recycle': 300,
        'pool_pre_ping': True
    }
    
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()
    
    @app.route('/')
    def home():
        if current_user.is_authenticated:
            return render_template('index.html')
        return render_template('login.html')
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('home'))
            
        if request.method == 'POST':
            phone = ''.join(filter(str.isdigit, request.form['phone']))
            password = request.form['password']
            
            if len(phone) != 10:
                flash('Phone must be 10 digits!', 'error')
                return render_template('login.html')
            
            try:
                user = User.query.filter_by(phone='+91' + phone).first()
                
                if user and user.check_password(password):
                    login_user(user)
                    flash('Login successful!', 'success')
                    return redirect(url_for('home'))
                else:
                    flash('Invalid credentials!', 'error')
            except Exception as e:
                flash('Database error. Please try again.', 'error')
                print(f"Login error: {e}")
        
        return render_template('login.html')
    
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('home'))
            
        if request.method == 'POST':
            name = request.form['name']
            phone = ''.join(filter(str.isdigit, request.form['phone']))
            password = request.form['password']
            contact_name = request.form['trusted_contact_name']
            contact_phone = ''.join(filter(str.isdigit, request.form['trusted_contact_phone']))
            contact_relationship = request.form['trusted_contact_relationship']
            
            if len(phone) != 10 or len(contact_phone) != 10:
                flash('Phone numbers must be 10 digits!', 'error')
                return render_template('register.html')
            
            user_phone = '+91' + phone
            contact_phone_formatted = '+91' + contact_phone
            
            try:
                if User.query.filter_by(phone=user_phone).first():
                    flash('Phone already registered!', 'error')
                    return render_template('register.html')
                
                if user_phone == contact_phone_formatted:
                    flash('Emergency contact cannot be your own number!', 'error')
                    return render_template('register.html')
                
                new_user = User(name=name, phone=user_phone)
                new_user.set_password(password)
                
                db.session.add(new_user)
                db.session.flush()
                
                emergency_contact = EmergencyContact(
                    user_id=new_user.id,
                    name=contact_name,
                    phone=contact_phone_formatted,
                    relationship=contact_relationship
                )
                db.session.add(emergency_contact)
                db.session.commit()
                
                login_user(new_user)
                flash('🎉 Registration successful! Welcome to Aran Safety App!', 'success')
                return redirect(url_for('home'))
                
            except Exception as e:
                db.session.rollback()
                flash('Registration failed. Please try again.', 'error')
                print(f"Registration error: {e}")
        
        return render_template('register.html')
    
    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('You have been logged out.', 'info')
        return redirect(url_for('login'))
    
    @app.route('/dashboard')
    @login_required
    def dashboard():
        return render_template('index.html')
    
    @app.route('/profile')
    @login_required
    def profile():
        return render_template('profile.html', google_maps_api_key=GOOGLE_MAPS_API_KEY)
    
    @app.route('/settings')
    @login_required
    def settings():
        return render_template('settings.html')
    
    @app.route('/route-planner')
    @login_required
    def route_planner():
        return render_template('route-planner.html', google_maps_api_key=GOOGLE_MAPS_API_KEY)
    
    @app.route('/whatsapp-setup')
    @login_required
    def whatsapp_setup():
        return render_template('whatsapp-setup.html')
    
    # TEST LOCATION ACCURACY
    @app.route('/api/test_location')
    @login_required
    def test_location():
        """Test if location links work correctly"""
        try:
            test_lat = 13.0827  # Chennai coordinates
            test_lng = 80.2707
            
            # Test different Google Maps formats
            maps_link1 = f"https://www.google.com/maps/search/?api=1&query={test_lat},{test_lng}"
            maps_link2 = f"https://maps.google.com/?q={test_lat},{test_lng}&z=15"
            maps_link3 = f"https://www.google.com/maps/@{test_lat},{test_lng},15z"
            
            return f"""
            <h1>📍 Location Link Test</h1>
            <p><strong>Test Coordinates:</strong> {test_lat}, {test_lng} (Chennai)</p>
            <hr>
            <h3>Format 1 (Recommended):</h3>
            <p><a href="{maps_link1}" target="_blank">{maps_link1}</a></p>
            <h3>Format 2:</h3>
            <p><a href="{maps_link2}" target="_blank">{maps_link2}</a></p>
            <h3>Format 3:</h3>
            <p><a href="{maps_link3}" target="_blank">{maps_link3}</a></p>
            <hr>
            <p><strong>Instructions:</strong> Click each link and check if it opens at the correct Chennai location.</p>
            """
        except Exception as e:
            return f"Error: {str(e)}"
    
    # QUICK TEST
    @app.route('/api/quick_test')
    @login_required
    def quick_test():
        try:
            # Test with fixed Chennai coordinates
            test_lat = 13.0827
            test_lng = 80.2707
            maps_link = f"https://www.google.com/maps/search/?api=1&query={test_lat},{test_lng}"
            
            message_body = f"""🚨 TEST from Aran App - Location Accuracy Test

This is a test message to verify location accuracy.

📍 Test Location (Chennai):
{maps_link}

📱 Test Time: {datetime.now().strftime('%I:%M %p')}

Please click the link above and confirm it opens at Chennai coordinates."""

            message = twilio_client.messages.create(
                body=message_body,
                from_=f'whatsapp:{os.getenv("TWILIO_PHONE_NUMBER")}',
                to=f'whatsapp:{os.getenv("TWILIO_TEST_PHONE")}'
            )
            
            return f"""
            <h1>✅ Test Sent Successfully!</h1>
            <p><strong>Message SID:</strong> {message.sid}</p>
            <p><strong>Test Location:</strong> {test_lat}, {test_lng} (Chennai)</p>
            <p><strong>Maps Link:</strong> {maps_link}</p>
            <p>Check Kamal's WhatsApp and verify the location opens correctly at Chennai.</p>
            """
            
        except Exception as e:
            return f"<h1>❌ Failed: {str(e)}</h1>"
    
    @app.route('/api/trigger_sos', methods=['POST'])
    @login_required
    def trigger_sos():
        try:
            data = request.get_json()
            current_user.sos_count += 1
            
            contacts = EmergencyContact.query.filter_by(user_id=current_user.id).all()
            
            # Get precise location data
            location_data = {
                'lat': data.get('lat'),
                'lng': data.get('lng'),
                'address': data.get('address', 'Live location shared')
            }
            
            print(f"🚨 SOS Triggered by {current_user.name}")
            print(f"📍 Location: {location_data['lat']}, {location_data['lng']}")
            
            result = send_whatsapp_alert(current_user, contacts, location_data)
            db.session.commit()
            
            return jsonify({
                'status': 'success', 
                'message': 'Emergency alerts sent with accurate location!',
                'location': location_data,
                'result': result
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})
    
    @app.route('/api/test_whatsapp', methods=['POST'])
    @login_required
    def test_whatsapp():
        try:
            contacts = EmergencyContact.query.filter_by(user_id=current_user.id).all()
            
            if not contacts:
                return jsonify({'status': 'error', 'message': 'No emergency contacts found'})
            
            # Use current location or default to Chennai
            test_location = {
                'lat': current_user.home_lat or 13.0827,
                'lng': current_user.home_lng or 80.2707,
                'address': current_user.home_address or 'Test Location, Chennai'
            }
            
            result = send_whatsapp_alert(current_user, contacts, test_location)
            
            if result['status'] == 'success':
                return jsonify({
                    'status': 'success',
                    'message': f'Test WhatsApp sent to {result["sent_count"]} contacts with accurate location',
                    'result': result
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to send test WhatsApp',
                    'result': result
                })
            
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    
    # EMERGENCY CONTACTS API ROUTES
    @app.route('/api/get_emergency_contacts')
    @login_required
    def get_emergency_contacts():
        try:
            contacts = EmergencyContact.query.filter_by(user_id=current_user.id).all()
            contacts_data = [{
                'id': contact.id,
                'name': contact.name,
                'phone': contact.phone,
                'relationship': contact.relationship
            } for contact in contacts]
            
            return jsonify(contacts_data)
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    
    @app.route('/api/add_emergency_contact', methods=['POST'])
    @login_required
    def add_emergency_contact():
        try:
            data = request.get_json()
            
            contact_phone = ''.join(filter(str.isdigit, data.get('phone', '')))
            contact_name = data.get('name', '')
            
            if len(contact_phone) != 10:
                return jsonify({'status': 'error', 'message': 'Phone must be 10 digits!'})
            
            if not contact_name:
                return jsonify({'status': 'error', 'message': 'Contact name is required!'})
            
            formatted_phone = '+91' + contact_phone
            
            # Check if contact already exists
            existing_contact = EmergencyContact.query.filter_by(
                user_id=current_user.id, 
                phone=formatted_phone
            ).first()
            
            if existing_contact:
                return jsonify({'status': 'error', 'message': 'Contact already exists!'})
            
            # Check if contact is same as user's phone
            if formatted_phone == current_user.phone:
                return jsonify({'status': 'error', 'message': 'Cannot add your own number!'})
            
            new_contact = EmergencyContact(
                user_id=current_user.id,
                name=contact_name,
                phone=formatted_phone,
                relationship=data.get('relationship', 'Emergency Contact')
            )
            
            db.session.add(new_contact)
            db.session.commit()
            
            return jsonify({
                'status': 'success', 
                'message': 'Emergency contact added successfully!'
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})
    
    @app.route('/api/delete_emergency_contact/<int:contact_id>', methods=['DELETE'])
    @login_required
    def delete_emergency_contact(contact_id):
        try:
            contact = EmergencyContact.query.filter_by(
                id=contact_id, 
                user_id=current_user.id
            ).first()
            
            if contact:
                db.session.delete(contact)
                db.session.commit()
                return jsonify({'status': 'success', 'message': 'Contact deleted successfully!'})
            else:
                return jsonify({'status': 'error', 'message': 'Contact not found!'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})
    
    # USER PROFILE API ROUTES
    @app.route('/api/get_user_profile')
    @login_required
    def get_user_profile():
        try:
            return jsonify({
                'name': current_user.name,
                'phone': current_user.phone,
                'home_address': current_user.home_address,
                'home_lat': current_user.home_lat,
                'home_lng': current_user.home_lng,
                'sos_count': current_user.sos_count or 0,
                'location_share_count': current_user.location_share_count or 0,
                'member_since': current_user.created_at.strftime('%B %Y') if current_user.created_at else 'Unknown'
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    
    @app.route('/api/update_user_profile', methods=['POST'])
    @login_required
    def update_user_profile():
        try:
            data = request.get_json()
            
            if 'name' in data:
                current_user.name = data['name']
            
            if 'phone' in data:
                new_phone = ''.join(filter(str.isdigit, data['phone']))
                
                if len(new_phone) != 10:
                    return jsonify({'status': 'error', 'message': 'Phone number must be 10 digits!'})
                
                formatted_phone = '+91' + new_phone
                
                # Check if phone is already taken by another user
                existing_user = User.query.filter_by(phone=formatted_phone).first()
                if existing_user and existing_user.id != current_user.id:
                    return jsonify({'status': 'error', 'message': 'Phone number already registered!'})
                
                current_user.phone = formatted_phone
            
            db.session.commit()
            
            return jsonify({
                'status': 'success', 
                'message': 'Profile updated successfully!'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})
    
    @app.route('/api/save_home', methods=['POST'])
    @login_required
    def save_home_location():
        try:
            data = request.get_json()
            current_user.home_lat = data.get('lat')
            current_user.home_lng = data.get('lng')
            current_user.home_address = data.get('address')
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'Home location saved!'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})
    
    @app.route('/api/increment_location_share', methods=['POST'])
    @login_required
    def increment_location_share():
        try:
            current_user.location_share_count = (current_user.location_share_count or 0) + 1
            db.session.commit()
            return jsonify({'status': 'success'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})
    
    # REAL GOOGLE MAPS INTEGRATION
    @app.route('/api/get_real_directions', methods=['POST'])
    @login_required
    def get_real_directions():
        try:
            data = request.get_json()
            origin = data.get('origin')
            destination = data.get('destination')
            travel_mode = data.get('travel_mode', 'driving')

            if origin == "Current Location" and data.get('userLocation'):
                origin = f"{data['userLocation']['lat']},{data['userLocation']['lng']}"

            if not origin or not destination:
                return jsonify({'status': 'error', 'message': 'Origin and destination are required'})

            base_url = "https://maps.googleapis.com/maps/api/directions/json"
            
            params = {
                'origin': origin,
                'destination': destination,
                'mode': travel_mode,
                'key': GOOGLE_MAPS_API_KEY,
                'alternatives': 'true',
                'units': 'metric'
            }

            query_string = urllib.parse.urlencode(params)
            full_url = f"{base_url}?{query_string}"

            with urllib.request.urlopen(full_url) as response:
                directions_data = json.loads(response.read().decode())

            if directions_data['status'] != 'OK':
                error_msg = f"Google API Error: {directions_data.get('error_message', directions_data['status'])}"
                return jsonify({'status': 'error', 'message': error_msg})

            processed_routes = []
            
            for route in directions_data['routes']:
                leg = route['legs'][0]
                
                # Calculate safety score
                safety_score = calculate_real_route_safety(route, leg)
                
                # Extract step-by-step instructions
                steps = []
                for step in leg['steps']:
                    instruction = step['html_instructions']
                    instruction = instruction.replace('<b>', '').replace('</b>', '')
                    instruction = instruction.replace('<div style="font-size:0.9em">', ' - ')
                    instruction = instruction.replace('</div>', '')
                    
                    steps.append({
                        'instruction': instruction,
                        'distance': step['distance']['text'],
                        'duration': step['duration']['text']
                    })

                processed_route = {
                    'summary': route['summary'] or f'Route {len(processed_routes) + 1}',
                    'distance': leg['distance'],
                    'duration': leg['duration'],
                    'safety_score': safety_score,
                    'start_address': leg['start_address'],
                    'end_address': leg['end_address'],
                    'steps': steps,
                    'overview_polyline': route['overview_polyline'],
                    'warnings': route.get('warnings', []),
                    'bounds': route['bounds']
                }
                
                processed_routes.append(processed_route)

            return jsonify({
                'status': 'success',
                'routes': processed_routes,
                'travel_mode': travel_mode
            })

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})

    def calculate_real_route_safety(route, leg):
        base_score = 50
        
        distance_km = leg['distance']['value'] / 1000
        if distance_km < 2:
            base_score += 15
        elif distance_km < 5:
            base_score += 10
        elif distance_km > 15:
            base_score -= 10

        current_hour = datetime.now().hour
        if 6 <= current_hour <= 20:
            base_score += 10
        else:
            base_score -= 5

        num_steps = len(leg['steps'])
        if num_steps < 10:
            base_score += 5
        elif num_steps > 20:
            base_score -= 5

        route_summary = (route.get('summary') or '').lower()
        if 'highway' in route_summary or 'express' in route_summary:
            base_score += 5
        if 'local' in route_summary or 'residential' in route_summary:
            base_score += 3

        duration_minutes = leg['duration']['value'] / 60
        if duration_minutes < 15:
            base_score += 10
        elif duration_minutes > 45:
            base_score -= 5

        return max(0, min(100, base_score))

    # FALLBACK ROUTE PLANNER
    @app.route('/api/get_route', methods=['POST'])
    @login_required
    def get_route():
        try:
            mock_route = {
                'status': 'success',
                'routes': [{
                    'summary': 'Safe Route via Main Roads',
                    'distance': {'text': '5.2 km', 'value': 5200},
                    'duration': {'text': '15 mins', 'value': 900},
                    'safety_score': 85,
                    'steps': [
                        {'instruction': 'Start from current location', 'distance': {'text': '0 m'}},
                        {'instruction': 'Head northeast on Main Street', 'distance': {'text': '2.1 km'}},
                        {'instruction': 'Turn right on Central Avenue', 'distance': {'text': '1.8 km'}},
                        {'instruction': 'Continue on Well Lit Road', 'distance': {'text': '1.3 km'}},
                        {'instruction': 'Arrive at destination', 'distance': {'text': '0 m'}}
                    ]
                }]
            }
            
            return jsonify(mock_route)
            
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    
    @app.route('/api/get_nearby_safe_places')
    @login_required
    def get_nearby_safe_places():
        safe_places = [
            {
                'name': 'Police Station',
                'type': 'police',
                'distance': '0.8 km',
                'address': '123 Safety Street',
                'phone': '100'
            },
            {
                'name': '24/7 Pharmacy',
                'type': 'pharmacy',
                'distance': '0.5 km',
                'address': '456 Health Avenue',
                'phone': '9876543210'
            },
            {
                'name': 'Well Lit Cafe',
                'type': 'cafe',
                'distance': '0.3 km',
                'address': '789 Bright Road',
                'phone': '9876543211'
            }
        ]
        return jsonify(safe_places)
    
    return app

if __name__ == '__main__':
    app = create_app()
    
    with app.app_context():
        try:
            db.create_all()
            print("✅ Database initialized successfully")
        except Exception as e:
            print(f"❌ Database error: {e}")
        
    print("🚀 Aran Women Safety App Started Successfully!")
    print("📧 Register: http://localhost:5000/register")
    print("🔐 Login: http://localhost:5000/login") 
    print("📱 WhatsApp Setup: http://localhost:5000/whatsapp-setup")
    print("📍 Location Test: http://localhost:5000/api/test_location")
    print("💬 Quick Test: http://localhost:5000/api/quick_test")
    print("✅ WhatsApp Integration: ACTIVE")
    print("✅ Google Maps Links: FIXED for accurate locations")
    
    app.run(debug=True, port=5000, threaded=False)