# Capstone 2 Phase 1: Security Foundation Implementation

**Status**: Ready to Deploy  
**Timeline**: Week 1 (Days 1-5)  
**Components**: JWT Auth, PostgreSQL, Encryption, RBAC  
**Hybrid Approach**: Runs alongside existing Phase 4 demo system

---

## 📋 Overview

This document describes the **Capstone 2 Phase 1 implementation**, which adds production-ready security to the Smart City IDS while keeping the existing Phase 4 demo system intact.

### What Gets Added
✅ **PostgreSQL** - Replaces in-memory storage with persistent encrypted database  
✅ **JWT Authentication** - Token-based API access control  
✅ **RBAC** - Role-Based Access Control (Admin, Analyst, Monitor, Service)  
✅ **Data Encryption** - Fernet encryption for sensitive alert/analysis data  
✅ **Audit Logging** - Complete audit trail of all actions  
✅ **API Keys** - Service-to-service authentication  
✅ **User Management** - Create/manage users with different roles  

### What Stays the Same
✅ Phase 4 demo system (attack simulators, dashboards)  
✅ Existing K3s cluster and services  
✅ Suricata, Prometheus, Grafana monitoring  
✅ Falco runtime detection  
✅ Groq LLM integration  

---

## 🎯 Architecture

### New Components Added

```
Current System (Phase 4)              Phase 1 Additions
─────────────────────────          ─────────────────
Falco (runtime IDS)                 PostgreSQL (persistent storage)
Suricata (network IDS)              ├─ Users table (with roles)
IDS API (FastAPI)                   ├─ API keys table
├─ In-memory storage (alert_repo)   ├─ Alerts (encrypted)
├─ Groq LLM integration             ├─ Analysis (encrypted)
└─ K8s automation                   ├─ Audit logs
Prometheus (metrics)                ├─ Automation actions
Grafana (dashboard)                 └─ Encryption keys
                                    
                                    Security Layer (new)
                                    ├─ JWT token generation
                                    ├─ RBAC middleware
                                    ├─ API key validation
                                    └─ Audit logging
```

### API Authentication Flow

```
User/Service
    │
    ├─→ POST /api/auth/login (username + password)
    │        └─→ JWT token returned
    │
    ├─→ POST /api/alerts (with Authorization: Bearer token)
    │        └─→ Token verified
    │        └─→ Role checked (Service role can submit alerts)
    │        └─→ Alert saved to encrypted DB
    │        └─→ Audit logged
    │
    └─→ GET /api/analysis/123 (with token)
            └─→ Decrypted from DB
            └─→ Returned to user (role-based filtering)
```

---

## 🚀 Installation & Setup

### Option 1: Automated Setup (Recommended)

```bash
# Run Phase 1 setup script
bash /home/aka/smart-city-ids/scripts/capstone2-phase1-setup.sh

# This will:
# 1. Generate encryption keys
# 2. Start PostgreSQL (if not running)
# 3. Create database schema
# 4. Run migrations
# 5. Create initial admin user
# 6. Generate .env.security file
```

**Output**:
```
✅ Capstone 2 Phase 1 Setup Complete!

Configuration saved to: /home/aka/smart-city-ids/.env.security

Database Details:
  Host: localhost:5432
  Database: smart_city_ids
  User: ids_user

Initial Admin Credentials:
  Username: admin
  Password: admin_change_me_in_production

⚠️ IMPORTANT: Change the admin password in production!
```

### Option 2: Manual Setup

**Step 1: Start PostgreSQL**
```bash
# Using docker-compose
docker-compose -f infrastructure/docker/postgres-compose.yml up -d

# Or using local PostgreSQL
sudo systemctl start postgresql
```

**Step 2: Create Database & Schema**
```bash
# Create database
createdb -U postgres smart_city_ids

# Run migrations
psql -U postgres -d smart_city_ids -f infrastructure/database/migrations/001_initial_schema.sql
```

**Step 3: Install Dependencies**
```bash
pip install sqlalchemy postgresql python-jose cryptography passlib bcrypt
```

**Step 4: Generate Secrets**
```bash
# Generate encryption key
python3 -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# Generate JWT secret
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"

# Add to .env.security
```

