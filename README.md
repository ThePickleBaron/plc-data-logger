# PLC Data Logger

A robust and efficient Python application for logging data from PLC devices with a modern GUI interface. Built for reliability and performance in industrial environments.

## Key Features

- **Modern GUI Interface**
  - Real-time data monitoring with automatic updates
  - Historical trend visualization with time range selection
  - Comprehensive device and tag management
  - Configurable sampling and retention settings

- **Robust Data Collection**
  - Connection pooling for efficient PLC communications
  - Automatic reconnection with progressive backoff
  - Batch tag reading for network optimization
  - Configurable sampling intervals
  - Comprehensive error recovery mechanisms

- **Efficient Data Management**
  - Thread-safe buffered file writing
  - Smart file rotation based on time and size
  - Automatic data compression for archiving
  - Configurable retention policy
  - USB drive support with space verification

- **Network Resilience**
  - Multi-threaded scanning for responsive UI
  - Background operations for long-running tasks
  - Connection pooling to reduce connection overhead
  - Error logging with detailed diagnostics

- **Resource Management**
  - System resource monitoring (disk space, memory)
  - Optimized memory usage with data queues
  - Efficient background cleanup operations
  - Performance monitoring and alerts

## New Features

- **Tag Import**
  - Import tags from CSV, TXT, or XML files
  - Support for multiple FactoryTalk export formats
  - Background processing of large tag lists
  - Automatic validation and deduplication

- **Enhanced Stability**
  - Thread-safe data handling throughout the application
  - Clean shutdown procedures to preserve data integrity
  - Better error handling and recovery strategies
  - Resource monitoring to prevent crashes

- **Performance Optimizations**
  - Batch operations for network and file I/O
  - Connection pooling for PLC devices
  - Optimized GUI updates with thread safety
  - Background processing for resource-intensive tasks

## System Requirements

- Python 3.8 or higher
- Windows 10/11 or Linux
- Network connectivity to PLC devices
- USB drive (optional, for data export)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/plc_data_logger.git
   cd plc_data_logger
   ```

2. Run the setup script:
   ```bash
   ./setup.sh
   ```

3. Follow the installation prompts to:
   - Install required Python packages
   - Configure network settings
   - Set up logging directories
   - Create desktop shortcuts

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for detailed instructions.

### Basic Usage

1. **Scan and Add Devices**
   - Enter your network range (e.g. "192.168.0.0/24")
   - Click "Scan Devices" to discover PLCs
   - Select discovered devices and click "Add Selected Device"

2. **Import or Configure Tags**
   - Select a device from the list
   - Click "Import Tags" to load tags from a file
   - Alternatively, discover and add tags manually

3. **Configure Logging Settings**
   - Set sample interval (default: 60 seconds)
   - Set file rotation interval (default: 3600 seconds)
   - Set data retention period (default: 30 days)

4. **Start Logging**
   - Click "Start Logging" button
   - Monitor real-time data in the Monitor tab
   - View trends in the Trends tab

## Configuration

The application can be configured through the GUI settings tab:

- **Sampling Settings**
  - Sample interval (seconds)
  - File rotation interval
  - Data retention period

- **Storage Settings**
  - Data retention policy
  - USB drive monitoring
  - Automatic file compression

## Logging

Logs are stored in the following locations:
- Application logs: `logs/plc_logger_*.log`
- Data logs: `logs/plc_data_*.csv`
- Compressed data: `logs/plc_data_*.csv.gz`

## Advanced Features

### Tag Import

The application supports importing tags from:
- CSV files (tags in first column)
- Text files (one tag per line)
- XML files (FactoryTalk export format)

To import tags:
1. Select a device in the device list
2. Click "Import Tags"
3. Select your tag file
4. Tags will be imported and associated with the selected device

### Resource Monitoring

The application monitors:
- Disk space (warns when below 1GB free)
- Memory usage (optimizes memory consumption)
- CPU usage (via the monitor_performance.sh script)

### Performance Optimization

- **Connection Pooling**: Reuses PLC connections to reduce network overhead
- **Batch Operations**: Reads tags in batches for better performance
- **Buffered Writing**: Collects data and writes to disk in batches
- **Thread Management**: Uses background threads for I/O operations

## Troubleshooting

1. **Connection Issues**
   - Check network connectivity
   - Verify PLC IP addresses
   - Check firewall settings
   - Review connection logs with increased verbosity

2. **Data Collection Problems**
   - Verify tag names
   - Check sampling interval
   - Review error logs
   - Check disk space

3. **GUI Issues**
   - Restart application
   - Check system resources
   - Verify Python installation
   - Review application logs

4. **File I/O Issues**
   - Check disk space
   - Verify permissions on log directories
   - Check USB drive connections
   - Review file operation logs

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support, please:
1. Check the documentation
2. Review existing issues
3. Create a new issue if needed
4. Contact the maintainers

## Acknowledgments

- ThePickleBaron for the original concept and emergency deployment
- Built with Python and Tkinter
- Uses Matplotlib for visualization
- Inspired by industrial automation needs
