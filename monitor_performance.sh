#!/bin/bash

echo "PLC Data Logger - Performance Monitor"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to check CPU temperature
check_temp() {
    if [ -f /sys/devices/virtual/thermal/thermal_zone0/temp ]; then
        temp=$(cat /sys/devices/virtual/thermal/thermal_zone0/temp)
        temp_c=$((temp/1000))
        if [ $temp_c -gt 80 ]; then
            echo -e "${RED}Warning: CPU temperature is $temp_c°C (High)${NC}"
            echo "Suggestion: Consider improving cooling or reducing sampling rate"
        elif [ $temp_c -gt 70 ]; then
            echo -e "${YELLOW}Note: CPU temperature is $temp_c°C (Moderate)${NC}"
        else
            echo -e "${GREEN}CPU temperature is $temp_c°C (Good)${NC}"
        fi
    fi
}

# Function to check memory usage
check_memory() {
    total=$(free -m | awk '/^Mem:/{print $2}')
    used=$(free -m | awk '/^Mem:/{print $3}')
    usage=$((used*100/total))
    
    if [ $usage -gt 90 ]; then
        echo -e "${RED}Warning: Memory usage is $usage% (High)${NC}"
        echo "Suggestion: Reduce number of monitored tags or increase update interval"
    elif [ $usage -gt 80 ]; then
        echo -e "${YELLOW}Note: Memory usage is $usage% (Moderate)${NC}"
    else
        echo -e "${GREEN}Memory usage is $usage% (Good)${NC}"
    fi
}

# Function to check disk space
check_disk() {
    usage=$(df -h /opt/plc_logger | awk '/\//{print $5}' | sed 's/%//')
    if [ $usage -gt 90 ]; then
        echo -e "${RED}Warning: Disk usage is $usage% (High)${NC}"
        echo "Suggestion: Clean old logs or reduce retention period"
    elif [ $usage -gt 80 ]; then
        echo -e "${YELLOW}Note: Disk usage is $usage% (Moderate)${NC}"
    else
        echo -e "${GREEN}Disk usage is $usage% (Good)${NC}"
    fi
}

# Function to check CPU usage
check_cpu() {
    usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d. -f1)
    if [ $usage -gt 90 ]; then
        echo -e "${RED}Warning: CPU usage is $usage% (High)${NC}"
        echo "Suggestion: Increase update intervals or reduce number of tags"
    elif [ $usage -gt 80 ]; then
        echo -e "${YELLOW}Note: CPU usage is $usage% (Moderate)${NC}"
    else
        echo -e "${GREEN}CPU usage is $usage% (Good)${NC}"
    fi
}

# Function to check process status
check_process() {
    if pgrep -f "plc_logger_main.py" > /dev/null; then
        echo -e "${GREEN}PLC Logger is running${NC}"
        pid=$(pgrep -f "plc_logger_main.py")
        echo "Process ID: $pid"
        echo "Running since: $(ps -o lstart= -p $pid)"
    else
        echo -e "${RED}PLC Logger is not running${NC}"
    fi
}

# Main monitoring loop
while true; do
    clear
    echo "PLC Data Logger - System Monitor"
    echo "==============================="
    echo "Time: $(date)"
    echo
    
    echo "System Status:"
    echo "-------------"
    check_process
    echo
    
    echo "Resource Usage:"
    echo "--------------"
    check_cpu
    check_memory
    check_temp
    check_disk
    echo
    
    echo "Performance Recommendations:"
    echo "-------------------------"
    # Check for specific conditions and provide recommendations
    if [ $usage -gt 80 ] || [ $temp_c -gt 70 ]; then
        echo "1. Consider increasing update intervals"
        echo "2. Reduce number of monitored tags"
        echo "3. Enable fan control (sudo jetson_clocks)"
    else
        echo "System is running optimally"
    fi
    
    echo
    echo "Press Ctrl+C to exit"
    sleep 5
done 