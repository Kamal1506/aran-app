import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from dotenv import load_dotenv

load_dotenv()


def _get_database_url():
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        raise ValueError("DATABASE_URL is not set")

    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    if database_url.startswith('postgresql://') or database_url.startswith('postgresql+psycopg2://'):
        parts = urlsplit(database_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.setdefault('sslmode', os.getenv('DB_SSLMODE', 'require'))
        database_url = urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment
        ))

    return database_url


def _is_auto_db_bootstrap_enabled():
    default_value = 'true' if os.getenv('FLASK_ENV', 'development').lower() == 'development' else 'false'
    return os.getenv('AUTO_DB_BOOTSTRAP', default_value).lower() == 'true'

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'fallback_secret_key_change_in_production')
    SQLALCHEMY_DATABASE_URI = _get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 300,
        'pool_pre_ping': True,
        'pool_timeout': int(os.getenv('DB_POOL_TIMEOUT', '15')),
        'connect_args': {
            'connect_timeout': int(os.getenv('DB_CONNECT_TIMEOUT', '10'))
        }
    }
    AUTO_DB_BOOTSTRAP = _is_auto_db_bootstrap_enabled()

    # Twilio Configuration
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
    TWILIO_TEST_PHONE = os.getenv('TWILIO_TEST_PHONE')
    
    # Google Maps Configuration
    GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
    
    # Flask Configuration
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
