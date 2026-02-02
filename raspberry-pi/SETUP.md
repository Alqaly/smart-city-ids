# Raspberry Pi 5 Setup for Smart City IDS

## Hardware Required

- Raspberry Pi 5
- PIR Motion Sensor (HC-SR501 or similar)
- 3 jumper wires (female-to-female)

## Network Architecture

The Pi connects to the IDS API through a Windows port proxy (for NAT-based VM setup):

```
┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│   Raspberry Pi      │      │   Windows Host      │      │   Ubuntu VM (NAT)   │
│   (WiFi Hotspot)    │ ───► │   Port 30800        │ ───► │   192.168.153.129   │
│                     │      │   (Port Proxy)      │      │   K3s + IDS API     │
└─────────────────────┘      └─────────────────────┘      └─────────────────────┘
```

### Windows Port Proxy Setup (One-Time)

Run in **PowerShell as Administrator**:
```powershell
# Add port proxy rule (persists across reboots)
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=30800 connectaddress=192.168.153.129 connectport=30800

# Add firewall rule
netsh advfirewall firewall add rule name="IDS API Forward 30800" dir=in action=allow protocol=TCP localport=30800

# Verify
netsh interface portproxy show all
```

### Finding Windows IP (When Changing WiFi)

On Windows:
```powershell
ipconfig
# Look for Wi-Fi adapter IPv4 address (e.g., 172.20.10.3)
```

---

## Wiring Diagram

### AM312 Mini PIR (Recommended - 3.3V)

**Note:** AM312 uses **3.3V** (not 5V). No LED indicator - this is normal.

```
AM312 Mini          Raspberry Pi 5
──────────          ──────────────
VCC (Left)   ────►  Pin 1  (3.3V)   ← NOT 5V!
OUT (Middle) ────►  Pin 11 (GPIO 17)
GND (Right)  ────►  Pin 6  (Ground)
```

### HC-SR501 PIR (Alternative - 5V)

```
HC-SR501            Raspberry Pi 5
──────────          ──────────────
VCC  ────────────►  Pin 2  (5V)
OUT  ────────────►  Pin 11 (GPIO 17)
GND  ────────────►  Pin 6  (Ground)
```

### Pin Reference (from corner near SD card):
```
   Pin 1 ●  ● Pin 2      ← 3.3V (AM312) or 5V (HC-SR501)
   Pin 3 ●  ● Pin 4  
   Pin 5 ●  ● Pin 6      ← GND
   Pin 7 ●  ● Pin 8
   Pin 9 ●  ● Pin 10
  Pin 11 ●  ● Pin 12     ← GPIO17 (Signal)
```

## Software Setup on Raspberry Pi

### 1. Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install Dependencies
```bash
sudo apt install python3-pip python3-gpiozero -y
pip3 install requests --break-system-packages
```

### 3. Test Connectivity
```bash
# Replace with your Windows host IP
curl http://172.20.10.3:30800/health
```

### 4. Copy the Sensor Script

Option A - Copy from your computer:
```bash
# On your computer, in the smart-city-ids directory:
scp raspberry-pi/motion_sensor.py pi@<PI_IP>:~/motion_sensor.py
```

Option B - Download directly on Pi:
```bash
# On the Raspberry Pi:
wget https://raw.githubusercontent.com/YOUR_REPO/smart-city-ids/main/raspberry-pi/motion_sensor.py
```

Option C - Create manually on Pi:
```bash
nano ~/motion_sensor.py
# Paste the content from raspberry-pi/motion_sensor.py
```

## Find Your IDS API URL

With NAT + Port Proxy setup, use **Windows host IP**:
```bash
# On Windows, find IP:
ipconfig
# Use the Wi-Fi adapter IPv4 (e.g., 172.20.10.3)

# IDS API URL will be:
# http://<WINDOWS_IP>:30800
```

**Example:** `http://172.20.10.3:30800`

## Running the Sensor

### Test Mode (Simulation - No Sensor Required)
```bash
python3 motion_sensor.py --ids-url http://<WINDOWS_IP>:30800 --simulate
```

### Live Mode (With Real PIR Sensor)
```bash
python3 motion_sensor.py --ids-url http://<WINDOWS_IP>:30800 --gpio-pin 17
```

### All Arguments
| Argument | Default | Description |
|----------|---------|-------------|
| `--ids-url` | Required | IDS API URL (e.g., http://172.20.10.3:30800) |
| `--gpio-pin` | 17 | GPIO pin number for PIR sensor |
| `--device-id` | auto | Device ID (default: rpi5-motion-hostname) |
| `--simulate` | false | Run without real sensor |
| `--heartbeat` | 60 | Heartbeat interval in seconds |

### Run as Background Service
```bash
# Create systemd service
sudo nano /etc/systemd/system/smart-city-sensor.service
```

Paste:
```ini
[Unit]
Description=Smart City Motion Sensor
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
ExecStart=/usr/bin/python3 /home/pi/motion_sensor.py --ids-url http://<VM_IP>:30800
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable smart-city-sensor
sudo systemctl start smart-city-sensor
sudo systemctl status smart-city-sensor
```

## Verify Connection

### On the Raspberry Pi:
```bash
# Test connectivity
curl http://<VM_IP>:30800/health

# Check if sensor data is being sent
python3 motion_sensor.py --ids-url http://<VM_IP>:30800 --simulate
```

### On the Azure VM (K3s cluster):
```bash
# Check IDS API logs for IoT events
kubectl logs -n smart-city deploy/ids-api -f | grep IoT

# Check registered devices
curl http://localhost:8000/api/iot/devices

# Check IoT events
curl http://localhost:8000/api/iot/events
```

## Triggering Security Alerts

The sensor automatically generates security alerts when:

1. **Rapid Motion** - 5+ motion events in 10 seconds
   - This simulates potential intrusion
   - Triggers LLM analysis with xAI Grok-4

### Manual Test (Simulate Intrusion)
Wave your hand in front of the sensor rapidly (5+ times in 10 seconds) to trigger a security alert.

### Simulated Intrusion
The simulation mode randomly generates rapid motion events (~2% chance) to test the security pipeline.

## Troubleshooting

### "Cannot connect to IDS API"
1. Check VM firewall: `sudo ufw allow 30800`
2. Verify NodePort: `kubectl get svc -n smart-city`
3. Test from Pi: `ping <VM_IP>`

### "gpiozero not available"
```bash
sudo apt install python3-gpiozero
```

### Sensor not detecting motion
1. Adjust PIR sensitivity (small screw on sensor)
2. Wait 30-60 seconds after power-on (PIR warm-up)
3. Check wiring connections

### View Logs
```bash
# If running as service
sudo journalctl -u smart-city-sensor -f
```
