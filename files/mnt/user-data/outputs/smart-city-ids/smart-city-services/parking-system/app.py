#!/usr/bin/env python3
"""
Parking System Service - Smart City IDS
Manages parking lots and payments (intentionally vulnerable)
"""

from flask import Flask, jsonify, request
import logging
from datetime import datetime

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simulated parking lots
PARKING_LOTS = {
    "LOT-A": {"location": "Downtown", "capacity": 500, "available": 234},
    "LOT-B": {"location": "Airport", "capacity": 1000, "available": 567},
    "LOT-C": {"location": "Mall", "capacity": 300, "available": 45},
}

PAYMENTS = []


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "parking-system",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/lots', methods=['GET'])
def get_lots():
    """Get available parking lots"""
    logger.info("GET /api/lots")
    return jsonify({
        "lots": PARKING_LOTS,
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/lot/<lot_id>/reserve', methods=['POST'])
def reserve_spot(lot_id):
    """Reserve a parking spot"""
    if lot_id not in PARKING_LOTS:
        return jsonify({"error": "Lot not found"}), 404
    
    lot = PARKING_LOTS[lot_id]
    if lot['available'] <= 0:
        return jsonify({"error": "No spaces available"}), 400
    
    data = request.get_json()
    lot['available'] -= 1
    
    logger.info(f"Reserved spot in {lot_id}: {data.get('license_plate')}")
    
    return jsonify({
        "reservation_id": f"RSV-{datetime.now().timestamp()}",
        "lot_id": lot_id,
        "duration": data.get("duration", 1),
        "price": data.get("duration", 1) * 5
    }), 201


@app.route('/api/payment', methods=['POST'])
def process_payment():
    """Process payment - VULNERABLE: Logs sensitive credit card data!"""
    data = request.get_json()
    
    # SECURITY VIOLATION: Logging credit card data in plain text!
    logger.critical(f"PAYMENT RECEIVED: {data}")
    logger.critical(f"  Card: {data.get('card_number')}")
    logger.critical(f"  CVV: {data.get('cvv')}")
    logger.critical(f"  Amount: ${data.get('amount')}")
    
    PAYMENTS.append({
        "timestamp": datetime.now().isoformat(),
        "amount": data.get('amount'),
        "card_last4": data.get('card_number', '')[-4:],
        "status": "processed"
    })
    
    return jsonify({
        "transaction_id": f"TXN-{len(PAYMENTS)}",
        "status": "success"
    }), 200


@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get all transactions - VULNERABLE: No auth, exposes payment data"""
    logger.warning("GET /api/transactions - UNAUTHORIZED ACCESS TO PAYMENT DATA!")
    return jsonify({
        "transactions": PAYMENTS,
        "total": len(PAYMENTS)
    }), 200


@app.route('/admin/system-status', methods=['GET'])
def system_status():
    """Admin endpoint - VULNERABLE: No authentication"""
    logger.warning("GET /admin/system-status - UNAUTHORIZED ACCESS!")
    
    total_revenue = sum(p.get('amount', 0) for p in PAYMENTS)
    
    return jsonify({
        "total_revenue": total_revenue,
        "transactions": len(PAYMENTS),
        "lots_status": PARKING_LOTS,
        "system_info": "Running on Python 3.9, no security patches"
    }), 200


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5002))
    logger.info(f"Starting Parking System on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
