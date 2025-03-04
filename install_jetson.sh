#!/bin/bash

echo "PLC Data Logger - Jetson Nano Installation Script"
echo "==============================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (sudo ./install_jetson.sh)"
    exit 1
fi

# Function to check command status
check_status() {
    if [ $? -eq 0 ]; then
        echo "✓ $1"
    else
        echo "✗ Error: $1 failed"
        exit 1
    fi
}

echo "Step 1: System Updates"
echo "---------------------"
apt-get update
check_status "System update"
apt-get upgrade -y
check_status "System upgrade"

echo -e "\nStep 2: Installing Dependencies"
echo "----------------------------"
apt-get install -y python3-pip python3-venv python3-tk
check_status "Python packages"
apt-get install -y libhdf5-serial-dev hdf5-tools libhdf5-dev
check_status "HDF5 libraries"
apt-get install -y libatlas-base-dev gfortran
check_status "Atlas and Fortran"
apt-get install -y htop
check_status "System monitoring tools"

echo -e "\nStep 3: Setting up Python Environment"
echo "--------------------------------"
# Create virtual environment
python3 -m venv /opt/plc_env
check_status "Virtual environment creation"

# Activate virtual environment and install packages
source /opt/plc_env/bin/activate
pip3 install --upgrade pip
check_status "Pip upgrade"
pip3 install -r requirements.txt
check_status "Python dependencies"

echo -e "\nStep 4: Optimizing Jetson Performance"
echo "--------------------------------"
# Enable maximum performance mode
if [ -f /usr/bin/jetson_clocks ]; then
    jetson_clocks
    check_status "Jetson performance optimization"
    
    # Add jetson_clocks to startup
    cat << EOF > /etc/systemd/system/jetson_clocks.service
[Unit]
Description=Jetson Performance Mode
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/jetson_clocks
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl enable jetson_clocks.service
    check_status "Performance mode autostart"
fi

echo -e "\nStep 5: Setting up Application"
echo "--------------------------"
# Create application directory
mkdir -p /opt/plc_logger
check_status "Application directory creation"

# Copy files to installation directory
cp -r * /opt/plc_logger/
check_status "File copying"

# Create logs directory with proper permissions
mkdir -p /opt/plc_logger/logs
chmod 777 /opt/plc_logger/logs
check_status "Log directory setup"

# Create USB mount point with proper permissions
mkdir -p /media/plc_data
chmod 777 /media/plc_data
check_status "USB mount point setup"

# Create launcher script
cat << EOF > /usr/local/bin/plc_logger
#!/bin/bash
source /opt/plc_env/bin/activate
cd /opt/plc_logger
./plc_logger_launcher.sh
EOF

chmod +x /usr/local/bin/plc_logger
check_status "Launcher script creation"

# Create desktop shortcut
cat << EOF > /usr/share/applications/plc_logger.desktop
[Desktop Entry]
Version=1.0
Name=PLC Data Logger
Comment=Monitor and log PLC data
Exec=/usr/local/bin/plc_logger
Icon=/opt/plc_logger/icon.png
Terminal=false
Type=Application
Categories=Utility;
EOF

check_status "Desktop shortcut creation"

# Set up auto-mounting for USB drives
cat << EOF > /etc/udev/rules.d/99-plc-logger-usb.rules
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", RUN{program}+="/bin/mkdir -p /media/plc_data/%k"
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", RUN{program}+="/bin/mount -o user,dmask=0000,fmask=0000 /dev/%k /media/plc_data/%k"
ACTION=="remove", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", RUN{program}+="/bin/umount -l /media/plc_data/%k"
ACTION=="remove", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", RUN{program}+="/bin/rmdir /media/plc_data/%k"
EOF

check_status "USB automount setup"

echo -e "\nStep 6: Final Configuration"
echo "------------------------"
# Set up automatic cleanup of old logs
cat << EOF > /etc/cron.daily/plc_logger_cleanup
#!/bin/bash
find /opt/plc_logger/logs -name "*.log" -mtime +30 -exec rm {} \;
EOF

chmod +x /etc/cron.daily/plc_logger_cleanup
check_status "Log cleanup configuration"

echo -e "\nInstallation Complete!"
echo "===================="
echo "The PLC Data Logger has been installed and configured."
echo "You can start it by:"
echo "1. Running 'plc_logger' from the terminal"
echo "2. Using the desktop shortcut"
echo "3. Rebooting (it will start automatically)"
echo -e "\nLogs are stored in: /opt/plc_logger/logs"
echo "USB drives will automatically mount in: /media/plc_data"
echo -e "\nEnjoy using PLC Data Logger!" 