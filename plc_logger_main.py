#!/usr/bin/env python3
"""
PLC Data Logger - Main Application
A Python application for logging data from PLC devices.
Optimized for Jetson Nano with display.
"""

import os
import sys
import json
import time
import logging
import gzip
import shutil
import threading
import ipaddress
from datetime import datetime, timedelta
from pathlib import Path
import csv
from typing import Dict, Any, List, Optional
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib
# Use Agg backend for better performance on Jetson Nano
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pandas as pd
from pylogix import PLC
import psutil

# Configure for Jetson Nano performance
HISTORY_LIMIT = 500  # Reduced from 1000 for better memory usage
UPDATE_INTERVAL = 1000  # GUI update interval in milliseconds
BATCH_SIZE = 10  # Number of tags to read in a single batch

# Configure logging
def setup_logging() -> logging.Logger:
    """Configure logging for the application."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"plc_logger_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

class PLCDataLogger:
    """Main class for PLC data logging operations"""
    
    def __init__(self, sample_interval: int = 60, save_interval: int = 3600):
        """Initialize the data logger
        
        Args:
            sample_interval (int): Time between samples in seconds
            save_interval (int): Time between creating new log files in seconds
        """
        self.logger = setup_logging()
        self.sample_interval = sample_interval
        self.save_interval = save_interval
        self.retention_days = 30  # Default retention period
        self.ip_addresses: List[str] = []
        self.ip_range = "10.13.50.0/24"  # Default subnet
        self.tags_to_log: Dict[str, List[str]] = {}  # Dict of {ip: [tags]}
        self.detected_tags: Dict[str, List[str]] = {}  # Dict of {ip: [tags]}
        self.device_info: Dict[str, Dict[str, str]] = {}  # Dict of {ip: {type, description}}
        
        # Data storage
        self.data_history: List[Dict[str, Any]] = []  # List of dicts with tag values
        self.current_filename: Optional[str] = None
        
        # Control flags
        self.running = False
        self.stop_event = threading.Event()
        
        # Load device info
        self.load_device_info()
        
        # Initialize data retention
        self.cleanup_old_data()

    def load_device_info(self) -> None:
        """Load known device information from file or create default"""
        device_info_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'device_info.json')
        
        try:
            if os.path.exists(device_info_file):
                with open(device_info_file, 'r') as f:
                    self.device_info = json.load(f)
            else:
                # Create default device info
                default_info = {
                    "10.13.50.100": {
                        "type": "CompactLogix",
                        "description": "Line 1 Main PLC"
                    },
                    "10.13.50.101": {
                        "type": "CompactLogix",
                        "description": "Line 2 Main PLC"
                    }
                }
                with open(device_info_file, 'w') as f:
                    json.dump(default_info, f, indent=2)
                self.device_info = default_info
        except Exception as e:
            self.logger.error(f"Error loading device info: {e}")
            self.device_info = {}

    def cleanup_old_data(self) -> None:
        """Clean up data files older than retention period"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            
            # Check both local and USB log directories
            log_dirs = [
                Path(os.path.dirname(os.path.abspath(__file__))) / "logs"
            ]
            
            # Add USB drive directories if available
            usb_drives = self.discover_usb_drives()
            for drive in usb_drives:
                log_dirs.append(Path(drive) / "plc_data_logs")
            
            for log_dir in log_dirs:
                if not log_dir.exists():
                    continue
                
                # Process CSV files
                for file in log_dir.glob("plc_data_*.csv"):
                    try:
                        # Extract date from filename
                        date_str = file.stem.split('_')[-1]
                        file_date = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                        
                        if file_date < cutoff_date:
                            # Compress old files
                            compressed_file = file.with_suffix('.csv.gz')
                            if not compressed_file.exists():
                                with open(file, 'rb') as f_in:
                                    with gzip.open(compressed_file, 'wb') as f_out:
                                        shutil.copyfileobj(f_in, f_out)
                                file.unlink()  # Delete original file
                            
                            # Remove compressed files older than retention period
                            if compressed_file.stat().st_mtime < cutoff_date.timestamp():
                                compressed_file.unlink()
                                
                    except Exception as e:
                        self.logger.error(f"Error processing file {file}: {e}")
                        
        except Exception as e:
            self.logger.error(f"Error during data cleanup: {e}")

    def _create_new_logfile(self):
        """Create a new log file for data storage"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Check for USB drives
        usb_drives = self.discover_usb_drives()
        if usb_drives:
            # Use the first USB drive
            base_dir = os.path.join(usb_drives[0], "plc_data_logs")
        else:
            # Fallback to local logs directory
            base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        
        # Create directory if it doesn't exist
        os.makedirs(base_dir, exist_ok=True)
        
        # Create filename
        self.current_filename = os.path.join(base_dir, f"plc_data_{timestamp}.csv")
        
        # Write header row
        try:
            with open(self.current_filename, 'w') as f:
                # Create header with all expected tags
                header = ["timestamp"]
                
                for ip in self.ip_addresses:
                    tags = self.tags_to_log.get(ip, [])
                    for tag in tags:
                        header.append(f"{ip}_{tag}")
                
                f.write(",".join(header) + "\n")
                
            # Run cleanup after creating new file
            self.cleanup_old_data()
                
        except Exception as e:
            self.logger.error(f"Error creating log file: {e}")
            self.current_filename = None

    def _write_data_to_file(self, data_point):
        """Write a data point to the current log file
        
        Args:
            data_point (dict): Data point to write
        """
        if not self.current_filename:
            return
        
        try:
            with open(self.current_filename, 'a') as f:
                # Get all expected columns from file header
                with open(self.current_filename, 'r') as read_f:
                    header = read_f.readline().strip().split(',')
                
                # Create a row with values for each column
                row = []
                for col in header:
                    if col in data_point:
                        row.append(str(data_point[col]))
                    else:
                        row.append("")
                
                f.write(",".join(row) + "\n")
                f.flush()  # Ensure data is written immediately
                
        except Exception as e:
            self.logger.error(f"Error writing to log file: {e}")
            # Try to create a new file on error
            self._create_new_logfile()

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.error(f"Configuration file {self.config_file} not found")
            sys.exit(1)
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON in configuration file {self.config_file}")
            sys.exit(1)

    def setup_data_logging(self):
        """Setup CSV file for data logging."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data_file = Path("logs") / f"plc_data_{timestamp}.csv"
        
        self.data_file = open(data_file, 'w', newline='')
        self.csv_writer = csv.writer(self.data_file)
        
        # Write header
        self.csv_writer.writerow(['timestamp'] + self.config.get('data_points', []))

    def _read_plc_data(self) -> Dict[str, Any]:
        """Read current data from all PLCs with automatic reconnection
        
        Returns:
            Dict[str, Any]: Current tag values with timestamp
        """
        data_point = {"timestamp": datetime.now().isoformat()}
        max_retries = 3
        retry_delay = 5  # seconds
        
        for ip in self.ip_addresses:
            retries = 0
            while retries < max_retries:
                try:
                    # Get tags to read for this IP
                    tags_to_read = self.tags_to_log.get(ip, [])
                    if not tags_to_read:
                        break
                    
                    with PLC() as comm:
                        comm.IPAddress = ip
                        comm.Timeout = 5000  # 5 second timeout
                        
                        # Read all tags at once for better performance
                        results = comm.Read(tags_to_read)
                        
                        # Process results
                        if isinstance(results, list):
                            for i, result in enumerate(results):
                                if result.Status == "Success":
                                    # Use tag name with IP as key to avoid conflicts
                                    tag_key = f"{ip}_{tags_to_read[i]}"
                                    data_point[tag_key] = result.Value
                        else:
                            # Single tag read
                            if results.Status == "Success":
                                tag_key = f"{ip}_{tags_to_read[0]}"
                                data_point[tag_key] = results.Value
                        
                        # Success - break retry loop
                        break
                        
                except Exception as e:
                    retries += 1
                    self.logger.warning(f"Attempt {retries}/{max_retries} failed for {ip}: {e}")
                    
                    if retries < max_retries:
                        time.sleep(retry_delay)
                    else:
                        self.logger.error(f"Failed to read from {ip} after {max_retries} attempts")
                        # Mark all tags for this IP as failed
                        for tag in tags_to_read:
                            tag_key = f"{ip}_{tag}"
                            data_point[tag_key] = None
        
        return data_point

    def _logging_thread(self, update_callback):
        """Thread function for continuous logging with error recovery
        
        Args:
            update_callback (function): Callback function for UI updates
        """
        last_file_time = time.time()
        consecutive_errors = 0
        max_consecutive_errors = 5
        error_delay = 30  # seconds
        
        while not self.stop_event.is_set():
            try:
                # Check if it's time to create a new log file
                current_time = time.time()
                if current_time - last_file_time >= self.save_interval:
                    self._create_new_logfile()
                    last_file_time = current_time
                
                # Read data from all PLCs
                data_point = self._read_plc_data()
                
                # Reset error counter on successful read
                consecutive_errors = 0
                
                # Store data in memory history (limit to 1000 points to avoid memory issues)
                self.data_history.append(data_point)
                if len(self.data_history) > 1000:
                    self.data_history.pop(0)
                
                # Write to log file
                self._write_data_to_file(data_point)
                
                # Call the update callback if provided
                if update_callback:
                    update_callback(data_point)
                
                # Wait for the next sample
                for _ in range(int(self.sample_interval)):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)
                    
            except Exception as e:
                consecutive_errors += 1
                self.logger.error(f"Error in logging thread: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    self.logger.critical("Too many consecutive errors, stopping logging")
                    self.stop_logging()
                    break
                
                # Exponential backoff for error delay
                time.sleep(error_delay * (2 ** (consecutive_errors - 1)))

    def log_data(self):
        """Log data from PLC to CSV file."""
        try:
            data = self.read_plc_data()
            timestamp = datetime.now().isoformat()
            
            # Write data row
            self.csv_writer.writerow([timestamp] + [data.get(point, '') for point in self.config.get('data_points', [])])
            self.data_file.flush()
            
            self.logger.info(f"Logged data: {data}")
        except Exception as e:
            self.logger.error(f"Error logging data: {e}")

    def run(self):
        """Main application loop."""
        self.logger.info("Starting PLC Data Logger")
        self.setup_data_logging()
        
        try:
            while True:
                self.log_data()
                time.sleep(self.config.get('logging_interval', 1))
        except KeyboardInterrupt:
            self.logger.info("Stopping PLC Data Logger")
        finally:
            if self.data_file:
                self.data_file.close()

    def discover_usb_drives(self) -> List[str]:
        """Discover mounted USB drives
        
        Returns:
            List[str]: List of mount points for USB drives
        """
        try:
            usb_drives = []
            
            # On Linux, check /proc/mounts for USB devices
            if sys.platform.startswith('linux'):
                if os.path.exists('/proc/mounts'):
                    with open('/proc/mounts', 'r') as f:
                        for line in f:
                            if 'usb' in line.lower() and any(x in line for x in ['/media/', '/mnt/']):
                                parts = line.split()
                                if len(parts) >= 2:
                                    mount_point = parts[1]
                                    if os.path.exists(mount_point) and os.access(mount_point, os.W_OK):
                                        usb_drives.append(mount_point)
            
            # Fallback method using psutil
            partitions = psutil.disk_partitions()
            for p in partitions:
                # Skip the root filesystem and non-removable drives
                if p.mountpoint == '/' or p.device == '':
                    continue
                
                if 'removable' in p.opts or any(x in p.mountpoint for x in ['/media/', '/mnt/']):
                    if os.path.exists(p.mountpoint) and os.access(p.mountpoint, os.W_OK):
                        usb_drives.append(p.mountpoint)
            
            return usb_drives
            
        except Exception as e:
            self.logger.error(f"Error discovering USB drives: {e}")
            return []

    def scan_ip_range(self) -> List[str]:
        """Scan a range of IP addresses for Allen-Bradley PLCs
        
        Returns:
            List[str]: List of IP addresses with responding PLCs
        """
        try:
            # Parse the IP range
            ip_network = ipaddress.ip_network(self.ip_range, strict=False)
            discovered = []
            
            # Scan each IP in the range
            for ip in ip_network.hosts():
                ip_str = str(ip)
                try:
                    with PLC() as comm:
                        comm.IPAddress = ip_str
                        comm.Timeout = 2000  # 2 seconds timeout for scanning
                        
                        # Try to read a simple tag to test connection
                        ret = comm.GetModuleProperties()
                        if ret.Value is not None:
                            # Save device info
                            self.device_info[ip_str] = {
                                "type": ret.Value.ProductName if hasattr(ret.Value, 'ProductName') else "Unknown",
                                "description": f"Device at {ip_str}"
                            }
                            discovered.append(ip_str)
                except Exception:
                    # Skip non-responsive IPs
                    pass
            
            # Save updated device info
            self.save_device_info()
            return discovered
            
        except Exception as e:
            self.logger.error(f"Error during IP scan: {e}")
            return []

    def discover_plc_tags(self, ip_address: str) -> List[str]:
        """Discover available tags in a PLC
        
        Args:
            ip_address (str): IP address of the PLC
            
        Returns:
            List[str]: List of tag names
        """
        try:
            with PLC() as comm:
                comm.IPAddress = ip_address
                
                # Get program tags
                program_tags = []
                ret = comm.GetProgramTagList()
                if ret.Status == "Success" and ret.Value is not None:
                    program_tags = [f"Program:{tag}" for tag in ret.Value]
                
                # Get controller tags
                ret = comm.GetTagList()
                controller_tags = []
                if ret.Status == "Success" and ret.Value is not None:
                    controller_tags = ret.Value
                
                # Store discovered tags
                all_tags = program_tags + controller_tags
                tag_names = [tag.TagName for tag in all_tags if hasattr(tag, 'TagName')]
                
                # Store in class dictionary
                self.detected_tags[ip_address] = tag_names
                
                return tag_names
                
        except Exception as e:
            self.logger.error(f"Error discovering tags: {e}")
            return []

    def start_logging(self, update_callback: Optional[callable] = None) -> None:
        """Start the data logging process
        
        Args:
            update_callback (callable, optional): Callback function for UI updates
        """
        if self.running:
            return
        
        self.running = True
        self.stop_event.clear()
        
        # Create a new log file
        self._create_new_logfile()
        
        # Start the logging thread
        threading.Thread(target=self._logging_thread, 
                         args=(update_callback,), 
                         daemon=True).start()

    def stop_logging(self) -> None:
        """Stop the logging process"""
        if not self.running:
            return
        
        self.stop_event.set()
        self.running = False

class PLCLoggerGUI(tk.Tk):
    def __init__(self):
        """Initialize the GUI with Jetson Nano optimizations"""
        super().__init__()
        
        # Set GUI parameters for Jetson display
        self.title("PLC Data Logger")
        self.geometry("800x480")  # Common Jetson display resolution
        
        # Enable hardware acceleration if available
        try:
            self.attributes('-hardware', True)
        except:
            pass
            
        # Reduce flickering
        self.update_idletasks()
        
        # Initialize the data logger
        self.logger = PLCDataLogger()
        
        # Initialize GUI variables with proper typing
        self._init_gui_variables()
        
        # Create GUI elements with optimized update intervals
        self.create_notebook()
        self.create_monitor_tab()
        self.create_trends_tab()
        self.create_settings_tab()
        
        # Initialize status bar
        self.create_status_bar()
        
        # Update USB drive status
        self.update_drive_status()
        
        # Configure update intervals
        self._configure_update_intervals()

    def _init_gui_variables(self):
        """Initialize GUI variables with proper typing"""
        self.monitor_tree: Optional[ttk.Treeview] = None
        self.tag_combo: Optional[ttk.Combobox] = None
        self.tag_var: tk.StringVar = tk.StringVar()
        self.range_var: tk.StringVar = tk.StringVar()
        self.fig: Optional[plt.Figure] = None
        self.ax: Optional[plt.Axes] = None
        self.canvas: Optional[FigureCanvasTkAgg] = None
        self.sample_var: tk.StringVar = tk.StringVar(value="60")
        self.file_var: tk.StringVar = tk.StringVar(value="3600")
        self.retention_var: tk.StringVar = tk.StringVar(value="30")
        self.auto_export_var: tk.BooleanVar = tk.BooleanVar(value=False)
        self.device_var: tk.StringVar = tk.StringVar()
        self.device_combo: Optional[ttk.Combobox] = None
        self.tag_list: Optional[tk.Listbox] = None
        self.selected_tags_list: Optional[tk.Listbox] = None
        self.start_btn: Optional[ttk.Button] = None
        self.stop_btn: Optional[ttk.Button] = None
        self.status_label: Optional[ttk.Label] = None
        self.drive_status: Optional[ttk.Label] = None
        self.ip_range_entry: Optional[ttk.Entry] = None
        self.device_list: Optional[tk.Listbox] = None

    def _configure_update_intervals(self):
        """Configure optimized update intervals for Jetson Nano"""
        # Update monitor less frequently
        self.after(UPDATE_INTERVAL, self._update_monitor)
        
        # Update drive status less frequently
        self.after(5000, self._update_drive_status)
        
        # Update trends graph less frequently
        self.after(UPDATE_INTERVAL * 2, self._update_trends)

    def _update_monitor(self):
        """Update monitor with optimized performance"""
        if self.monitor_tree and hasattr(self.logger, 'data_history') and self.logger.data_history:
            try:
                # Only update changed values
                current_data = self.logger.data_history[-1]
                for item in self.monitor_tree.get_children():
                    tag_name = self.monitor_tree.item(item)['values'][0]
                    if tag_name in current_data:
                        new_value = current_data[tag_name]
                        if str(new_value) != str(self.monitor_tree.item(item)['values'][1]):
                            self.monitor_tree.item(item, values=(tag_name, new_value, 
                                                               current_data.get('timestamp', ''), 
                                                               'OK' if new_value is not None else 'Error'))
                
                # Schedule next update
                self.after(UPDATE_INTERVAL, self._update_monitor)
            except Exception as e:
                self.logger.error(f"Error updating monitor: {e}")

    def _update_trends(self):
        """Update trends with optimized performance"""
        if self.canvas and self.ax:
            try:
                selected_tag = self.tag_var.get()
                if selected_tag and self.logger.data_history:
                    # Clear previous plot
                    self.ax.clear()
                    
                    # Convert data to pandas for efficient processing
                    df = pd.DataFrame(self.logger.data_history[-HISTORY_LIMIT:])
                    if 'timestamp' in df.columns and selected_tag in df.columns:
                        df['timestamp'] = pd.to_datetime(df['timestamp'])
                        self.ax.plot(df['timestamp'], df[selected_tag])
                        
                        # Optimize plot appearance
                        self.ax.set_xlabel('Time')
                        self.ax.set_ylabel('Value')
                        self.ax.grid(True)
                        plt.setp(self.ax.get_xticklabels(), rotation=45)
                        
                        # Use tight layout to prevent label cutoff
                        self.fig.tight_layout()
                        
                        # Update canvas
                        self.canvas.draw()
                
                # Schedule next update
                self.after(UPDATE_INTERVAL * 2, self._update_trends)
            except Exception as e:
                self.logger.error(f"Error updating trends: {e}")

    def create_monitor_tab(self):
        """Create monitor tab with optimized performance"""
        if not hasattr(self, 'monitor_tab'):
            return
            
        # Create frame with proper weights
        frame = ttk.Frame(self.monitor_tab)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Configure grid weights for better resizing
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        
        # Create treeview with scrollbar
        self.monitor_tree = ttk.Treeview(frame, columns=('Tag', 'Value', 'Timestamp', 'Status'),
                                       show='headings')
        
        # Configure columns for optimal display
        self.monitor_tree.heading('Tag', text='Tag')
        self.monitor_tree.heading('Value', text='Value')
        self.monitor_tree.heading('Timestamp', text='Timestamp')
        self.monitor_tree.heading('Status', text='Status')
        
        # Set column widths based on content
        self.monitor_tree.column('Tag', width=200)
        self.monitor_tree.column('Value', width=100)
        self.monitor_tree.column('Timestamp', width=150)
        self.monitor_tree.column('Status', width=80)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.monitor_tree.yview)
        self.monitor_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack with proper fill and expand
        self.monitor_tree.grid(row=1, column=0, sticky='nsew')
        scrollbar.grid(row=1, column=1, sticky='ns')

    def create_status_bar(self) -> None:
        """Create the status bar at the bottom of the window"""
        status_frame = ttk.Frame(self)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Status: Ready")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.drive_status = ttk.Label(status_frame, text="No USB Drive")
        self.drive_status.pack(side=tk.RIGHT)
    
    def update_status(self, message: str) -> None:
        """Update the status bar message
        
        Args:
            message (str): Status message to display
        """
        if self.status_label:
            self.status_label.config(text=f"Status: {message}")
            self.update()
    
    def update_drive_status(self) -> None:
        """Update the USB drive status display"""
        try:
            if not self.drive_status:
                return
                
            drives = self.logger.discover_usb_drives()
            if drives:
                self.drive_status.config(text=f"USB: {drives[0]}")
            else:
                self.drive_status.config(text="No USB Drive")
        except Exception as e:
            self.logger.error(f"Error updating drive status: {e}")
            if self.drive_status:
                self.drive_status.config(text="USB Error")

def main():
    """Main entry point"""
    try:
        app = PLCLoggerGUI()
        app.mainloop()
    except Exception as e:
        messagebox.showerror("Fatal Error", f"Application failed to start: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 