---

## 📁 New Files Created

### Code Files

| File | Purpose | Lines |
|------|---------|-------|
| `src/ids-api/core/security.py` | JWT, RBAC, token management | 250+ |
| `src/ids-api/infrastructure/database.py` | SQLAlchemy models with encryption | 300+ |
| `src/ids-api/infrastructure/db_config.py` | Database config & migrations | 100+ |

### Configuration Files

| File | Purpose |
|------|---------|
| `infrastructure/database/migrations/001_initial_schema.sql` | Database schema |
| `.env.security` | Secrets (generated during setup) |
| `.env.example` | Template for configuration |

### Scripts

| File | Purpose | Status |
|------|---------|--------|
| `scripts/capstone2-phase1-setup.sh` | Automated Phase 1 setup | ✅ Ready |

---

## 🔐 Security Implementation Details

### 1. JWT Authentication

**Token Structure**:
```json
{
  "sub": "analyst_user",
  "role": "analyst",
  "permissions": ["alert:read", "alert:write", "analysis:read"],
  "exp": 1673350400,
  "iat": 1673306400
}
```

**Usage in API**:
```python
@app.post("/api/alerts")
async def process_alert(
    alert: Alert,
    token: TokenData = Depends(verify_token)  # Required!
):
    # Token automatically verified
    # User role checked
    # Audit logged
    ...
```

**Create Token**:
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"analyst","password":"password123"}'

# Response:
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Use Token**:
```bash
curl -X POST http://localhost:8000/api/alerts \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{"output":"Alert","rule":"Rule","priority":"Critical",...}'
```

### 2. Role-Based Access Control (RBAC)

**Roles & Permissions**:

| Role | Permissions | Use Case |
|------|-------------|----------|
| `admin` | All operations | System administrators |
| `analyst` | Read/write alerts & analysis | Security analysts |
| `monitor` | Read-only alerts & analysis | Dashboard monitoring |
| `service` | Write alerts only | Falco, Suricata forwarders |

**Implementation**:
```python
# Require analyst role
@app.post("/api/analysis/execute")
async def execute_analysis(
    token: TokenData = Depends(require_role(Role.ANALYST))
):
    ...

# Require specific permission
@app.delete("/api/users/{user_id}")
async def delete_user(
    token: TokenData = Depends(require_permission("user:delete"))
):
    ...
```

### 3. Data Encryption (Fernet)

**Encrypted Fields** (in database):
- `encrypted_alert_data` - Full alert JSON
- `encrypted_analysis` - LLM analysis result
- `encrypted_result` - Analysis details

**Encryption Process**:
```python
# Store encrypted
alert.encrypt_alert_data({
    "output": "SQL injection detected",
    "priority": "Critical",
    "output_fields": {...}
})
db.add(alert)
db.commit()

# Retrieve decrypted
alert = db.query(AlertRecord).get(alert_id)
original_data = alert.decrypt_alert_data()  # Returns dict
```

**Key Rotation** (future enhancement):
```python
# Example: Rotate encryption key
old_key = Fernet(old_encryption_key)
new_key = Fernet(new_encryption_key)

for alert in db.query(AlertRecord).all():
    data = old_key.decrypt(alert.encrypted_alert_data)
    alert.encrypted_alert_data = new_key.encrypt(data)
    db.commit()
```

### 4. Audit Logging

**Audit Trail** - Every action logged:
```json
{
  "action": "alert:view",
  "resource_type": "alert",
  "resource_id": "alert-12345",
  "user_id": 3,
  "status": "success",
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0...",
  "created_at": "2026-01-10T12:00:00Z"
}
```

**Query Audit Logs**:
```bash
# Who accessed a specific alert?
SELECT * FROM audit_logs 
WHERE resource_type='alert' AND resource_id='alert-12345';

# What did a user do?
SELECT * FROM audit_logs 
WHERE user_id=3 AND created_at > '2026-01-10';

# What failed in the last hour?
SELECT * FROM audit_logs 
WHERE status='failure' AND created_at > NOW() - INTERVAL '1 hour';
```

---

