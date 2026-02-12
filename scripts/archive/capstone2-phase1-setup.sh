#!/bin/bash

# Capstone 2 Phase 1: Security Foundation Setup
# This script sets up PostgreSQL and initializes the security infrastructure

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║   Capstone 2 Phase 1: Security Foundation Setup                ║"
echo "║   - PostgreSQL database with encryption                        ║"
echo "║   - User authentication (JWT + API keys)                       ║"
echo "║   - RBAC and audit logging                                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Configuration
DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-smart_city_ids}
DB_USER=${DB_USER:-ids_user}
DB_PASSWORD=${DB_PASSWORD:-ids_password}
ENCRYPTION_KEY=${ENCRYPTION_KEY:-}
JWT_SECRET_KEY=${JWT_SECRET_KEY:-}

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_success() { echo -e "${GREEN}[✅]${NC} $1"; }
log_error() { echo -e "${RED}[❌]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[⚠️]${NC} $1"; }

# Step 1: Generate encryption keys if not provided
log_step "Generating encryption keys..."
if [ -z "$ENCRYPTION_KEY" ]; then
    log_warning "ENCRYPTION_KEY not provided, generating new key"
    ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    log_success "Generated ENCRYPTION_KEY: ${ENCRYPTION_KEY:0:20}..."
fi

if [ -z "$JWT_SECRET_KEY" ]; then
    log_warning "JWT_SECRET_KEY not provided, generating new key"
    JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    log_success "Generated JWT_SECRET_KEY: ${JWT_SECRET_KEY:0:20}..."
fi

# Step 2: Check PostgreSQL
log_step "Checking PostgreSQL connectivity..."
if ! command -v psql &> /dev/null; then
    log_error "psql not found. Install PostgreSQL client: apt install postgresql-client"
    exit 1
fi

if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d postgres -c "SELECT 1" &>/dev/null; then
    log_success "PostgreSQL is accessible"
else
    log_warning "PostgreSQL not accessible. Attempting docker-compose setup..."
    
    # Create docker-compose.yml for PostgreSQL
    cat > /tmp/postgres-compose.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: smart_city_ids
      POSTGRES_USER: ids_user
      POSTGRES_PASSWORD: ids_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ids_user"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
EOF
    
    log_step "Starting PostgreSQL with docker-compose..."
    docker-compose -f /tmp/postgres-compose.yml up -d
    sleep 5
    log_success "PostgreSQL started"
fi

# Step 3: Create database
log_step "Creating database..."
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;" 2>/dev/null || log_warning "Database already exists"
log_success "Database ready: $DB_NAME"

# Step 4: Run migrations
log_step "Running database migrations..."
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -f /home/kali/smart-city-ids/infrastructure/database/migrations/001_initial_schema.sql
log_success "Database schema created"

# Step 5: Install Python dependencies
log_step "Installing Python dependencies..."
pip install -q sqlalchemy postgresql python-jose cryptography passlib bcrypt -q
log_success "Dependencies installed"

# Step 6: Create .env file with secrets
log_step "Creating .env file with secrets..."
cat > /home/kali/smart-city-ids/.env.security << EOF
# Capstone 2 Phase 1 - Security Configuration
# Generated: $(date)

# Database
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
SQL_ECHO=false

# Encryption
ENCRYPTION_KEY=${ENCRYPTION_KEY}

# JWT
JWT_SECRET_KEY=${JWT_SECRET_KEY}
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Security
ENVIRONMENT=development
DEBUG=false
LOG_LEVEL=INFO
EOF

chmod 600 /home/kali/smart-city-ids/.env.security
log_success "Created .env.security (permissions: 600)"

# Step 7: Create initial admin user
log_step "Creating initial admin user..."
python3 << PYEOF
import sys
sys.path.insert(0, '/home/kali/smart-city-ids')
from src.ids_api.core.security import hash_password
from src.ids_api.infrastructure.db_config import SessionLocal, init_db
from src.ids_api.infrastructure.database import User, UserRole

# Initialize DB
init_db()

# Create admin user
db = SessionLocal()
admin_user = User(
    username="admin",
    email="admin@smartcity.ids",
    hashed_password=hash_password("admin_change_me_in_production"),
    role=UserRole.ADMIN,
    is_active=True,
    is_verified=True
)

try:
    db.add(admin_user)
    db.commit()
    print("✅ Admin user created: admin/admin_change_me_in_production")
except Exception as e:
    print(f"⚠️ Admin user may already exist: {e}")
finally:
    db.close()
PYEOF

log_success "Admin user created"

# Step 8: Display summary
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
log_success "Capstone 2 Phase 1 Setup Complete!"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Configuration saved to: /home/kali/smart-city-ids/.env.security"
echo ""
echo "Database Details:"
echo "  Host: $DB_HOST:$DB_PORT"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo ""
echo "Initial Admin Credentials:"
echo "  Username: admin"
echo "  Password: admin_change_me_in_production"
echo ""
echo "⚠️  IMPORTANT: Change the admin password in production!"
echo ""
echo "Next Steps:"
echo "  1. Review .env.security file"
echo "  2. Update admin password: UPDATE users SET hashed_password=... WHERE username='admin'"
echo "  3. Create additional users for analyst/monitor roles"
echo "  4. Generate API keys for service-to-service auth"
echo "  5. Deploy updated IDS API with auth middleware"
echo ""
echo "Documentation:"
echo "  See: /home/kali/smart-city-ids/docs/SECURITY.md"
echo ""
