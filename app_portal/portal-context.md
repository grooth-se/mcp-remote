# Subseatec Application Portal - Development Context

## Project Overview

**Application name:** Subseatec App Portal  
**Purpose:** Central authentication gateway and app launcher for all Subseatec internal applications  
**Server:** 172.27.55.104 (HPE ProLiant ML110 Gen11, 64GB RAM, Ubuntu Server with GUI)  
**Users:** 12 employees with individual app permissions

## Architecture

```
                         Internet/LAN
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Ubuntu Server 172.27.55.104                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    Nginx Reverse Proxy                      │  │
│  │                    (Port 80/443)                            │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                              │                                    │
│  ┌──────────────────────────┴─────────────────────────────────┐  │
│  │                    App Portal (Port 5000)                   │  │
│  │  - Login / Authentication                                   │  │
│  │  - User Management (Admin)                                  │  │
│  │  - App Launcher                                             │  │
│  │  - Session & Token Management                               │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                              │                                    │
│         ┌────────────────────┼────────────────────┐              │
│         ▼                    ▼                    ▼              │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │Accrued Inc. │  │    HeatSim      │  │ MPQP Generator  │      │
│  │  (5001)     │  │    (5002)       │  │    (5003)       │      │
│  └─────────────┘  └─────────────────┘  └─────────────────┘      │
│         ▼                    ▼                    ▼              │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │MG5 Integr.  │  │   Durabler2     │  │  SPInventory    │      │
│  │  (5004)     │  │    (5005)       │  │    (5006)       │      │
│  └─────────────┘  └─────────────────┘  └─────────────────┘      │
│         ▼                                                        │
│  ┌─────────────┐                                                 │
│  │HeatTreat    │                                                 │
│  │Tracker(5007)│                                                 │
│  └─────────────┘                                                 │
└──────────────────────────────────────────────────────────────────┘
```

## Security Model

### Authentication Flow

```
1. User navigates to https://172.27.55.104 (or domain)
                    │
                    ▼
2. Portal shows login page
   User enters username + password
                    │
                    ▼
3. Portal validates credentials
   Creates session + JWT token
                    │
                    ▼
4. Portal shows app launcher
   (Only apps user has permission to see)
                    │
                    ▼
5. User clicks app → Opens in new tab
   URL includes token: /app/heatsim?token=xxx
                    │
                    ▼
6. Nginx routes to app
   App validates token with Portal API
                    │
                    ▼
7. App grants access if token valid + user has permission
```

### Access Control

- **Direct app access blocked** - Nginx only allows app access with valid portal token
- **Admin exception** - Admin users can access apps directly for debugging
- **Token expiration** - Tokens expire after configurable time (default: 8 hours)
- **Per-user permissions** - Each user assigned specific apps they can access

## Technology Stack

- **Portal Backend:** Python Flask
- **Database:** SQLite (users, permissions, sessions)
- **Authentication:** JWT tokens + session management
- **Reverse Proxy:** Nginx
- **Frontend:** HTML/CSS/JavaScript (Bootstrap for styling)
- **Deployment:** Docker + Docker Compose
- **SSL:** Self-signed certificate (internal use)

## Features

### User Features

**Login Page:**
- Username and password authentication
- "Remember me" option (extends session)
- Clear error messages

**App Launcher Dashboard:**
- Grid/list of permitted applications
- App icons and descriptions
- Click to open app in new tab
- Visual indication if app is online/offline

**User Profile:**
- Change own password
- View session info
- Logout

### Admin Features

**User Management:**
- Create new users
- Edit user details
- Reset user passwords
- Deactivate/reactivate users
- Delete users

**Permission Management:**
- View all apps
- Assign/remove app access per user
- Bulk permission updates

**App Management:**
- Register new applications
- Edit app details (name, description, URL, icon)
- Enable/disable apps
- View app health status

**Admin Management:**
- Grant admin rights to users
- Revoke admin rights
- View admin activity log

**System:**
- View active sessions
- Force logout users
- View access logs

## Database Schema

