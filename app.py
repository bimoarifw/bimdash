"""
Bimdash - Professional System Monitoring Dashboard
A comprehensive Flask-based dashboard for real-time system monitoring
"""

import psutil
import os

# Set host paths for psutil before importing utils
if os.environ.get('HOST_PROC'):
    psutil.PROCFS_PATH = os.environ['HOST_PROC']

from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flasgger import Swagger, swag_from
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import base64
import requests
import secrets
from utils.collector import SystemMetricsCollector

# Set host paths for psutil after all imports
if os.environ.get('HOST_PROC'):
    psutil.PROCFS_PATH = os.environ['HOST_PROC']

app = Flask(__name__, instance_relative_config=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///apps.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
db = SQLAlchemy(app)

# Swagger configuration
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec',
            "route": '/api/v1/apispec.json',
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/api/v1/docs"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Bimdash API",
        "description": "System monitoring API with real-time metrics",
        "version": "1.0.0",
        "contact": {
            "name": "API Support"
        }
    },
    "securityDefinitions": {
        "APIKeyHeader": {
            "type": "apiKey",
            "name": "X-API-Key",
            "in": "header",
            "description": "API key for authentication. Get your key from Settings page."
        }
    },
    "security": [
        {
            "APIKeyHeader": []
        }
    ]
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

# Flask-Limiter for better rate limiting
RATELIMIT_STORAGE = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')
DEFAULT_LIMITS = os.environ.get('BIMDASH_DEFAULT_LIMITS', '10000 per hour,1000 per minute')

def _limiter_key():
    """Return a rate-limit key: prefer API key id (if present and valid), else remote IP."""
    try:
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key:
            key_obj = APIKey.query.filter_by(key=api_key, is_active=True).first()
            if key_obj:
                return f"apikey:{key_obj.id}"
            # invalid api key - count under a shared bucket to avoid bypass
            return f"apikey:invalid"
    except Exception:
        pass
    return get_remote_address()


limiter = Limiter(
    app=app,
    key_func=_limiter_key,
    storage_uri=RATELIMIT_STORAGE,
    default_limits=[s.strip() for s in DEFAULT_LIMITS.split(',') if s.strip()],
    headers_enabled=True
)


def _int_from_env(key: str, default: int) -> int:
    try:
        value = int(os.environ.get(key, default))
        return value if value >= 0 else default
    except (TypeError, ValueError):
        return default


def _build_poll_config() -> dict:
    fast_ms = _int_from_env('BIMDASH_FAST_POLL_MS', 1000)
    slow_ms = _int_from_env('BIMDASH_SLOW_POLL_MS', 5000)
    hidden_ms = _int_from_env('BIMDASH_HIDDEN_POLL_MS', 0)
    if slow_ms < fast_ms:
        slow_ms = fast_ms
    return {
        'fast_ms': fast_ms,
        'slow_ms': slow_ms,
        'hidden_ms': hidden_ms
    }


metrics_collector = SystemMetricsCollector()
poll_config = _build_poll_config()

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Ensure instance folder exists
try:
    os.makedirs(app.instance_path)
except OSError:
    pass

