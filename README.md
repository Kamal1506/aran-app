# 🛡️ Aran - Women Safety Application

A comprehensive Flask-based web application designed to enhance women's safety through emergency alerts, location sharing, and safe route planning. Built with security and privacy as core principles.

---

## 📋 Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Usage](#usage)
- [API Endpoints](#api-endpoints)
- [Security](#security)
- [Contributing](#contributing)
- [License](#license)

---

## ✨ Features

### 🚨 Emergency SOS
- Trigger emergency alerts with one click
- Automatic location sharing with emergency contacts
- Real-time WhatsApp notifications to contacts
- Emergency alert tracking and logging

### 📍 Location Tracking
- Real-time location sharing
- Safe route planning with safety scores
- Google Maps integration
- Location history

### 👥 Emergency Contacts
- Add/manage emergency contacts
- Store contact relationships
- Priority-based notifications
- Contact verification

### 🗺️ Safe Route Planner
- Alternative route suggestions
- Safety scoring for routes
- Well-lit area preferences
- Real-time navigation

### 🔐 User Management
- Secure user authentication
- Password hashing
- User profile management
- Home location storage

### 💬 WhatsApp Integration
- Send emergency alerts via WhatsApp
- Real-time notifications
- Location link sharing
- Multi-contact messaging

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend Framework** | Flask 2.3.3 |
| **Database** | SQLite with SQLAlchemy |
| **Authentication** | Flask-Login |
| **API Integration** | Twilio (WhatsApp), Google Maps |
| **Frontend** | HTML5, CSS3, Bootstrap 5, JavaScript |
| **Security** | Werkzeug (password hashing), python-dotenv |
| **Environment Management** | python-dotenv 1.0.0 |

---

## 📁 Project Structure

```
aran-app/
├── app.py                      # Main Flask application
├── config.py                   # Configuration management
├── twilio.env                  # Environment variables (DO NOT COMMIT)
├── .env.example                # Template for environment variables
├── requirements.txt            # Python dependencies
├── SECURITY_MIGRATION.md       # Security setup documentation
├── README.md                   # This file
│
├── models/
│   └── user.py                # User and EmergencyContact models
│
├── routes/
│   ├── auth.py                # Authentication routes
│   ├── emergency.py           # Emergency/SOS routes
│   └── location.py            # Location routes
│
├── templates/                  # HTML templates
│   ├── base.html              # Base template
│   ├── index.html             # Home page
│   ├── login.html             # Login page
│   ├── register.html          # Registration page
│   ├── profile.html           # User profile
│   ├── settings.html          # App settings
│   ├── route-planner.html     # Route planning
│   └── whatsapp-setup.html    # WhatsApp setup
│
├── static/                     # Static files
│   ├── css/
│   │   └── style.css          # Custom styles
│   └── js/                    # JavaScript files
│
└── instance/                   # Instance folder (auto-generated)
    └── database.db            # SQLite database
```

---

## 📦 Prerequisites

- **Python 3.8+** - Programming language
- **pip** - Python package manager
- **Twilio Account** - For WhatsApp messaging
- **Google Maps API Key** - For mapping features
- **Modern Web Browser** - For accessing the application

---

## 🚀 Installation

### Step 1: Clone or Download the Project

```bash
cd aran-app
```

### Step 2: Create Virtual Environment (Optional but Recommended)

```bash
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Set Up Environment Variables

```bash
# Copy the example file
copy .env.example twilio.env

# Or on macOS/Linux
cp .env.example twilio.env
```

---

## ⚙️ Configuration

Edit `twilio.env` with your actual credentials:

```env
# Twilio Configuration
TWILIO_ACCOUNT_SID=your_actual_twilio_sid
TWILIO_AUTH_TOKEN=your_actual_twilio_token
TWILIO_PHONE_NUMBER=+1415...your_twilio_number
TWILIO_TEST_PHONE=+91...your_test_phone

# Google Maps API
GOOGLE_MAPS_API_KEY=your_actual_google_maps_key

# Flask Configuration
SECRET_KEY=your_generated_secret_key
FLASK_ENV=development
DEBUG=True
```

### Getting Credentials

| Credential | Source | Instructions |
|-----------|--------|--------------|
| Twilio SID & Token | [Twilio Console](https://www.twilio.com/console) | Account → API Keys & Tokens |
| Twilio Phone | [Twilio Console](https://www.twilio.com/console) | Phone Numbers → Manage Numbers |
| Google Maps Key | [Google Cloud Console](https://console.cloud.google.com) | APIs & Services → Credentials |
| Secret Key | Generate | `python -c "import secrets; print(secrets.token_hex(32))"` |

### Security Note

⚠️ **Never commit `twilio.env` to Git!** It's protected by `.gitignore`. Always use `.env.example` as a template.

---

## ▶️ Running the Application

### Development Server

```bash
python app.py
```

The application will start at: **http://localhost:5000**

### Production Server

```bash
# Set environment to production
set FLASK_ENV=production
set DEBUG=False

# Run with production server (e.g., Gunicorn)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:create_app()
```

---

## 📱 Usage

### 1. **Register/Login**
   - Navigate to http://localhost:5000/register
   - Create account with phone number and password
   - Login with credentials

### 2. **Add Emergency Contacts**
   - Go to Profile → Emergency Contacts
   - Add contact name, phone, and relationship
   - Save contact

### 3. **Set Home Location**
   - Go to Profile → Home Location
   - Allow browser location access or manually enter address
   - Save location

### 4. **Trigger Emergency SOS**
   - Click the SOS button (large red button)
   - Confirm emergency
   - Alerts sent to all emergency contacts via WhatsApp
   - Your location shared automatically

### 5. **Plan Safe Routes**
   - Go to Route Planner
   - Enter start and destination locations
   - View routes with safety scores
   - Select preferred route

---

## 🔌 API Endpoints

### Authentication
- `POST /register` - User registration
- `POST /login` - User login
- `GET /logout` - User logout

### Emergency/SOS
- `POST /api/trigger_sos` - Trigger emergency alert
- `POST /api/test_whatsapp` - Send test WhatsApp message

### Location
- `POST /api/save_home` - Save home location
- `GET /api/get_current_location` - Get current location
- `POST /api/get_real_directions` - Get route directions

### Profile
- `GET /api/get_user_profile` - Get user information
- `POST /api/update_user_profile` - Update user profile
- `POST /api/add_emergency_contact` - Add emergency contact
- `DELETE /api/delete_emergency_contact/<id>` - Delete contact

---

## 🔐 Security

### Implemented Security Measures

✅ **Environment Variables** - All credentials in `.env` files
✅ **Password Hashing** - Using Werkzeug security
✅ **Session Management** - Flask-Login for authentication
✅ **CSRF Protection** - Flask built-in protection
✅ **SQL Injection Prevention** - SQLAlchemy ORM
✅ **HTTPS Ready** - Can be deployed with SSL/TLS
✅ **Secure Headers** - Recommended for production

### Security Migration

See [SECURITY_MIGRATION.md](SECURITY_MIGRATION.md) for detailed information about:
- How secrets are managed
- Environment variable setup
- Best practices for deployment
- Production recommendations

---

## 📚 Database Models

### User Model
- `id` - Primary key
- `name` - User's name
- `phone` - Phone number (unique)
- `password_hash` - Hashed password
- `home_lat`, `home_lng` - Home coordinates
- `home_address` - Home address
- `sos_count` - Number of SOS alerts sent
- `location_share_count` - Location shares count
- `created_at` - Registration timestamp

### EmergencyContact Model
- `id` - Primary key
- `user_id` - Foreign key to User
- `name` - Contact name
- `phone` - Contact phone number
- `relationship` - Relationship type
- `created_at` - Creation timestamp

---

## 🐛 Troubleshooting

### Issue: `NameError: name 'load_dotenv' is not defined`
**Solution:** Install python-dotenv: `pip install python-dotenv`

### Issue: Twilio not connecting
**Solution:** Check `twilio.env` has valid credentials and is in project root

### Issue: Google Maps not loading
**Solution:** Verify `GOOGLE_MAPS_API_KEY` is valid in `twilio.env`

### Issue: Port 5000 already in use
**Solution:** Change port: `python -c "from app import app; app.run(port=5001)"`

### Issue: Database errors
**Solution:** Delete `instance/database.db` and restart app to reinitialize

---

## 📖 Documentation

- [Security Migration Guide](SECURITY_MIGRATION.md) - Environment setup
- [Flask Documentation](https://flask.palletsprojects.com) - Framework docs
- [Twilio Documentation](https://www.twilio.com/docs) - WhatsApp API
- [Google Maps API](https://developers.google.com/maps) - Mapping service

---

## 🤝 Contributing

To contribute to this project:

1. Create a new branch for your feature
2. Make your changes
3. Test thoroughly
4. Submit a pull request with detailed description

### Coding Standards
- Follow PEP 8 for Python code
- Use meaningful variable names
- Comment complex logic
- Test all new features

---

## 📝 License

This project is provided as-is for educational and personal use.

---

## 👥 Support

For issues, questions, or suggestions:
- Check existing issues/documentation
- Review [SECURITY_MIGRATION.md](SECURITY_MIGRATION.md)
- Contact project maintainer

---

## 🔄 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | Feb 2026 | Initial release |
| 1.1.0 | Feb 2026 | Security migration to environment variables |

---

## ⚠️ Important Notes

- **Never hardcode credentials** in source files
- **Always use environment variables** for sensitive data
- **Test WhatsApp integration** before production use
- **Verify Google Maps API** permissions for location features
- **Keep dependencies updated** regularly

---

**Last Updated:** February 23, 2026

**Built with ❤️ for Women's Safety**