```sql
-- Users
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    email TEXT,
    is_admin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    last_login TIMESTAMP,
    password_changed_at TIMESTAMP
);

-- Applications
CREATE TABLE applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_code TEXT UNIQUE NOT NULL,        -- e.g., 'accruedincome', 'heatsim'
    app_name TEXT NOT NULL,               -- Display name
    description TEXT,
    internal_url TEXT NOT NULL,           -- e.g., 'http://localhost:5001'
    icon TEXT,                            -- Icon filename or class
    display_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    requires_gpu BOOLEAN DEFAULT FALSE,   -- Info flag
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User-App Permissions
CREATE TABLE user_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    app_id INTEGER REFERENCES applications(id) ON DELETE CASCADE,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    granted_by INTEGER REFERENCES users(id),
    UNIQUE(user_id, app_id)
);

-- Sessions
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- Access Log
CREATE TABLE access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    app_id INTEGER REFERENCES applications(id),
    action TEXT,                          -- 'login', 'logout', 'access_app', 'denied'
    ip_address TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT
);

-- Audit Log (admin actions)
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    target_type TEXT,                     -- 'user', 'app', 'permission'
    target_id INTEGER,
    old_value TEXT,
    new_value TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Initial Applications

| App Code | App Name | Port | Description |
|----------|----------|------|-------------|
| accruedincome | Accrued Income | 5001 | Project accrued income calculations |
| heatsim | HeatSim | 5002 | Materials simulation platform |
| mpqpgenerator | MPQP Generator | 5003 | Manufacturing document generator |
| mg5integration | MG5 Integrator | 5004 | Monitor G5 data integration |
| durabler2 | Durabler2 | 5005 | (Description TBD) |
| spinventory | SPInventory | 5006 | (Description TBD) |
| heattreattracker | Heat Treatment Tracker | 5007 | Heat treatment tracking |

## Application Structure

```
subseatec-portal/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── application.py
│   │   ├── permission.py
│   │   └── session.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py              # Login, logout, password change
│   │   ├── dashboard.py         # App launcher
│   │   ├── admin/
│   │   │   ├── __init__.py
│   │   │   ├── users.py         # User management
│   │   │   ├── apps.py          # App management
│   │   │   └── permissions.py   # Permission management
│   │   └── api/
│   │       ├── __init__.py
│   │       └── token_validation.py  # API for apps to validate tokens
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py      # Authentication logic
│   │   ├── token_service.py     # JWT handling
│   │   └── app_health.py        # Check if apps are running
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── password.py          # Password hashing
│   │   └── decorators.py        # @login_required, @admin_required
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   └── change_password.html
│   │   ├── dashboard/
│   │   │   └── index.html       # App launcher
│   │   └── admin/
│   │       ├── users.html
│   │       ├── apps.html
│   │       └── permissions.html
│   └── static/
│       ├── css/
│       ├── js/
│       └── icons/               # App icons
├── nginx/
│   ├── nginx.conf
│   └── ssl/
│       ├── server.crt           # Self-signed cert
│       └── server.key
├── scripts/
│   ├── init_db.py               # Initialize database
│   ├── create_admin.py          # Create first admin user
│   └── generate_ssl.sh          # Generate self-signed certificate
├── tests/
├── data/
│   └── portal.db                # SQLite database
├── requirements.txt
├── Dockerfile
├── docker-compose.yml           # Portal + Nginx + all apps
└── README.md
```

## Token Validation API

Apps call this endpoint to validate user access:

**Endpoint:** `POST /api/validate-token`

**Request:**
```json
{
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "app_code": "heatsim"
}
```

**Response (success):**
```json
{
    "valid": true,
    "user": {
        "id": 1,
        "username": "john.doe",
        "display_name": "John Doe",
        "is_admin": false
    },
    "permissions": ["heatsim", "accruedincome"]
}
```

**Response (failure):**
```json
{
    "valid": false,
    "error": "Token expired"
}
```

## App Integration Guide

Each app must implement token validation. Here's the integration code:

```python
# For each Flask app - add to utils/portal_auth.py

import requests
from functools import wraps
from flask import request, redirect, session, current_app

PORTAL_URL = "http://localhost:5000"  # Or from config

