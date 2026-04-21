from flask import Flask, app, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
import os
import urllib.request
import urllib.parse
import json
from twilio.rest import Client
from dotenv import load_dotenv
import time
from config import Config
from sqlalchemy import inspect, text
from zoneinfo import ZoneInfo
from werkzeug.utils import secure_filename
import uuid
from sqlalchemy.exc import SQLAlchemyError

# Load local environment variables without overriding real platform env vars.
load_dotenv()

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
    check_in_active = db.Column(db.Boolean, default=False)
    check_in_deadline = db.Column(db.DateTime)
    check_in_note = db.Column(db.String(200))
    journey_active = db.Column(db.Boolean, default=False)
    journey_destination = db.Column(db.String(200))
    journey_deadline = db.Column(db.DateTime)
    journey_started_at = db.Column(db.DateTime)
    journey_last_lat = db.Column(db.Float)
    journey_last_lng = db.Column(db.Float)
    blood_group = db.Column(db.String(10))
    allergies = db.Column(db.String(200))
    medical_notes = db.Column(db.String(300))
    latest_voice_note_url = db.Column(db.String(300))
    latest_voice_note_at = db.Column(db.DateTime)
    latest_alert_type = db.Column(db.String(50))
    latest_alert_time = db.Column(db.DateTime)
    latest_alert_payload = db.Column(db.Text)
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
APP_TIMEZONE = ZoneInfo("Asia/Kolkata")


def get_local_now():
    return datetime.now(timezone.utc).astimezone(APP_TIMEZONE)


def format_local_timestamp():
    return get_local_now().strftime('%Y-%m-%d %I:%M %p')


def offset_point(lat, lng, lat_delta=0.0, lng_delta=0.0):
    return {
        'lat': round(lat + lat_delta, 6),
        'lng': round(lng + lng_delta, 6)
    }