## 📊 Database Schema

### Users Table
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'monitor' NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
```

### Alerts Table (with encryption)
```sql
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(36) UNIQUE NOT NULL,
    source VARCHAR(50),
    rule VARCHAR(512),
    severity INTEGER,
    encrypted_alert_data BYTEA NOT NULL,  -- Encrypted JSON
    encrypted_analysis BYTEA,              -- Encrypted LLM result
    is_analyzed BOOLEAN DEFAULT FALSE,
    actions_taken JSON DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    created_by VARCHAR(255) DEFAULT 'system'
);
```

### Audit Logs Table
```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(255) NOT NULL,
    resource_type VARCHAR(255),
    resource_id VARCHAR(255),
    details JSON,
    status VARCHAR(50),
    ip_address VARCHAR(45),
    user_agent VARCHAR(512),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🔄 Migration Path

### Phase 4 → Phase 1 Hybrid Mode

**Step 1**: Deploy PostgreSQL & run migrations
```bash
bash /home/aka/smart-city-ids/scripts/capstone2-phase1-setup.sh
```

**Step 2**: Keep Phase 4 demo running as-is
```bash
# Phase 4 demo continues to work
bash /home/aka/smart-city-ids/scripts/phase4-run-smart-city-attacks.sh
```

**Step 3**: Update IDS API to use auth middleware
```python
# Update services/ids-api/src/main.py to include:
from src.ids_api.core.security import verify_token, TokenData, Depends

# Add to endpoints:
@app.post("/api/alerts")
async def process_alert(
    alert: Alert,
    token: TokenData = Depends(verify_token)  # NEW: Requires auth
):
    # Now requires valid JWT token
    ...
```

**Step 4**: Create admin users
```bash
# Interactive user creation
python3 << 'EOF'
from src.ids_api.infrastructure.db_config import SessionLocal
from src.ids_api.infrastructure.database import User, UserRole
from src.ids_api.core.security import hash_password

db = SessionLocal()

# Create analyst user
analyst = User(
    username="analyst1",
    email="analyst1@smartcity.ids",
    hashed_password=hash_password("analyst_password"),
    role=UserRole.ANALYST,
    is_active=True,
    is_verified=True
)
db.add(analyst)
db.commit()
print(f"✅ Created analyst user: analyst1")
EOF
```

**Step 5**: Generate API keys for services
```python
# For Suricata forwarder
import secrets
from src.ids_api.infrastructure.database import APIKey

api_key = secrets.token_urlsafe(32)
db_key = APIKey(
    user_id=service_user.id,
    key=hash(api_key),  # Store hash, not actual key
    name="suricata-forwarder",
    description="Forwarder for Suricata Eve JSON alerts"
)
db.add(db_key)
db.commit()

# Return to operator (one-time display)
print(f"API Key (save this): {api_key}")
```

---

## 🧪 Testing Phase 1

### Test 1: User Authentication
```bash
# Create test user
curl -X POST http://localhost:8000/api/users \
  -H "Authorization: Bearer admin_token" \
  -H "Content-Type: application/json" \
  -d '{"username":"test_analyst","email":"test@smartcity.ids","password":"test123","role":"analyst"}'

# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test_analyst","password":"test123"}'

# Verify token works
curl -X GET http://localhost:8000/api/profile \
  -H "Authorization: Bearer <token_from_above>"
```

### Test 2: RBAC Enforcement
```bash
# Monitor user tries to write alert (should fail - insufficient role)
curl -X POST http://localhost:8000/api/alerts \
  -H "Authorization: Bearer monitor_token" \
  -H "Content-Type: application/json" \
  -d '{"output":"test","rule":"test",...}'

# Expected: 403 Forbidden

# Service user writes alert (should succeed)
curl -X POST http://localhost:8000/api/alerts \
  -H "Authorization: Bearer service_token" \
  -H "Content-Type: application/json" \
  -d '{"output":"test","rule":"test",...}'

# Expected: 200 OK
```

### Test 3: Data Encryption
```bash
# Verify encrypted data in database
psql -U ids_user smart_city_ids

-- View encrypted alert
SELECT alert_id, source, encrypted_alert_data FROM alerts LIMIT 1;

-- Alert data appears as bytea (binary), not readable JSON
-- ✅ Encryption working correctly
```