def validate_portal_token(token, app_code):
    """Validate token with portal."""
    try:
        response = requests.post(
            f"{PORTAL_URL}/api/validate-token",
            json={"token": token, "app_code": app_code},
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        current_app.logger.error(f"Portal validation error: {e}")
    return {"valid": False}

def portal_login_required(app_code):
    """Decorator to require portal authentication."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check for token in query param (initial access from portal)
            token = request.args.get('token')
            
            if token:
                # Validate with portal
                result = validate_portal_token(token, app_code)
                if result.get('valid'):
                    # Store in session
                    session['portal_user'] = result['user']
                    session['portal_token'] = token
                    # Redirect to remove token from URL
                    return redirect(request.path)
                else:
                    return redirect(f"{PORTAL_URL}/login?error=invalid_token")
            
            # Check existing session
            if 'portal_user' not in session:
                return redirect(f"{PORTAL_URL}/login?next={request.url}")
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Usage in app routes:
# @app.route('/')
# @portal_login_required('heatsim')
# def index():
#     user = session['portal_user']
#     return render_template('index.html', user=user)
```

## Nginx Configuration

```nginx
# nginx/nginx.conf

upstream portal {
    server portal:5000;
}

upstream accruedincome {
    server accruedincome:5001;
}

upstream heatsim {
    server heatsim:5002;
}

upstream mpqpgenerator {
    server mpqpgenerator:5003;
}

upstream mg5integration {
    server mg5integration:5004;
}

upstream durabler2 {
    server durabler2:5005;
}

upstream spinventory {
    server spinventory:5006;
}

upstream heattreattracker {
    server heattreattracker:5007;
}

server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/nginx/ssl/server.crt;
    ssl_certificate_key /etc/nginx/ssl/server.key;

    # Portal (default)
    location / {
        proxy_pass http://portal;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Apps - require token parameter or valid session
    location /app/accruedincome/ {
        # Token validation happens in the app
        proxy_pass http://accruedincome/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /app/heatsim/ {
        proxy_pass http://heatsim/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /app/mpqpgenerator/ {
        proxy_pass http://mpqpgenerator/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /app/mg5integration/ {
        proxy_pass http://mg5integration/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /app/durabler2/ {
        proxy_pass http://durabler2/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /app/spinventory/ {
        proxy_pass http://spinventory/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /app/heattreattracker/ {
        proxy_pass http://heattreattracker/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - portal
    restart: unless-stopped

  portal:
    build: .
    environment:
      - SECRET_KEY=${PORTAL_SECRET_KEY}
      - DATABASE_PATH=/data/portal.db
    volumes:
      - portal_data:/data
    restart: unless-stopped

  # Apps will be added here as they are developed
  # Each app has its own Dockerfile in its folder
  
  # Example:
  # accruedincome:
  #   build: ../accruedincome
  #   environment:
  #     - PORTAL_URL=http://portal:5000
  #   volumes:
  #     - accruedincome_data:/data
  #   restart: unless-stopped

volumes:
  portal_data:
```

## Development Phases

### Phase 1: Core Portal
- [ ] Project setup and structure
- [ ] Database schema and models
- [ ] User authentication (login/logout)
- [ ] Password hashing (Werkzeug)
- [ ] Session management
- [ ] Basic login page UI

### Phase 2: App Launcher
- [ ] Dashboard with app grid
- [ ] App cards with icons
- [ ] Token generation for app access
- [ ] Open app in new tab
- [ ] App health check (online/offline status)

### Phase 3: Admin - User Management
- [ ] User list view
- [ ] Create user
- [ ] Edit user
- [ ] Reset password
- [ ] Activate/deactivate user
- [ ] Delete user

### Phase 4: Admin - App & Permission Management
- [ ] App list and registration
- [ ] Edit app details
- [ ] Permission matrix (user × app)
- [ ] Assign/revoke permissions
- [ ] Admin role management

### Phase 5: Token Validation API
- [ ] `/api/validate-token` endpoint
- [ ] Token expiration handling
- [ ] Create integration code template for apps
- [ ] Documentation for app developers

### Phase 6: Nginx & Security
- [ ] Nginx configuration
- [ ] SSL certificate generation
- [ ] Route protection
- [ ] Admin bypass for direct access

### Phase 7: Logging & Monitoring
- [ ] Access logging
- [ ] Admin audit log
- [ ] Session monitoring
- [ ] Force logout capability

### Phase 8: Docker & Deployment
- [ ] Portal Dockerfile
- [ ] Docker Compose for all services
- [ ] Init scripts (create admin, generate SSL)
- [ ] Deployment documentation

## Configuration

```python
# app/config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-in-production')
    DATABASE_PATH = os.environ.get('DATABASE_PATH', 'data/portal.db')
    
    # Session
    SESSION_LIFETIME_HOURS = int(os.environ.get('SESSION_LIFETIME', 8))
    REMEMBER_ME_DAYS = int(os.environ.get('REMEMBER_ME_DAYS', 7))
    
    # Token
    TOKEN_EXPIRY_HOURS = int(os.environ.get('TOKEN_EXPIRY', 8))
    
    # Password
    MIN_PASSWORD_LENGTH = 8
    
    # Portal
    PORTAL_NAME = "Subseatec Applications"
    
    # Apps health check
    HEALTH_CHECK_TIMEOUT = 3  # seconds
```

## Initial Setup Commands

```bash
# On server 172.27.55.104

# 1. Create project directory
mkdir -p /opt/subseatec
cd /opt/subseatec

# 2. Clone/copy portal code
git clone <repository> portal
# Or copy files

# 3. Generate SSL certificate
cd portal
./scripts/generate_ssl.sh

# 4. Create .env file
cat > .env << EOF
PORTAL_SECRET_KEY=$(openssl rand -hex 32)
EOF

# 5. Build and start
docker-compose build
docker-compose up -d

# 6. Create first admin user
docker-compose exec portal python scripts/create_admin.py

# 7. Access portal
# https://172.27.55.104
```

## Notes

### Adding New Apps

1. Create app with Flask + portal integration code
2. Add to Docker Compose
3. Add Nginx location block
4. Register app in portal admin
5. Assign permissions to users

### Security Considerations

- All passwords hashed with Werkzeug (bcrypt)
- JWT tokens signed with server secret
- HTTPS enforced via Nginx redirect
- Session tokens rotated on password change
- Failed login attempts logged

### Backup

- SQLite database file: `/data/portal.db`
- Include in regular backup routine
- Can export users/permissions as JSON for disaster recovery

## Server Details

- **IP:** 172.27.55.104
- **Hardware:** HPE ProLiant ML110 Gen11
- **RAM:** 64GB
- **OS:** Ubuntu Server (with GUI)
- **SSH User:** administrator
- **Services:** Python, Docker installed
- **Ports:** 80 (HTTP), 443 (HTTPS), 22 (SSH)
