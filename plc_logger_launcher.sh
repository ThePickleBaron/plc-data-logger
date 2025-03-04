#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}PLC Data Logger Launcher${NC}"
echo "======================="

# Check if running in virtual environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    if [ -f "/opt/plc_env/bin/activate" ]; then
        source /opt/plc_env/bin/activate
    elif [ -f "$HOME/plc_env/bin/activate" ]; then
        source $HOME/plc_env/bin/activate
    else
        echo -e "${RED}Error: Virtual environment not found${NC}"
        echo "Please run the installation script first"
        exit 1
    fi
fi

# Function to check system resources
check_resources() {
    # Check CPU temperature
    if [ -f /sys/devices/virtual/thermal/thermal_zone0/temp ]; then
        temp=$(cat /sys/devices/virtual/thermal/thermal_zone0/temp)
        temp_c=$((temp/1000))
        if [ $temp_c -gt 80 ]; then
            echo -e "${RED}Warning: CPU temperature is high ($temp_c°C)${NC}"
            echo "Consider enabling fan control with: sudo jetson_clocks"
        fi
    fi
    
    # Check memory
    total_mem=$(free -m | awk '/^Mem:/{print $2}')
    if [ $total_mem -lt 2000 ]; then
        echo -e "${YELLOW}Note: Running with limited memory ($total_mem MB)${NC}"
        echo "Performance may be affected"
    fi
    
    # Check disk space
    free_space=$(df -m /opt/plc_logger 2>/dev/null | awk '/\//{print $4}' || df -m . | awk '/\//{print $4}')
    if [ $free_space -lt 1000 ]; then
        echo -e "${YELLOW}Warning: Low disk space (${free_space}MB free)${NC}"
        echo "Consider cleaning old logs"
    fi
}

# Function to optimize system
optimize_system() {
    # Set process priority
    renice -n -10 $$
    
    # Set CPU governor to performance if possible
    if [ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]; then
        echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
    fi
    
    # Increase USB buffer size for better drive performance
    if [ -f /sys/module/usbcore/parameters/usbfs_memory_mb ]; then
        echo 1000 | sudo tee /sys/module/usbcore/parameters/usbfs_memory_mb
    fi
}

# Check and create required directories
mkdir -p logs
chmod 777 logs

# Perform system checks
echo "Performing system checks..."
check_resources

# Optimize system
echo "Optimizing system performance..."
optimize_system

# Start the monitoring script in the background
./monitor_performance.sh &
MONITOR_PID=$!

# Start the main application
echo -e "\n${GREEN}Starting PLC Data Logger...${NC}"
python3 plc_logger_main.py

# Cleanup
kill $MONITOR_PID 2>/dev/null 