def build_safety_heatmap_data(origin, destination=None):
    now = get_local_now()
    hour = now.hour
    night_risk = 22 if hour >= 20 or hour < 6 else 8
    evening_risk = 12 if 18 <= hour < 20 else 0

    destination = destination or origin
    center_lat = (origin['lat'] + destination['lat']) / 2
    center_lng = (origin['lng'] + destination['lng']) / 2

    hotspots = [
        {
            'name': 'Police Support Zone',
            'category': 'safe',
            'risk_score': max(18, 28 - night_risk // 2),
            'intensity': 0.18,
            'reason': 'Close to police and high-visibility roads.',
            'lat': center_lat + 0.0035,
            'lng': center_lng - 0.0025
        },
        {
            'name': 'Transit Stretch',
            'category': 'caution',
            'risk_score': 54 + evening_risk,
            'intensity': 0.54,
            'reason': 'Traffic bottlenecks and mixed lighting after sunset.',
            'lat': center_lat - 0.0015,
            'lng': center_lng + 0.004
        },
        {
            'name': 'Dark Side Street',
            'category': 'risk',
            'risk_score': min(92, 68 + night_risk),
            'intensity': 0.86,
            'reason': 'Low footfall zone with poor late-night visibility.',
            'lat': center_lat + 0.0045,
            'lng': center_lng + 0.005
        },
        {
            'name': '24x7 Pharmacy Belt',
            'category': 'safe',
            'risk_score': max(16, 24 - evening_risk // 2),
            'intensity': 0.2,
            'reason': 'Nearby pharmacy and late-hour commercial activity.',
            'lat': center_lat - 0.004,
            'lng': center_lng - 0.003
        },
        {
            'name': 'Quiet Residential Pocket',
            'category': 'caution',
            'risk_score': min(78, 46 + night_risk),
            'intensity': 0.62,
            'reason': 'Residential lane becomes isolated late at night.',
            'lat': center_lat + 0.0008,
            'lng': center_lng - 0.005
        }
    ]

    hotspots = [{
        **spot,
        'lat': round(spot['lat'], 6),
        'lng': round(spot['lng'], 6)
    } for spot in hotspots]

    return {
        'generated_at': format_local_timestamp(),
        'time_band': 'night' if hour >= 20 or hour < 6 else 'day',
        'summary': 'Risk rises after dark and drops near active public-support places.',
        'hotspots': hotspots
    }

def ensure_runtime_columns(app):
    """Keep local databases compatible without a formal migration step."""
    required_columns = {
        'check_in_active': 'ALTER TABLE "user" ADD COLUMN check_in_active BOOLEAN DEFAULT FALSE',
        'check_in_deadline': 'ALTER TABLE "user" ADD COLUMN check_in_deadline TIMESTAMP',
        'check_in_note': 'ALTER TABLE "user" ADD COLUMN check_in_note VARCHAR(200)',
        'journey_active': 'ALTER TABLE "user" ADD COLUMN journey_active BOOLEAN DEFAULT FALSE',
        'journey_destination': 'ALTER TABLE "user" ADD COLUMN journey_destination VARCHAR(200)',
        'journey_deadline': 'ALTER TABLE "user" ADD COLUMN journey_deadline TIMESTAMP',
        'journey_started_at': 'ALTER TABLE "user" ADD COLUMN journey_started_at TIMESTAMP',
        'journey_last_lat': 'ALTER TABLE "user" ADD COLUMN journey_last_lat DOUBLE PRECISION',
        'journey_last_lng': 'ALTER TABLE "user" ADD COLUMN journey_last_lng DOUBLE PRECISION',
        'blood_group': 'ALTER TABLE "user" ADD COLUMN blood_group VARCHAR(10)',
        'allergies': 'ALTER TABLE "user" ADD COLUMN allergies VARCHAR(200)',
        'medical_notes': 'ALTER TABLE "user" ADD COLUMN medical_notes VARCHAR(300)',
        'latest_voice_note_url': 'ALTER TABLE "user" ADD COLUMN latest_voice_note_url VARCHAR(300)',
        'latest_voice_note_at': 'ALTER TABLE "user" ADD COLUMN latest_voice_note_at TIMESTAMP',
        'latest_alert_type': 'ALTER TABLE "user" ADD COLUMN latest_alert_type VARCHAR(50)',
        'latest_alert_time': 'ALTER TABLE "user" ADD COLUMN latest_alert_time TIMESTAMP',
        'latest_alert_payload': 'ALTER TABLE "user" ADD COLUMN latest_alert_payload TEXT'
    }

    with app.app_context():
        inspector = inspect(db.engine)
        if 'user' not in inspector.get_table_names():
            return

        existing_columns = {column['name'] for column in inspector.get_columns('user')}
        for column_name, statement in required_columns.items():
            if column_name not in existing_columns:
                db.session.execute(text(statement))
        db.session.commit()


def send_whatsapp_messages(contacts, message_body):
    if not twilio_client:
        return {'status': 'error', 'message': 'Twilio not configured'}

    sent_messages = []
    failed_messages = []

    for contact in contacts:
        try:
            phone_clean = contact.phone.replace('+', '').replace(' ', '')
            if len(phone_clean) == 10:
                phone_clean = '91' + phone_clean

            whatsapp_to = f"whatsapp:+{phone_clean}"
            message = twilio_client.messages.create(
                body=message_body,
                from_=f'whatsapp:{os.getenv("TWILIO_PHONE_NUMBER")}',
                to=whatsapp_to
            )

            sent_messages.append({
                'name': contact.name,
                'phone': contact.phone,
                'message_id': message.sid
            })
            time.sleep(1)
        except Exception as e:
            failed_messages.append({
                'name': contact.name,
                'phone': contact.phone,
                'error': str(e)
            })

    return {
        'status': 'success' if sent_messages else 'error',
        'sent_count': len(sent_messages),
        'failed_count': len(failed_messages),
        'sent_messages': sent_messages,
        'failed_messages': failed_messages
    }


def get_voice_evidence_line(user):
    if not user.latest_voice_note_url:
        return None
    return f"Voice evidence:\n{user.latest_voice_note_url}"


def store_latest_alert(user, alert_type, result):
    user.latest_alert_type = alert_type
    user.latest_alert_time = datetime.utcnow()
    user.latest_alert_payload = json.dumps({
        'status': result.get('status'),
        'sent_count': result.get('sent_count', 0),
        'failed_count': result.get('failed_count', 0),
        'sent_messages': result.get('sent_messages', []),
        'failed_messages': result.get('failed_messages', [])
    })


def build_location_link(location_data):
    lat = location_data.get('lat')
    lng = location_data.get('lng')
    if lat is None or lng is None:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"


def send_check_in_missed_alert(user):
    contacts = EmergencyContact.query.filter_by(user_id=user.id).all()
    if not contacts:
        return {'status': 'error', 'message': 'No emergency contacts configured'}

    maps_link = build_location_link({
        'lat': user.home_lat,
        'lng': user.home_lng
    })
    location_line = maps_link or 'Home location not available in profile yet.'
    note_line = user.check_in_note or 'No destination note shared.'
    evidence_line = get_voice_evidence_line(user)

    message_body = f"""Safety Check-In Alert - Aran App

{user.name} missed their safety check-in.

Destination / Note:
{note_line}

Last saved safe location:
{location_line}

Phone: {user.phone}
Time: {format_local_timestamp()}

Please contact them immediately and verify they are safe."""

    if evidence_line:
        message_body += f"\n\n{evidence_line}"

    return send_whatsapp_messages(contacts, message_body)


def send_journey_started_alert(user):
    contacts = EmergencyContact.query.filter_by(user_id=user.id).all()
    if not contacts:
        return {'status': 'error', 'message': 'No emergency contacts configured'}

    maps_link = build_location_link({
        'lat': user.journey_last_lat,
        'lng': user.journey_last_lng
    })
    location_line = maps_link or 'Live location unavailable.'
    evidence_line = get_voice_evidence_line(user)

    message_body = f"""Journey Started - Aran App

{user.name} has started a shared journey.

Destination:
{user.journey_destination or 'Destination not provided'}

Expected arrival:
{user.journey_deadline.astimezone(APP_TIMEZONE).strftime('%Y-%m-%d %I:%M %p') if user.journey_deadline else 'Not set'}

Starting location:
{location_line}

Phone: {user.phone}
Time: {format_local_timestamp()}

You will be notified if they do not mark the journey as completed safely."""

    if evidence_line:
        message_body += f"\n\n{evidence_line}"

    return send_whatsapp_messages(contacts, message_body)


def send_journey_missed_alert(user):
    contacts = EmergencyContact.query.filter_by(user_id=user.id).all()
    if not contacts:
        return {'status': 'error', 'message': 'No emergency contacts configured'}

    maps_link = build_location_link({
        'lat': user.journey_last_lat or user.home_lat,
        'lng': user.journey_last_lng or user.home_lng
    })
    location_line = maps_link or 'Last known location unavailable.'
    evidence_line = get_voice_evidence_line(user)

    message_body = f"""Journey Alert - Aran App

{user.name} has not confirmed safe arrival for their journey.

Destination:
{user.journey_destination or 'Destination not provided'}

Last known location:
{location_line}

Phone: {user.phone}
Time: {format_local_timestamp()}

Please contact them immediately and verify they have arrived safely."""

    if evidence_line:
        message_body += f"\n\n{evidence_line}"

    return send_whatsapp_messages(contacts, message_body)


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
        evidence_line = get_voice_evidence_line(user)
        
        message_body = f"""🚨 EMERGENCY ALERT - Aran App 🚨

{user.name} needs immediate assistance!

📍 *Live Location:* 
{maps_link}

📱 User Phone: {user.phone}
🕒 Time: {format_local_timestamp()}

📊 Coordinates: {lat:.6f}, {lng:.6f}

🚑 Emergency Contacts:
• Police: 100
• Ambulance: 108  
• Women Helpline: 1091

Please check on them immediately and provide assistance!"""

        if evidence_line:
            message_body += f"\n\n{evidence_line}"

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
    app.config.from_object(Config)

    db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if db_url:
        try:
            parts = urllib.parse.urlsplit(db_url)
            masked_netloc = parts.hostname or ''
            if parts.port:
                masked_netloc += f":{parts.port}"
            safe_db_url = urllib.parse.urlunsplit((
                parts.scheme,
                masked_netloc,
                parts.path,
                parts.query,
                parts.fragment
            ))
            print("DATABASE_URL =", safe_db_url)
        except Exception:
            print("DATABASE_URL configured")

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    if app.config.get('AUTO_DB_BOOTSTRAP'):
        with app.app_context():
            try:
                db.create_all()
                ensure_runtime_columns(app)
                print("Database tables ensured")
            except SQLAlchemyError as exc:
                print(f"Database bootstrap skipped: {exc}")
    else:
        print("Automatic database bootstrap disabled")


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
            form_data = request.form if request.form else (request.get_json(silent=True) or {})
            phone = ''.join(filter(str.isdigit, (form_data.get('phone') or '')))
            password = form_data.get('password') or ''

            if not phone or not password:
                flash('Phone and password are required!', 'error')
                return render_template('login.html'), 400
            
            if len(phone) != 10:
                flash('Phone must be 10 digits!', 'error')
                return render_template('login.html'), 400
            
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
            form_data = request.form if request.form else (request.get_json(silent=True) or {})
            name = (form_data.get('name') or '').strip()
            phone = ''.join(filter(str.isdigit, (form_data.get('phone') or '')))
            password = form_data.get('password') or ''
            contact_name = (form_data.get('trusted_contact_name') or '').strip()
            contact_phone = ''.join(filter(str.isdigit, (form_data.get('trusted_contact_phone') or '')))
            contact_relationship = (form_data.get('trusted_contact_relationship') or '').strip()

            if not all([name, phone, password, contact_name, contact_phone, contact_relationship]):
                flash('Please fill in all required fields!', 'error')
                return render_template('register.html'), 400
            
            if len(phone) != 10 or len(contact_phone) != 10:
                flash('Phone numbers must be 10 digits!', 'error')
                return render_template('register.html'), 400
            
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

    @app.route('/focus-mode')
    @login_required
    def focus_mode():
        return render_template('focus-mode.html')
    
    @app.route('/route-planner')
    @login_required
    def route_planner():
        return render_template('route-planner.html', google_maps_api_key=GOOGLE_MAPS_API_KEY)
    
    @app.route('/whatsapp-setup')
    @login_required
    def whatsapp_setup():
        return render_template('whatsapp-setup.html', twilio_phone=os.getenv('TWILIO_PHONE_NUMBER'))
    
    # TEST LOCATION ACCURACY
    @app.route('/api/test_location')
    @login_required
    def test_location():
        """Test if location links work correctly"""
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

📱 Test Time: {get_local_now().strftime('%I:%M %p')}

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
            store_latest_alert(current_user, 'sos', result)
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
            store_latest_alert(current_user, 'test_whatsapp', result)
            db.session.commit()
            
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
            latest_alert = json.loads(current_user.latest_alert_payload) if current_user.latest_alert_payload else None
            return jsonify({
                'name': current_user.name,
                'phone': current_user.phone,
                'home_address': current_user.home_address,
                'home_lat': current_user.home_lat,
                'home_lng': current_user.home_lng,
                'sos_count': current_user.sos_count or 0,
                'location_share_count': current_user.location_share_count or 0,
                'journey_active': current_user.journey_active or False,
                'journey_destination': current_user.journey_destination,
                'journey_deadline': current_user.journey_deadline.isoformat() if current_user.journey_deadline else None,
                'blood_group': current_user.blood_group,
                'allergies': current_user.allergies,
                'medical_notes': current_user.medical_notes,
                'latest_voice_note_url': current_user.latest_voice_note_url,
                'latest_voice_note_at': current_user.latest_voice_note_at.isoformat() if current_user.latest_voice_note_at else None,
                'latest_alert_type': current_user.latest_alert_type,
                'latest_alert_time': current_user.latest_alert_time.isoformat() if current_user.latest_alert_time else None,
                'latest_alert': latest_alert,
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

            if 'blood_group' in data:
                current_user.blood_group = (data.get('blood_group') or '').strip()[:10] or None

            if 'allergies' in data:
                current_user.allergies = (data.get('allergies') or '').strip()[:200] or None

            if 'medical_notes' in data:
                current_user.medical_notes = (data.get('medical_notes') or '').strip()[:300] or None
            
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

    @app.route('/api/upload_voice_evidence', methods=['POST'])
    @login_required
    def upload_voice_evidence():
        try:
            if 'audio' not in request.files:
                return jsonify({'status': 'error', 'message': 'Audio file is required.'})

            audio_file = request.files['audio']
            if not audio_file.filename:
                return jsonify({'status': 'error', 'message': 'Audio file is missing.'})

            extension = os.path.splitext(secure_filename(audio_file.filename))[1] or '.webm'
            voice_dir = os.path.join(app.static_folder, 'uploads', 'voice_notes')
            os.makedirs(voice_dir, exist_ok=True)
            filename = f"user_{current_user.id}_{uuid.uuid4().hex}{extension}"
            file_path = os.path.join(voice_dir, filename)
            audio_file.save(file_path)

            current_user.latest_voice_note_url = url_for('static', filename=f'uploads/voice_notes/{filename}', _external=True)
            current_user.latest_voice_note_at = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'status': 'success',
                'message': 'Voice evidence saved.',
                'voice_note_url': current_user.latest_voice_note_url,
                'saved_at': current_user.latest_voice_note_at.isoformat()
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})

    @app.route('/api/check_in_status')
    @login_required
    def get_check_in_status():
        deadline = current_user.check_in_deadline
        active = bool(current_user.check_in_active and deadline)
        remaining_seconds = None

        if active:
            remaining_seconds = int((deadline - datetime.utcnow()).total_seconds())
            if remaining_seconds <= 0:
                remaining_seconds = 0

        return jsonify({
            'status': 'success',
            'active': active,
            'deadline': deadline.isoformat() if deadline else None,
            'remaining_seconds': remaining_seconds,
            'note': current_user.check_in_note
        })

    @app.route('/api/start_check_in_timer', methods=['POST'])
    @login_required
    def start_check_in_timer():
        try:
            data = request.get_json() or {}
            minutes = int(data.get('minutes', 0))
            note = (data.get('note') or '').strip()

            if minutes < 1 or minutes > 180:
                return jsonify({'status': 'error', 'message': 'Choose a timer between 1 and 180 minutes.'})

            current_user.check_in_active = True
            current_user.check_in_deadline = datetime.utcnow() + timedelta(minutes=minutes)
            current_user.check_in_note = note[:200] if note else None
            db.session.commit()

            return jsonify({
                'status': 'success',
                'message': 'Check-in timer started.',
                'deadline': current_user.check_in_deadline.isoformat(),
                'note': current_user.check_in_note
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})

    @app.route('/api/confirm_check_in', methods=['POST'])
    @login_required
    def confirm_check_in():
        try:
            current_user.check_in_active = False
            current_user.check_in_deadline = None
            current_user.check_in_note = None
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'Check-in marked safe.'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})

    @app.route('/api/check_in_timeout', methods=['POST'])
    @login_required
    def check_in_timeout():
        try:
            if not current_user.check_in_active or not current_user.check_in_deadline:
                return jsonify({'status': 'success', 'message': 'No active timer.'})

            if datetime.utcnow() < current_user.check_in_deadline:
                remaining = int((current_user.check_in_deadline - datetime.utcnow()).total_seconds())
                return jsonify({
                    'status': 'pending',
                    'message': 'Timer still active.',
                    'remaining_seconds': remaining
                })

            alert_result = send_check_in_missed_alert(current_user)
            store_latest_alert(current_user, 'check_in_timeout', alert_result)
            current_user.check_in_active = False
            current_user.check_in_deadline = None
            current_user.check_in_note = None
            db.session.commit()

            if alert_result.get('status') != 'success':
                return jsonify({
                    'status': 'error',
                    'message': alert_result.get('message', 'Could not send missed check-in alerts.'),
                    'result': alert_result
                })

            return jsonify({
                'status': 'success',
                'message': 'Missed check-in alerts sent to trusted contacts.',
                'result': alert_result
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})

    @app.route('/api/journey_status')
    @login_required
    def journey_status():
        deadline = current_user.journey_deadline
        active = bool(current_user.journey_active and deadline)
        remaining_seconds = None

        if active:
            remaining_seconds = int((deadline - datetime.utcnow()).total_seconds())
            if remaining_seconds <= 0:
                remaining_seconds = 0

        return jsonify({
            'status': 'success',
            'active': active,
            'destination': current_user.journey_destination,
            'deadline': deadline.isoformat() if deadline else None,
            'remaining_seconds': remaining_seconds
        })

    @app.route('/api/start_journey_sharing', methods=['POST'])
    @login_required
    def start_journey_sharing():
        try:
            data = request.get_json() or {}
            destination = (data.get('destination') or '').strip()
            minutes = int(data.get('minutes', 0))
            lat = data.get('lat')
            lng = data.get('lng')

            if not destination:
                return jsonify({'status': 'error', 'message': 'Destination is required.'})

            if minutes < 5 or minutes > 300:
                return jsonify({'status': 'error', 'message': 'Journey timer must be between 5 and 300 minutes.'})

            current_user.journey_active = True
            current_user.journey_destination = destination[:200]
            current_user.journey_started_at = datetime.utcnow()
            current_user.journey_deadline = datetime.utcnow() + timedelta(minutes=minutes)
            current_user.journey_last_lat = lat
            current_user.journey_last_lng = lng
            db.session.commit()

            alert_result = send_journey_started_alert(current_user)
            store_latest_alert(current_user, 'journey_started', alert_result)
            db.session.commit()

            return jsonify({
                'status': 'success',
                'message': 'Journey sharing started.',
                'destination': current_user.journey_destination,
                'deadline': current_user.journey_deadline.isoformat(),
                'result': alert_result
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})

    @app.route('/api/complete_journey', methods=['POST'])
    @login_required
    def complete_journey():
        try:
            current_user.journey_active = False
            current_user.journey_destination = None
            current_user.journey_deadline = None
            current_user.journey_started_at = None
            current_user.journey_last_lat = None
            current_user.journey_last_lng = None
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'Journey marked completed safely.'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)})

    @app.route('/api/journey_timeout', methods=['POST'])
    @login_required
    def journey_timeout():
        try:
            data = request.get_json() or {}
            lat = data.get('lat')
            lng = data.get('lng')

            if lat is not None:
                current_user.journey_last_lat = lat
            if lng is not None:
                current_user.journey_last_lng = lng

            if not current_user.journey_active or not current_user.journey_deadline:
                db.session.commit()
                return jsonify({'status': 'success', 'message': 'No active journey.'})

            if datetime.utcnow() < current_user.journey_deadline:
                remaining = int((current_user.journey_deadline - datetime.utcnow()).total_seconds())
                db.session.commit()
                return jsonify({
                    'status': 'pending',
                    'message': 'Journey still active.',
                    'remaining_seconds': remaining
                })

            alert_result = send_journey_missed_alert(current_user)
            store_latest_alert(current_user, 'journey_timeout', alert_result)
            current_user.journey_active = False
            current_user.journey_destination = None
            current_user.journey_deadline = None
            current_user.journey_started_at = None
            current_user.journey_last_lat = None
            current_user.journey_last_lng = None
            db.session.commit()

            if alert_result.get('status') != 'success':
                return jsonify({
                    'status': 'error',
                    'message': alert_result.get('message', 'Could not send missed journey alerts.'),
                    'result': alert_result
                })

            return jsonify({
                'status': 'success',
                'message': 'Journey timeout alerts sent to trusted contacts.',
                'result': alert_result
            })
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
                    'start_location': leg['start_location'],
                    'end_location': leg['end_location'],
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

        current_hour = get_local_now().hour
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

    @app.route('/api/get_safety_heatmap', methods=['POST'])
    @login_required
    def get_safety_heatmap():
        try:
            data = request.get_json() or {}
            origin = data.get('origin') or {}
            destination = data.get('destination') or {}

            origin_lat = origin.get('lat')
            origin_lng = origin.get('lng')
            if origin_lat is None or origin_lng is None:
                return jsonify({'status': 'error', 'message': 'Origin coordinates are required'})

            origin_point = {
                'lat': float(origin_lat),
                'lng': float(origin_lng)
            }

            destination_point = None
            if destination.get('lat') is not None and destination.get('lng') is not None:
                destination_point = {
                    'lat': float(destination['lat']),
                    'lng': float(destination['lng'])
                }

            heatmap_data = build_safety_heatmap_data(origin_point, destination_point)
            return jsonify({
                'status': 'success',
                **heatmap_data
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    
    return app

app = create_app()

if __name__ == "__main__":

    print("🚀 Aran Women Safety App Started Successfully!")
    print("📧 Register: http://localhost:5000/register")
    print("🔐 Login: http://localhost:5000/login")
    print("📱 WhatsApp Setup: http://localhost:5000/whatsapp-setup")
    print("📍 Location Test: http://localhost:5000/api/test_location")
    print("💬 Quick Test: http://localhost:5000/api/quick_test")
    print("✅ WhatsApp Integration: ACTIVE")
    print("✅ Google Maps Links: FIXED for accurate locations")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
