#!/usr/bin/env python3
"""
Smart City IDS - Main Application
AI-powered Intrusion Detection System with Groq LLM
"""

from flask import Flask, jsonify, request
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MOCK_MODE = os.getenv('MOCK_MODE', 'true').lower() == 'true'
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

# Alert storage
alerts = []
threat_analyses = []


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "smart-city-ids",
        "mode": "mock" if MOCK_MODE else "production",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get all collected alerts"""
    return jsonify({
        "alerts": alerts,
        "total": len(alerts)
    }), 200


@app.route('/api/alerts', methods=['POST'])
def create_alert():
    """Create a new security alert"""
    data = request.get_json()
    
    alert = {
        "id": len(alerts) + 1,
        "timestamp": datetime.now().isoformat(),
        "source": data.get('source', 'unknown'),
        "severity": data.get('severity', 'medium'),
        "message": data.get('message', ''),
        "service": data.get('service', ''),
        "status": "new"
    }
    
    alerts.append(alert)
    logger.info(f"New alert created: {alert['id']} - {alert['message']}")
    
    return jsonify(alert), 201


@app.route('/api/analyze/<int:alert_id>', methods=['POST'])
def analyze_alert(alert_id):
    """Analyze a security alert with LLM"""
    if alert_id > len(alerts):
        return jsonify({"error": "Alert not found"}), 404
    
    alert = alerts[alert_id - 1]
    
    if MOCK_MODE:
        # Mock analysis for demo
        analysis = {
            "alert_id": alert_id,
            "severity": alert['severity'],
            "threat_type": "Potential " + alert['severity'].upper() + " threat",
            "description": f"Analysis of {alert['message']}",
            "recommended_actions": [
                "Isolate affected service",
                "Review access logs",
                "Increase monitoring"
            ],
            "confidence": 0.95
        }
    else:
        # Real Groq LLM analysis
        try:
            from groq import Groq
            
            client = Groq(api_key=GROQ_API_KEY)
            
            prompt = f"""
You are a cybersecurity expert analyzing a security alert from a Smart City IDS system.

Alert Details:
- Source: {alert['source']}
- Service: {alert['service']}
- Severity: {alert['severity']}
- Message: {alert['message']}

Please provide:
1. Threat classification
2. Potential impact
3. Recommended immediate actions
4. Long-term mitigation strategies

Be concise and actionable.
"""
            
            message = client.messages.create(
                model="mixtral-8x7b-32768",
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            analysis = {
                "alert_id": alert_id,
                "severity": alert['severity'],
                "llm_analysis": message.content[0].text,
                "model": "mixtral-8x7b-32768"
            }
        
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            analysis = {
                "alert_id": alert_id,
                "error": str(e),
                "fallback": "LLM analysis unavailable"
            }
    
    alert['status'] = 'analyzed'
    threat_analyses.append(analysis)
    
    logger.info(f"Alert {alert_id} analyzed")
    return jsonify(analysis), 200


@app.route('/api/analyses', methods=['GET'])
def get_analyses():
    """Get all threat analyses"""
    return jsonify({
        "analyses": threat_analyses,
        "total": len(threat_analyses)
    }), 200


@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    """Dashboard with security summary"""
    high_severity = sum(1 for a in alerts if a['severity'] == 'high')
    medium_severity = sum(1 for a in alerts if a['severity'] == 'medium')
    low_severity = sum(1 for a in alerts if a['severity'] == 'low')
    
    return jsonify({
        "total_alerts": len(alerts),
        "alert_breakdown": {
            "high": high_severity,
            "medium": medium_severity,
            "low": low_severity
        },
        "analyzed": sum(1 for a in alerts if a['status'] == 'analyzed'),
        "pending": sum(1 for a in alerts if a['status'] == 'new'),
        "threat_analyses": len(threat_analyses),
        "mode": "mock" if MOCK_MODE else "production"
    }), 200


@app.route('/api/simulate-alert', methods=['POST'])
def simulate_alert():
    """Simulate a security alert for testing"""
    if not MOCK_MODE:
        return jsonify({"error": "Simulation only available in mock mode"}), 400
    
    # Create a simulated alert
    alert = {
        "id": len(alerts) + 1,
        "timestamp": datetime.now().isoformat(),
        "source": "Falco",
        "severity": "high",
        "message": "Suspicious process execution detected in traffic-camera pod",
        "service": "traffic-camera",
        "status": "new"
    }
    
    alerts.append(alert)
    
    # Auto-analyze it
    analysis = {
        "alert_id": alert['id'],
        "severity": alert['severity'],
        "threat_type": "Privilege Escalation Attempt",
        "description": "Detected execution of unauthorized system tool attempting to access privileged resources",
        "recommended_actions": [
            "Immediately isolate the affected pod",
            "Review process execution logs",
            "Check for unauthorized user accounts",
            "Validate system integrity"
        ],
        "confidence": 0.98,
        "automatic": True
    }
    
    alert['status'] = 'analyzed'
    threat_analyses.append(analysis)
    
    return jsonify({
        "alert": alert,
        "analysis": analysis
    }), 201


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get system configuration"""
    return jsonify({
        "mock_mode": MOCK_MODE,
        "groq_configured": bool(GROQ_API_KEY),
        "alerts_stored": len(alerts),
        "analyses_performed": len(threat_analyses)
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('IDS_PORT', 5003))
    logger.info(f"Starting Smart City IDS on port {port}")
    logger.info(f"Mock mode: {MOCK_MODE}")
    app.run(host='0.0.0.0', port=port, debug=True)
