from flask import Flask, jsonify, request
import time
import random
import os

app = Flask(__name__)

# Simulated parking lots
parking_lots = {
    "LOT_A": {"capacity": 100, "occupied": 45, "location": "City Center"},
    "LOT_B": {"capacity": 200, "occupied": 180, "location": "Mall District"},
    "LOT_C": {"capacity": 150, "occupied": 90, "location": "Airport"}
}

request_count = 0

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "parking-system"}), 200

@app.route('/api/lots', methods=['GET'])
def get_lots():
    global request_count
    request_count += 1
    
    # Add some randomness to simulate real-time changes
    for lot in parking_lots.values():
        lot["occupied"] = min(lot["capacity"], lot["occupied"] + random.randint(-2, 3))
    
    return jsonify({
        "parking_lots": parking_lots,
        "timestamp": time.time()
    }), 200

@app.route('/api/lot/<lot_id>/reserve', methods=['POST'])
def reserve_spot(lot_id):
    global request_count
    request_count += 1
    
    if lot_id not in parking_lots:
        return jsonify({"error": "Parking lot not found"}), 404
    
    lot = parking_lots[lot_id]
    if lot["occupied"] >= lot["capacity"]:
        return jsonify({"error": "Parking lot full"}), 400
    
    lot["occupied"] += 1
    return jsonify({
        "message": "Spot reserved",
        "lot_id": lot_id,
        "spots_remaining": lot["capacity"] - lot["occupied"]
    }), 200

@app.route('/api/payment', methods=['POST'])
def process_payment():
    """Payment endpoint (vulnerable to data exfiltration)"""
    global request_count
    request_count += 1
    
    payment_data = request.json
    # VULNERABILITY: Logs sensitive payment info
    print(f"Payment received: {payment_data}")
    
    return jsonify({
        "status": "success",
        "transaction_id": f"TXN_{random.randint(1000, 9999)}",
        "warning": "PAYMENT_DATA_LOGGED"
    }), 200

@app.route('/api/stats', methods=['GET'])
def get_stats():
    total_capacity = sum(lot["capacity"] for lot in parking_lots.values())
    total_occupied = sum(lot["occupied"] for lot in parking_lots.values())
    
    return jsonify({
        "requests_total": request_count,
        "total_capacity": total_capacity,
        "total_occupied": total_occupied,
        "occupancy_rate": round((total_occupied / total_capacity) * 100, 2)
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=False)
