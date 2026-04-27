#!/bin/bash
# iDrink Setup Script
# Run once after a fresh Raspberry Pi OS flash
# Usage: bash setup.sh

set -e

echo "=================================================="
echo "  iDrink Setup"
echo "=================================================="

# Set static IP (skip if already configured)
echo ""
echo "[1/5] Setting static IP to 192.168.1.251..."
if grep -q "192.168.1.251" /etc/dhcpcd.conf; then
  echo "      Static IP already set, skipping."
else
  sudo bash -c 'cat >> /etc/dhcpcd.conf <<EOF

interface wlan0
static ip_address=192.168.1.251/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1
EOF'
fi

# Update package list
echo ""
echo "[2/5] Updating packages..."
sudo apt update -y

# Install Python packages
echo ""
echo "[3/5] Installing Flask and gpiozero..."
pip3 install flask gpiozero --break-system-packages

# Create systemd service
echo ""
echo "[4/5] Installing iDrink as a system service..."
sudo bash -c 'cat > /etc/systemd/system/idrink.service <<EOF
[Unit]
Description=iDrink Bartender
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/iDrink_8/server.py
WorkingDirectory=/home/pi/iDrink_8
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
EOF'

sudo systemctl daemon-reload
sudo systemctl enable idrink
sudo systemctl start idrink

# Done
echo ""
echo "[5/5] Done!"
echo ""
echo "  iDrink will be available at http://192.168.1.251:5000"
echo "  To check status: sudo systemctl status idrink"
echo "  To view logs:    journalctl -u idrink -n 50"
echo "=================================================="
echo ""
echo "Rebooting in 5 seconds to apply static IP..."
sleep 5
sudo reboot