class App(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    favicon_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<App {self.name}>'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    full_name = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class APIKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    key = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    user = db.relationship('User', backref=db.backref('api_keys', lazy=True))

    @staticmethod
    def generate_key():
        return secrets.token_urlsafe(32)

    def __repr__(self):
        return f'<APIKey {self.name}>'

# Create database tables
with app.app_context():
    try:
        db.create_all()
        # Initialize default user if not exists
        default_username = os.environ.get('BIMDASH_USERNAME', 'bimdash')
        default_password = os.environ.get('BIMDASH_PASSWORD', 'secret123')

        user = User.query.filter_by(username=default_username).first()
        if not user:
            user = User(username=default_username)
            user.set_password(default_password)
            db.session.add(user)
            db.session.commit()
            print(f"Default user '{default_username}' created successfully")
    except Exception as e:
        # Table might already exist, continue
        pass

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.before_request
def _refresh_metrics_activity():
    if request.path.startswith('/static/'):
        return
    metrics_collector.mark_activity()


def require_api_key(f):
    """Decorator untuk endpoint API eksternal yang butuh API key."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        key_obj = APIKey.query.filter_by(key=api_key, is_active=True).first()
        
        if not key_obj:
            return jsonify({'error': 'Invalid API key'}), 401
        
        # Update last used
        key_obj.last_used = datetime.utcnow()
        db.session.commit()
        
        # Attach to request for rate limiting
        request.api_key_obj = key_obj
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    """Login route"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Please provide both username and password.', 'error')
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logout route"""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    """Main dashboard route"""
    metrics = metrics_collector.metrics()
    processes_info = metrics_collector.processes()
    apps = App.query.all()

    return render_template('index.html',
                         system_info=metrics['system'],
                         cpu_info=metrics['cpu'],
                         memory_info=metrics['memory'],
                         disk_info=metrics['disk'],
                         network_info=metrics['network'],
                         processes_info=processes_info,
                         uptime_info=metrics['uptime'],
                         docker_info=metrics['docker'],
                         apps=apps,
                         poll_config=poll_config)

@app.route('/api/overview')
@login_required
def api_overview():
    """API endpoint for overview metrics (CPU, Memory, Uptime)"""
    metrics = metrics_collector.metrics()
    return jsonify({
        'cpu': metrics['cpu'],
        'memory': metrics['memory'],
        'uptime': metrics['uptime'],
        'timestamp': metrics['timestamp']
    })

@app.route('/api/docker')
@login_required
def api_docker():
    """API endpoint for Docker information"""
    metrics = metrics_collector.metrics()
    return jsonify(metrics['docker'])

@app.route('/api/disk')
@login_required
def api_disk():
    """API endpoint for disk information"""
    metrics = metrics_collector.metrics()
    return jsonify(metrics['disk'])

@app.route('/api/network')
@login_required
def api_network():
    """API endpoint for network information"""
    metrics = metrics_collector.metrics()
    return jsonify(metrics['network'])

@app.route('/api/metrics')
@login_required
def api_metrics():
    """API endpoint for real-time metrics"""
    metrics = metrics_collector.metrics()
    return jsonify(metrics)

@app.route('/api/processes')
@login_required
def api_processes():
    """API endpoint for process information"""
    return jsonify(metrics_collector.processes())

@app.route('/api/apps')
@login_required
def api_apps():
    """API endpoint for apps"""
    apps = App.query.all()
    return jsonify([{
        'id': app.id,
        'name': app.name,
        'url': app.url,
        'favicon_url': app.favicon_url
    } for app in apps])

@app.route('/api/apps', methods=['POST'])
@login_required
def add_app():
    """Add a new app"""
    data = request.get_json()
    name = data.get('name')
    url = data.get('url')

    if not name or not url:
        return jsonify({'error': 'Name and URL are required'}), 400

    # Get favicon URL
    favicon_url = get_favicon_url(url)

    app = App(name=name, url=url, favicon_url=favicon_url)
    db.session.add(app)
    db.session.commit()

    return jsonify({
        'id': app.id,
        'name': app.name,
        'url': app.url,
        'favicon_url': app.favicon_url
    })

@app.route('/api/apps/<int:app_id>', methods=['DELETE'])
@login_required
def delete_app(app_id):
    """Delete an app"""
    app = App.query.get_or_404(app_id)
    db.session.delete(app)
    db.session.commit()
    return jsonify({'success': True})


# ============= Settings Routes =============

@app.route('/settings')
@login_required
def settings():
    """Settings page"""
    api_keys = APIKey.query.filter_by(user_id=current_user.id).all()
    return render_template('settings.html', api_keys=api_keys)

@app.route('/api/settings/profile', methods=['POST'])
@login_required
def update_profile():
    """Update user profile"""
    data = request.get_json()
    
    if 'full_name' in data:
        current_user.full_name = data['full_name']
    
    if 'username' in data:
        # Check if username is taken
        existing = User.query.filter_by(username=data['username']).first()
        if existing and existing.id != current_user.id:
            return jsonify({'error': 'Username already taken'}), 400
        current_user.username = data['username']
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/settings/password', methods=['POST'])
@login_required
def change_password():
    """Change user password"""
    data = request.get_json()
    
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({'error': 'Both current and new password required'}), 400
    
    if not current_user.check_password(current_password):
        return jsonify({'error': 'Current password is incorrect'}), 400
    
    if len(new_password) < 6:
        return jsonify({'error': 'New password must be at least 6 characters'}), 400
    
    current_user.set_password(new_password)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/settings/apikeys', methods=['GET'])
@login_required
def get_api_keys():
    """Get all API keys for current user"""
    keys = APIKey.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': key.id,
        'name': key.name,
        'key': key.key[:8] + '...' + key.key[-4:],
        'created_at': key.created_at.isoformat(),
        'last_used': key.last_used.isoformat() if key.last_used else None,
        'is_active': key.is_active
    } for key in keys])

@app.route('/api/settings/apikeys', methods=['POST'])
@login_required
def create_api_key():
    """Create new API key"""
    data = request.get_json()
    name = data.get('name', 'Unnamed Key')
    
    # Limit to 5 keys per user
    if APIKey.query.filter_by(user_id=current_user.id).count() >= 5:
        return jsonify({'error': 'Maximum 5 API keys allowed'}), 400
    
    api_key = APIKey(
        user_id=current_user.id,
        name=name,
        key=APIKey.generate_key()
    )
    
    db.session.add(api_key)
    db.session.commit()
    
    return jsonify({
        'id': api_key.id,
        'name': api_key.name,
        'key': api_key.key,  # Show full key only on creation
        'created_at': api_key.created_at.isoformat()
    })

@app.route('/api/settings/apikeys/<int:key_id>', methods=['DELETE'])
@login_required
def delete_api_key(key_id):
    """Delete API key"""
    api_key = APIKey.query.filter_by(id=key_id, user_id=current_user.id).first_or_404()
    db.session.delete(api_key)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/settings/apikeys/<int:key_id>/toggle', methods=['POST'])
@login_required
def toggle_api_key(key_id):
    """Toggle API key active status"""
    api_key = APIKey.query.filter_by(id=key_id, user_id=current_user.id).first_or_404()
    api_key.is_active = not api_key.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': api_key.is_active})


# ============= Public API v1 (External Integration) =============

@app.route('/api/v1/system', methods=['GET'])
@require_api_key
@limiter.limit("10 per minute")
def api_v1_system():
    """
    Get system information
    ---
    tags:
      - System
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: System information
        schema:
          type: object
          properties:
            hostname:
              type: string
            os:
              type: string
            architecture:
              type: string
            processor:
              type: string
            cpu_count:
              type: integer
            uptime_seconds:
              type: number
            uptime_formatted:
              type: string
      401:
        description: Invalid or missing API key
    """
    metrics = metrics_collector.metrics()
    return jsonify({
        'hostname': metrics['system']['hostname'],
        'os': metrics['system']['os'],
        'architecture': metrics['system']['architecture'],
        'processor': metrics['system']['processor'],
        'cpu_count': metrics['system']['cpu_count'],
        'uptime_seconds': metrics['uptime']['uptime_seconds'],
        'uptime_formatted': metrics['uptime']['uptime_formatted']
    })

@app.route('/api/v1/stats', methods=['GET'])
@require_api_key
@limiter.limit("10 per minute")
def api_v1_stats():
    """
    Get current system statistics
    ---
    tags:
      - Stats
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: Current system statistics (cached, not real-time)
        schema:
          type: object
          properties:
            timestamp:
              type: string
            cpu:
              type: object
              properties:
                percent:
                  type: number
                cores:
                  type: integer
            memory:
              type: object
            swap:
              type: object
            network:
              type: object
      401:
        description: Invalid or missing API key
      429:
        description: Rate limit exceeded
    """
    metrics = metrics_collector.metrics()
    return jsonify({
        'timestamp': metrics['timestamp'],
        'cpu': {
            'percent': metrics['cpu']['overall_percent'],
            'cores': len(metrics['cpu']['per_core_percent'])
        },
        'memory': {
            'total_gb': metrics['memory']['virtual']['total_gb'],
            'used_gb': metrics['memory']['virtual']['used_gb'],
            'percent': metrics['memory']['virtual']['percent']
        },
        'swap': {
            'total_gb': metrics['memory']['swap']['total_gb'],
            'used_gb': metrics['memory']['swap']['used_gb'],
            'percent': metrics['memory']['swap']['percent']
        },
        'network': {
            'bytes_sent': metrics['network']['bytes_sent'],
            'bytes_recv': metrics['network']['bytes_recv']
        }
    })

@app.route('/api/v1/docker', methods=['GET'])
@require_api_key
@limiter.limit("10 per minute")
def api_v1_docker():
    """
    Get Docker containers information
    ---
    tags:
      - Docker
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: Docker containers list
        schema:
          type: object
          properties:
            containers:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
                  status:
                    type: string
                  image:
                    type: string
                  cpu_percent:
                    type: number
                  memory_percent:
                    type: number
            total:
              type: integer
      401:
        description: Invalid or missing API key
      429:
        description: Rate limit exceeded
    """
    metrics = metrics_collector.metrics()
    containers = []
    
    for container in metrics.get('docker', []):
        if 'error' in container:
            continue
        containers.append({
            'id': container.get('id'),
            'name': container.get('name'),
            'status': container.get('status'),
            'image': container.get('image'),
            'cpu_percent': container.get('cpu_percent', 0),
            'memory_percent': container.get('mem_percent', 0)
        })
    
    return jsonify({'containers': containers, 'total': len(containers)})


def get_favicon_url(url):
    """Extract favicon URL from a website"""
    try:
        # Remove protocol if present
        domain = url.replace('https://', '').replace('http://', '').split('/')[0]

        # Try common favicon locations
        favicon_urls = [
            f'https://{domain}/favicon.ico',
            f'https://{domain}/favicon.png',
            f'https://{domain}/favicon.svg',
            f'https://www.google.com/s2/favicons?domain={domain}&sz=32'
        ]

        # For local/private IPs, use default SVG
        if domain.startswith('192.168.') or domain.startswith('10.') or domain.startswith('172.') or domain == 'localhost':
            return get_default_app_icon()

        # Try to fetch favicon
        for favicon_url in favicon_urls[:-1]:  # Exclude Google for now
            try:
                response = requests.get(favicon_url, timeout=2)
                if response.status_code == 200:
                    return favicon_url
            except:
                continue

        # Fallback to Google or default
        return favicon_urls[-1]
    except:
        return get_default_app_icon()

def get_default_app_icon():
    """Return a default SVG icon as data URL"""
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-8 h-8 text-gray-400">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
        <line x1="8" y1="21" x2="16" y2="21"></line>
        <line x1="12" y1="17" x2="12" y2="21"></line>
    </svg>'''
    # Encode as data URL
    encoded = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
    return f'data:image/svg+xml;base64,{encoded}'

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8535, debug=True)