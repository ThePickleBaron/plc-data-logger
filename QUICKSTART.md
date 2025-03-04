# PLC Data Logger - Quick Start Guide

This guide will help you get started with the PLC Data Logger application quickly.

## Prerequisites

1. Python 3.8 or higher installed
2. Network access to your PLC devices
3. USB drive (optional, for data export)

## Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yourusername/plc_data_logger.git
   cd plc_data_logger
   ```

2. **Run Setup Script**
   ```bash
   ./setup.sh
   ```
   - Follow the prompts to install dependencies
   - Configure network settings
   - Set up logging directories

3. **Launch the Application**
   ```bash
   ./plc_logger_launcher.sh
   ```

## Jetson Nano Setup

### Prerequisites
1. Jetson Nano with display
2. Python 3.6 or later
3. Git installed
4. Network connection to PLCs

### Installation Steps for Jetson Nano

1. Update system packages:
```bash
sudo apt-get update
sudo apt-get upgrade
```

2. Install required system dependencies:
```bash
sudo apt-get install -y python3-pip python3-venv python3-tk
sudo apt-get install -y libhdf5-serial-dev hdf5-tools libhdf5-dev
sudo apt-get install -y libatlas-base-dev gfortran
```

3. Create and activate a Python virtual environment:
```bash
python3 -m venv ~/plc_env
source ~/plc_env/bin/activate
```

4. Clone the repository:
```bash
cd ~
git clone https://github.com/ThePickleBaron/plc-data-logger.git
cd plc-data-logger
```

5. Install Python dependencies:
```bash
pip3 install --upgrade pip
pip3 install -r requirements.txt
```

6. Set up execution permissions:
```bash
chmod +x setup.sh
chmod +x plc_logger_launcher.sh
chmod +x create_offline_package.sh
```

7. Run the setup script:
```bash
./setup.sh
```

8. Launch the application:
```bash
./plc_logger_launcher.sh
```

### Performance Tips for Jetson Nano

1. Monitor CPU temperature:
```bash
tegrastats
```

2. If needed, enable fan control:
```bash
sudo jetson_clocks
```

3. For better GUI performance:
- Keep the number of monitored tags under 50
- Use the default update interval (1 second)
- Close other graphical applications when running the logger

### Troubleshooting

1. If you see "Display not found" error:
```bash
export DISPLAY=:0
```

2. If matplotlib shows backend errors:
```bash
sudo apt-get install python3-matplotlib
```

3. If tkinter is not found:
```bash
sudo apt-get install python3-tk
```

4. If USB drives are not detected:
- Ensure the drive is formatted as ext4 or FAT32
- Check mount permissions:
```bash
sudo chmod 777 /media/nvidia
```

### Additional Configuration

1. Auto-start on boot:
```bash
mkdir -p ~/.config/autostart
cat << EOF > ~/.config/autostart/plc_logger.desktop
[Desktop Entry]
Type=Application
Name=PLC Logger
Exec=/home/nvidia/plc-data-logger/plc_logger_launcher.sh
EOF
```

2. Monitor system resources:
```bash
htop
```

3. Check logs:
```bash
tail -f ~/plc-data-logger/logs/plc_logger_*.log
```

## Basic Usage

### 1. Adding Devices

1. Click the "Scan Devices" button
2. Enter your network range (e.g., "10.13.50.0/24")
3. Select discovered devices from the list
4. Click "Add Selected Device"

### 2. Configuring Tags

1. Select a device from the dropdown
2. Click "Discover Tags"
3. Select tags to monitor
4. Click "Add Selected Tags"

### 3. Starting Data Collection

1. Configure sampling settings:
   - Set sample interval (default: 60 seconds)
   - Set file rotation interval (default: 3600 seconds)
   - Set data retention period (default: 30 days)

2. Click "Start Logging"
3. Monitor real-time data in the Monitor tab

### 4. Viewing Trends

1. Go to the Trends tab
2. Select a tag from the dropdown
3. Choose a time range
4. Click "Update Graph"

### 5. Data Export

1. Insert a USB drive
2. Click "Export Data"
3. Select the USB drive
4. Wait for export to complete

## Advanced Features

### Data Management

- **Automatic Compression**: Old data files are automatically compressed
- **Retention Policy**: Configure how long to keep data
- **File Rotation**: Automatic creation of new log files
- **USB Export**: Easy data transfer to external drives

### Error Handling

- **Automatic Reconnection**: Handles network interruptions
- **Error Recovery**: Recovers from temporary failures
- **Graceful Shutdown**: Ensures data integrity
- **Comprehensive Logging**: Detailed error tracking

### Performance Optimization

- **Batch Reading**: Efficient tag reading
- **Memory Management**: Limited history storage
- **Optimized I/O**: Efficient file operations
- **Background Processing**: Non-blocking operations

## Troubleshooting

### Common Issues

1. **No Devices Found**
   - Check network connectivity
   - Verify IP range
   - Check firewall settings

2. **Data Collection Errors**
   - Verify tag names
   - Check PLC connection
   - Review error logs

3. **GUI Issues**
   - Restart application
   - Check system resources
   - Verify Python installation

### Getting Help

1. Check the application logs in `logs/plc_logger_*.log`
2. Review the [README.md](README.md)
3. Create an issue in the repository
4. Contact support

## Best Practices

1. **Regular Maintenance**
   - Monitor disk space
   - Review log files
   - Update settings as needed

2. **Data Management**
   - Regular data exports
   - Archive old data
   - Monitor retention policy

3. **Network Setup**
   - Use static IP addresses
   - Configure firewall rules
   - Monitor network stability

4. **Performance**
   - Optimize sampling intervals
   - Manage tag count
   - Monitor system resources 