### Test 4: Audit Trail
```bash
# Query audit logs
psql -U ids_user smart_city_ids

SELECT action, user_id, resource_type, status, created_at 
FROM audit_logs 
ORDER BY created_at DESC 
LIMIT 10;

-- Should show all recent actions with user IDs
```

---

## 📋 Deployment Checklist

- [ ] PostgreSQL running and accessible
- [ ] Database schema created (migrations ran successfully)
- [ ] Encryption key generated and stored securely
- [ ] JWT secret key generated and stored securely
- [ ] .env.security file created with proper permissions (600)
- [ ] Initial admin user created
- [ ] IDS API updated with auth middleware
- [ ] Suricata forwarder configured with API key
- [ ] Falco configured with service token
- [ ] Test authentication flow (login → token → API call)
- [ ] Test RBAC (different roles have different access)
- [ ] Verify audit logs recording actions
- [ ] Verify data encryption/decryption works
- [ ] Phase 4 demo still runs alongside new security layer

---

## 🔐 Security Considerations

### Password Security
- ✅ Passwords hashed with bcrypt (not stored in plain text)
- ✅ API keys stored as hashes (original key shown once)
- ⚠️ Change default admin password immediately
- ⚠️ Use strong passwords (12+ characters, mixed case, numbers, symbols)

### Token Security
- ✅ JWT tokens include expiration (default: 1 hour)
- ✅ Tokens signed with secret key (validates haven't been tampered)
- ⚠️ Store tokens securely in client (not in localStorage for SPAs)
- ⚠️ Use HTTPS in production (prevent token interception)

### Database Security
- ✅ Sensitive fields encrypted (alerts, analysis)
- ✅ User passwords hashed with bcrypt
- ✅ Audit trail of all access
- ⚠️ Use strong DB password
- ⚠️ Restrict DB network access
- ⚠️ Regular backups with encryption

### Key Management
- ✅ Encryption key stored in .env.security (not in code)
- ✅ File permissions restricted (600)
- ⚠️ Never commit .env.security to git
- ⚠️ Rotate encryption key periodically
- ⚠️ Use secrets management system (Vault, AWS Secrets) in production

---

## 📈 Next Steps (Phase 2)

Phase 2 (Week 2) will add:
- ✅ Comprehensive input validation
- ✅ Rate limiting
- ✅ Request logging
- ✅ Error handling improvements
- ✅ Retry logic with exponential backoff

---

## 📞 Support & Troubleshooting

### PostgreSQL Connection Error
```
Error: could not connect to server: Connection refused
```

**Solution**:
```bash
# Check if PostgreSQL is running
docker-compose -f infrastructure/docker/postgres-compose.yml ps

# Start it if not running
docker-compose -f infrastructure/docker/postgres-compose.yml up -d

# Or verify credentials in .env.security
echo $DATABASE_URL
```

### Token Verification Failed
```
HTTPException: status_code=401, detail="Could not validate credentials"
```

**Solution**:
```bash
# Verify JWT_SECRET_KEY matches
grep JWT_SECRET_KEY /home/aka/smart-city-ids/.env.security

# Token may be expired - generate new one
curl -X POST http://localhost:8000/api/auth/login ...
```

### Encryption/Decryption Error
```
InvalidToken: The token is invalid because it could not be decrypted
```

**Solution**:
```bash
# Verify ENCRYPTION_KEY hasn't changed
grep ENCRYPTION_KEY /home/aka/smart-city-ids/.env.security

# Don't change ENCRYPTION_KEY after data is encrypted!
# Use key rotation procedure instead
```

---

## 📚 Related Documentation

- [Security Architecture](./SECURITY.md)
- [API Reference](./API.md)
- [Database Migrations](../infrastructure/database/migrations/)
- [Environment Configuration](./.env.example)

---

**Status**: Phase 1 Ready for Deployment  
**Last Updated**: 2026-01-11  
**Capstone 2 Progress**: Phase 1/5 (Week 1/5) ✅
