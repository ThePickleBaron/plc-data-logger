# PLC Data Logger

A robust and efficient Python application for logging data from PLC devices with a modern GUI interface.

## Features

- **Modern GUI Interface**
  - Real-time data monitoring
  - Historical trend visualization
  - Device and tag management
  - Configurable settings

- **Robust Data Collection**
  - Automatic reconnection handling
  - Batch tag reading for efficiency
  - Configurable sampling intervals
  - Error recovery mechanisms

- **Efficient Data Management**
  - Automatic data compression
  - Configurable retention policy
  - File rotation management
  - USB drive support for data export

- **Network Resilience**
  - Automatic device discovery
  - Connection retry mechanisms
  - Error logging and recovery
  - Graceful shutdown handling

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

## Configuration

The application can be configured through the GUI settings tab:

- **Sampling Settings**
  - Sample interval (seconds)
  - File rotation interval
  - Data retention period

- **Storage Settings**
  - Data retention policy
  - Auto-export settings
  - USB drive preferences

## Logging

Logs are stored in the following locations:
- Application logs: `logs/plc_logger_*.log`
- Data logs: `logs/plc_data_*.csv`
- Compressed data: `logs/plc_data_*.csv.gz`

## Troubleshooting

1. **Connection Issues**
   - Check network connectivity
   - Verify PLC IP addresses
   - Check firewall settings
   - Review connection logs

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

- Thanks to all contributors
- Built with Python and Tkinter
- Uses Matplotlib for visualization
- Inspired by industrial automation needs 