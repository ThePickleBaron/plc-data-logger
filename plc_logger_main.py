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
import re
from queue import Queue
from datetime import datetime, timedelta
from pathlib import Path
import csv
from typing import Dict, Any, List, Optional, Tuple
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib
# Use Agg backend for better performance on Jetson Nano
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pandas as pd
from pylogix import PLC

# Configure for Jetson Nano performance
HISTORY_LIMIT = 500  # Reduced from 1000 for better memory usage
UPDATE_INTERVAL = 1000  # GUI update interval in milliseconds
BATCH_SIZE = 10  # Number of tags to read in a single batch
MAX_QUEUE_SIZE = HISTORY_LIMIT * 2
MIN_DISK_SPACE_GB = 1

class BufferedFileWriter:
    """Thread-safe buffered file writer with batch commits"""
    def __init__(self, logger: logging.Logger):
        self.buffer: List[List[str]] = []
        self.logger = logger
        self._lock = threading.Lock()
        self.last_flush = time.time()
        self.current_file = None
        self.header = None
        
    def set_file(self, filename: str, header: List[str]) -> None:
        """Set the current file and prepare it if needed"""
        with self._lock:
            self.current_file = filename
            self.header = header
            
            # Create the file with header if it doesn't exist
            if not os.path.exists(filename):
                try:
                    os.makedirs(os.path.dirname(filename), exist_ok=True)
                    with open(filename, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(header)
                except Exception as e:
                    self.logger.error(f"Failed to create file {filename}: {e}")
        
    def add_record(self, record: Dict[str, Any], header: List[str]) -> None:
        """Add a record to the buffer"""
        with self._lock:
            try:
                row = [str(record.get(col, "")) for col in header]
                self.buffer.append(row)
                
                # Auto-flush if buffer size exceeds limit or 60 seconds passed
                if len(self.buffer) >= BATCH_SIZE or (time.time() - self.last_flush) > 60:
                    self.flush()
            except Exception as e:
                self.logger.error(f"Buffer add failed: {e}")

    def flush(self) -> None:
        """Flush buffer to disk"""
        with self._lock:
            if not self.buffer or not self.current_file:
                return
                
            try:
                with open(self.current_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerows(self.buffer)
                self.buffer.clear()
                self.last_flush = time.time()
            except Exception as e:
                self.logger.error(f"Buffer flush failed: {e}")

class PLCConnectionPool:
    """Manage PLC connections with connection pooling"""
    
    def __init__(self, logger):
        self.connections = {}
        self.logger = logger
        self._lock = threading.Lock()
    
    def get_connection(self, ip_address: str) -> PLC:
        """Get an existing connection or create a new one"""
        with self._lock:
            if ip_address not in self.connections:
                conn = PLC()
                conn.IPAddress = ip_address
                conn.Timeout = 5000
                self.connections[ip_address] = conn
                self.logger.debug(f"Created new PLC connection to {ip_address}")
            return self.connections[ip_address]
    
    def close_all(self):
        """Close all connections in the pool"""
        with self._lock:
            for ip, conn in self.connections.items():
                try:
                    conn.Close()
                    self.logger.debug(f"Closed PLC connection to {ip}")
                except Exception as e:
                    self.logger.error(f"Error closing PLC connection to {ip}: {e}")
            self.connections.clear()

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
        
        # Data storage with thread safety
        self.data_queue: Queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.data_lock = threading.Lock()
        self.file_writer = BufferedFileWriter(self.logger)
        self.last_disk_check = time.time()
        self.last_file_time = time.time()
        self.current_filename: Optional[str] = None
        
        # PLC connection management
        self.connection_pool = PLCConnectionPool(self.logger)
        
        # Control flags
        self.running = False
        self.stop_event = threading.Event()
        
        # Load device info
        self.load_device_info()

    def save_device_info(self) -> None:
        """Save device information to JSON file"""
        try:
            device_info_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'device_info.json')
            with open(device_info_file, 'w') as f:
                json.dump(self.device_info, f, indent=2)
            self.logger.info("Device information saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving device info: {e}")
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
                        # Extract date from filename safely
                        date_str = file.stem.split('_')[-2:]  # Get last two parts after split
                        if len(date_str) >= 2:
                            full_date_str = '_'.join(date_str)
                            try:
                                file_date = datetime.strptime(full_date_str, "%Y%m%d_%H%M%S")
                            except ValueError:
                                # Try alternative format with just the date part
                                try:
                                    file_date = datetime.strptime(date_str[0], "%Y%m%d")
                                except ValueError:
                                    self.logger.warning(f"Could not parse date from filename: {file.name}")
                                    continue
                        else:
                            self.logger.warning(f"Unexpected filename format: {file.name}")
                            continue
                        
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
            
    def _check_file_rotation(self) -> bool:
        """Check if it's time to rotate the log file"""
        if not self.current_filename or not os.path.exists(self.current_filename):
            return True
            
        try:
            # Check file size
            file_size = os.path.getsize(self.current_filename)
            if file_size > 100 * 1024 * 1024:  # 100 MB
                self.logger.info(f"Rotating log file due to size: {file_size / (1024*1024):.2f} MB")
                return True
                
            # Check time elapsed
            current_time = time.time()
            if current_time - self.last_file_time >= self.save_interval:
                self.logger.info("Rotating log file due to time interval")
                return True
                
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking file rotation: {e}")
            return True  # Rotate on error to be safe

    def _create_new_logfile(self):
        """Create a new log file with robustness improvements"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Choose storage location
        try:
            # Check for USB drives with sufficient space
            usb_drives = self.discover_usb_drives()
            base_dir = None
            
            for drive in usb_drives:
                try:
                    # Check available space
                    if sys.platform.startswith('linux'):
                        stat = os.statvfs(drive)
                        free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
                    else:
                        # Windows - simpler approach
                        import ctypes
                        free_bytes = ctypes.c_ulonglong(0)
                        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                            ctypes.c_wchar_p(drive), None, None, ctypes.pointer(free_bytes))
                        free_gb = free_bytes.value / (1024**3)
                        
                    if free_gb >= MIN_DISK_SPACE_GB:
                        base_dir = os.path.join(drive, "plc_data_logs")
                        self.logger.info(f"Using USB drive at {drive} with {free_gb:.1f}GB available")
                        break
                except Exception as e:
                    self.logger.warning(f"Error checking space on {drive}: {e}")
                    
            # Fallback to local logs directory
            if not base_dir:
                base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
                self.logger.info("Using local storage for logs")
            
            # Create directory if it doesn't exist
            os.makedirs(base_dir, exist_ok=True)
            
            # Create filename with the full timestamp format
            self.current_filename = os.path.join(base_dir, f"plc_data_{timestamp}.csv")
            self.last_file_time = time.time()
            
            # Create header for the new file
            header = ["timestamp"]
            for ip in self.ip_addresses:
                tags = self.tags_to_log.get(ip, [])
                for tag in tags:
                    header.append(f"{ip}_{tag}")
            
            # Set the file in the file writer
            self.file_writer.set_file(self.current_filename, header)
                
            # Run cleanup after creating new file
            threading.Thread(target=self.cleanup_old_data, daemon=True).start()
                
        except Exception as e:
            self.logger.error(f"Error creating log file: {e}")
            self.current_filename = None

    def _check_system_resources(self) -> bool:
        """Check disk space and memory"""
        try:
            # Disk space check
            if (time.time() - self.last_disk_check) > 3600:  # 1 hour
                if sys.platform.startswith('linux'):
                    stat = os.statvfs('/')
                    free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
                else:
                    # Windows
                    import ctypes
                    free_bytes = ctypes.c_ulonglong(0)
                    ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                        ctypes.c_wchar_p("C:\\"), None, None, ctypes.pointer(free_bytes))
                    free_gb = free_bytes.value / (1024**3)
                    
                if free_gb < MIN_DISK_SPACE_GB:
                    self.logger.critical(f"Insufficient disk space: {free_gb:.1f}GB")
                    return False
                self.last_disk_check = time.time()
                
            # Memory check
            try:
                import resource
                mem_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                if mem_usage > 500 * 1024:  # 500MB
                    self.logger.warning(f"High memory usage: {mem_usage/1024:.1f}MB")
            except ImportError:
                # resource module not available on Windows
                pass
                
            return True
        except Exception as e:
            self.logger.error(f"Resource check failed: {e}")
            return True  # Continue on check failure

    def _read_plc_data(self) -> Dict[str, Any]:
        """Read current data from all PLCs with improved error handling"""
        data_point = {"timestamp": datetime.now().isoformat()}
        max_retries = 3
        retry_delay = 5  # seconds
        
        for ip in self.ip_addresses:
            retries = 0
            success = False
            
            while retries < max_retries and not success and not self.stop_event.is_set():
                try:
                    # Get tags to read for this IP
                    tags_to_read = self.tags_to_log.get(ip, [])
                    if not tags_to_read:
                        break
                    
                    # Use connection pool instead of creating new connections
                    comm = self.connection_pool.get_connection(ip)
                    
                    # Use batch reading for better performance
                    for i in range(0, len(tags_to_read), BATCH_SIZE):
                        batch = tags_to_read[i:i+BATCH_SIZE]
                        results = comm.Read(batch)
                        
                        # Process results
                        if isinstance(results, list):
                            for j, result in enumerate(results):
                                if result.Status == "Success":
                                    tag_key = f"{ip}_{batch[j]}"
                                    data_point[tag_key] = result.Value
                                else:
                                    self.logger.warning(f"Read failed for {ip}_{batch[j]}: {result.Status}")
                                    tag_key = f"{ip}_{batch[j]}"
                                    data_point[tag_key] = None
                        else:
                            # Single tag read
                            if results.Status == "Success":
                                tag_key = f"{ip}_{batch[0]}"
                                data_point[tag_key] = results.Value
                            else:
                                self.logger.warning(f"Read failed for {ip}_{batch[0]}: {results.Status}")
                                tag_key = f"{ip}_{batch[0]}"
                                data_point[tag_key] = None
                    
                    success = True
                        
                except Exception as e:
                    retries += 1
                    self.logger.warning(f"Attempt {retries}/{max_retries} failed for {ip}: {e}")
                    
                    if retries < max_retries and not self.stop_event.is_set():
                        time.sleep(retry_delay * retries)  # Progressive backoff
                    else:
                        self.logger.error(f"Failed to read from {ip} after {max_retries} attempts")
                        # Mark all tags for this IP as failed
                        for tag in tags_to_read:
                            tag_key = f"{ip}_{tag}"
                            data_point[tag_key] = None
        
        return data_point

    def _logging_thread(self, update_callback):
        """Thread function for continuous logging with error recovery"""
        consecutive_errors = 0
        max_consecutive_errors = 5
        error_delay = 30  # seconds
        
        while not self.stop_event.is_set():
            try:
                # Check system resources
                if not self._check_system_resources():
                    time.sleep(30)
                    continue
                    
                # Check if it's time to create a new log file
                if self._check_file_rotation():
                    self._create_new_logfile()
                
                # Read data from all PLCs
                data_point = self._read_plc_data()
                
                # Reset error counter on successful read
                consecutive_errors = 0
                
                # Store data in memory with thread safety
                with self.data_lock:
                    if self.data_queue.qsize() >= HISTORY_LIMIT:
                        # Remove oldest item if queue is full
                        try:
                            self.data_queue.get_nowait()
                        except:
                            pass
                    self.data_queue.put(data_point)
                
                # Get the current file header
                header = ["timestamp"]
                for ip in self.ip_addresses:
                    tags = self.tags_to_log.get(ip, [])
                    for tag in tags:
                        header.append(f"{ip}_{tag}")
                
                # Write to log file
                try:
                    if self.current_filename:
                        self.file_writer.add_record(data_point, header)
                except Exception as e:
                    self.logger.error(f"Error writing to file: {e}")
                    # Try to create a new file on error
                    self._create_new_logfile()
                
                # Call the update callback if provided
                if update_callback:
                    update_callback(data_point)
                
                # Wait for the next sample
                self._wait_for_next_sample()
                    
            except Exception as e:
                consecutive_errors += 1
                self.logger.error(f"Error in logging thread: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    self.logger.critical("Too many consecutive errors, stopping logging")
                    self.stop_logging()
                    break
                
                # Exponential backoff for error delay
                backoff_time = error_delay * (2 ** (consecutive_errors - 1))
                self.logger.warning(f"Backing off for {backoff_time} seconds")
                
                # Wait with stop check
                for _ in range(int(backoff_time)):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)
    
    def _wait_for_next_sample(self):
        """Wait for the next sample interval with stop check"""
        for _ in range(int(self.sample_interval)):
            if self.stop_event.is_set():
                break
            time.sleep(1)

    def discover_usb_drives(self) -> List[str]:
        """Discover mounted USB drives with fallback methods
        
        Returns:
            List[str]: List of mount points for USB drives
        """
        usb_drives = []
        try:
            if sys.platform.startswith('linux'):
                # Try reading from /proc/mounts first
                if os.path.exists('/proc/mounts'):
                    with open('/proc/mounts', 'r') as f:
                        for line in f:
                            if 'usb' in line.lower() and any(x in line for x in ['/media/', '/mnt/']):
                                parts = line.split()
                                if len(parts) >= 2:
                                    mount_point = parts[1]
                                    if os.path.exists(mount_point) and os.access(mount_point, os.W_OK):
                                        usb_drives.append(mount_point)
            
                # Fallback to checking common USB mount points
                if not usb_drives:
                    common_paths = ['/media', '/mnt']
                    for base_path in common_paths:
                        if os.path.exists(base_path):
                            for item in os.listdir(base_path):
                                full_path = os.path.join(base_path, item)
                                if os.path.ismount(full_path) and os.access(full_path, os.W_OK):
                                    usb_drives.append(full_path)
                                
            elif sys.platform.startswith('win'):
                # Use Windows API to detect removable drives
                import ctypes
                drives = []
                bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                for letter in range(65, 91):  # A-Z
                    if bitmask & (1 << (letter - 65)):
                        drive = chr(letter) + ":\\"
                        if ctypes.windll.kernel32.GetDriveTypeW(drive) == 2:  # DRIVE_REMOVABLE
                            if os.path.exists(drive) and os.access(drive, os.W_OK):
                                usb_drives.append(drive)
        except Exception as e:
            self.logger.error(f"Error discovering USB drives: {e}")
        
        return usb_drives

    def scan_ip_range(self) -> List[str]:
        """Scan a range of IP addresses for Allen-Bradley PLCs
        
        Returns:
            List[str]: List of IP addresses with responding PLCs
        """
        try:
            # Parse the IP range
            ip_network = ipaddress.ip_network(self.ip_range, strict=False)
            discovered = []
            
            self.logger.info(f"Starting IP scan of {self.ip_range}")
            
            # Scan each IP in the range
            for ip in ip_network.hosts():
                ip_str = str(ip)
                try:
                    self.logger.info(f"Checking IP: {ip_str}")
                    with PLC() as comm:
                        comm.IPAddress = ip_str
                        comm.Timeout = 2000  # 2 seconds timeout for scanning
                        
                        # Try to read a simple tag to test connection
                        ret = comm.GetModuleProperties()
                        self.logger.info(f"Result for {ip_str}: {ret.Status}")
                        
                        if ret.Status == "Success" and ret.Value is not None:
                            # Save device info
                            self.device_info[ip_str] = {
                                "type": ret.Value.ProductName if hasattr(ret.Value, 'ProductName') else "Unknown",
                                "description": f"Device at {ip_str}"
                            }
                            discovered.append(ip_str)
                            self.logger.info(f"Discovered PLC at {ip_str}")
                except Exception as e:
                    # Skip non-responsive IPs
                    self.logger.debug(f"No response from {ip_str}: {e}")
                    pass
            
            # Save updated device info
            self.save_device_info()
            
            self.logger.info(f"IP scan completed. Found {len(discovered)} devices")
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

    def import_tags_from_file(self, filename: str, ip_address: str) -> List[str]:
        """Import tags from a file (supports CSV, TXT and XML formats)
        
        Args:
            filename (str): Path to the file with tags
            ip_address (str): IP address to associate with the tags
            
        Returns:
            List[str]: List of imported tag names
        """
        imported_tags = []
        try:
            file_ext = os.path.splitext(filename)[1].lower()
            
            if file_ext == '.csv':
                imported_tags = self._import_tags_from_csv(filename, ip_address)
            elif file_ext == '.txt':
                imported_tags = self._import_tags_from_txt(filename, ip_address)
            elif file_ext == '.xml':
                imported_tags = self._import_tags_from_xml(filename, ip_address)
            else:
                self.logger.error(f"Unsupported file format: {file_ext}")
                return []
                
            # Update tags for this IP address
            if ip_address not in self.tags_to_log:
                self.tags_to_log[ip_address] = []
                
            # Add tags that don't already exist
            for tag in imported_tags:
                if tag not in self.tags_to_log[ip_address]:
                    self.tags_to_log[ip_address].append(tag)
                    
            return imported_tags
            
        except Exception as e:
            self.logger.error(f"Error importing tags: {e}")
            return []
            
    def _import_tags_from_csv(self, filename: str, ip_address: str) -> List[str]:
        """Import tags from a CSV file
        
        Args:
            filename (str): Path to the CSV file
            ip_address (str): IP address to associate with the tags
            
        Returns:
            List[str]: List of imported tag names
        """
        imported_tags = []
        try:
            with open(filename, 'r') as f:
                # Try to determine dialect
                sample = f.read(1024)
                f.seek(0)
                
                sniffer = csv.Sniffer()
                has_header = sniffer.has_header(sample)
                dialect = sniffer.sniff(sample)
                
                reader = csv.reader(f, dialect)
                
                # Skip header if present
                if has_header:
                    next(reader)
                    
                # Look for tag names in the first column
                for row in reader:
                    if row and len(row) > 0 and row[0].strip():  # Check if row exists and first cell is not empty
                        tag_name = row[0].strip()
                        # Remove any quotes or extra whitespace
                        tag_name = tag_name.strip('"\'')
                        imported_tags.append(tag_name)
                        
            self.logger.info(f"Imported {len(imported_tags)} tags from CSV file")
            return imported_tags
            
        except Exception as e:
            self.logger.error(f"Error importing tags from CSV: {e}")
            return []
            
    def _import_tags_from_txt(self, filename: str, ip_address: str) -> List[str]:
        """def _import_tags_from_txt(self, filename: str, ip_address: str) -> List[str]:

        
        Args:
            filename (str): Path to the TXT file
            ip_address (str): IP address to associate with the tags
            
        Returns:
            List[str]: List of imported tag names
        """
        imported_tags = []
        try:
            with open(filename, 'r') as f:
                lines = f.readlines()
                
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#'):  # Skip empty lines and comments
                        # Try to extract the tag name
                        parts = line.split(',')  # Handle comma-separated formats
                        tag_name = parts[0].strip()
                        
                        # Remove any quotes or extra whitespace
                        tag_name = tag_name.strip('"\'')
                        
                        if tag_name:
                            imported_tags.append(tag_name)
                        
            self.logger.info(f"Imported {len(imported_tags)} tags from TXT file")
            return imported_tags
            
        except Exception as e:
            self.logger.error(f"Error importing tags from TXT: {e}")
            return []
            
    def _import_tags_from_xml(self, filename: str, ip_address: str) -> List[str]:
        """Import tags from an XML file (FactoryTalk XML export)
        
        Args:
            filename (str): Path to the XML file
            ip_address (str): IP address to associate with the tags
            
        Returns:
            List[str]: List of imported tag names
        """
        imported_tags = []
        try:
            import xml.etree.ElementTree as ET
            
            tree = ET.parse(filename)
            root = tree.getroot()
            
            # Look for tag elements with different potential formats
            
            # Format 1: FactoryTalk tag export
            tags = root.findall(".//Tag")
            for tag in tags:
                name_attr = tag.get('Name')
                if name_attr:
                    imported_tags.append(name_attr)
                    
            # Format 2: Tag names in TagName elements
            if not imported_tags:
                tag_elements = root.findall(".//TagName")
                for tag_element in tag_elements:
                    if tag_element.text:
                        imported_tags.append(tag_element.text.strip())
            
            # Format 3: Tag names as element names with 'tag' prefix
            if not imported_tags:
                for element in root.findall(".//*"):
                    tag_name = element.tag
                    if tag_name.lower().startswith('tag'):
                        name_value = element.get('name') or element.text
                        if name_value:
                            imported_tags.append(name_value.strip())
                            
            self.logger.info(f"Imported {len(imported_tags)} tags from XML file")
            return imported_tags
            
        except Exception as e:
            self.logger.error(f"Error importing tags from XML: {e}")
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
        """Stop the logging process with clean shutdown"""
        if not self.running:
            return
        
        self.stop_event.set()
        self.running = False
        
        # Ensure all data is written to disk
        try:
            self.file_writer.flush()
            self.logger.info("Flushed remaining data to disk")
        except Exception as e:
            self.logger.error(f"Error during final flush: {e}")
        
        # Close all PLC connections
        try:
            self.connection_pool.close_all()
        except Exception as e:
            self.logger.error(f"Error closing PLC connections: {e}")
        
        # Wait for threads to terminate gracefully
        self.logger.info("Waiting for threads to terminate...")
        time.sleep(1)  # Give threads time to finish

class PLCLoggerGUI(tk.Tk):
    def __init__(self):
        """Initialize the GUI with Jetson Nano optimizations"""
        super().__init__()
        
        # Initialize logger first
        self.logger = PLCDataLogger()
        
        # Set GUI parameters for Jetson display
        self.title("PLC Data Logger")
        self.geometry("800x480")  # Common Jetson display resolution
        
        # Initialize notebook
        self.notebook: Optional[ttk.Notebook] = None
        self.monitor_tab: Optional[ttk.Frame] = None
        self.trends_tab: Optional[ttk.Frame] = None
        self.settings_tab: Optional[ttk.Frame] = None
        
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
        
        # Set up application closing event
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _init_gui_variables(self) -> None:
        """Initialize GUI variables with proper typing"""
        # Tree and list variables
        self.monitor_tree: Optional[ttk.Treeview] = None
        self.device_list: Optional[tk.Listbox] = None
        self.tag_list: Optional[tk.Listbox] = None
        self.selected_tags_list: Optional[tk.Listbox] = None
        
        # Combo boxes
        self.tag_combo: Optional[ttk.Combobox] = None
        self.device_combo: Optional[ttk.Combobox] = None
        
        # String variables
        self.tag_var: tk.StringVar = tk.StringVar()
        self.range_var: tk.StringVar = tk.StringVar()
        self.sample_var: tk.StringVar = tk.StringVar(value="60")
        self.file_var: tk.StringVar = tk.StringVar(value="3600")
        self.retention_var: tk.StringVar = tk.StringVar(value="30")
        self.device_var: tk.StringVar = tk.StringVar()
        
        # Boolean variables
        self.auto_export_var: tk.BooleanVar = tk.BooleanVar(value=False)
        
        # Matplotlib variables
        self.fig: Optional[plt.Figure] = None
        self.ax: Optional[plt.Axes] = None
        self.canvas: Optional[FigureCanvasTkAgg] = None
        
        # Entry fields
        self.ip_range_entry: Optional[ttk.Entry] = None
        
        # Buttons
        self.start_btn: Optional[ttk.Button] = None
        self.stop_btn: Optional[ttk.Button] = None
        
        # Labels
        self.status_label: Optional[ttk.Label] = None
        self.drive_status: Optional[ttk.Label] = None

    def _configure_update_intervals(self):
        """Configure optimized update intervals for Jetson Nano"""
        # Update monitor less frequently
        self.after(UPDATE_INTERVAL, self._update_monitor)
        
        # Update drive status less frequently
        self.after(5000, self.update_drive_status)
        
        # Update trends graph less frequently
        self.after(UPDATE_INTERVAL * 2, self._update_trends)

    def _update_monitor(self):
        """Update monitor with optimized performance and error handling"""
        if not self.monitor_tree:
            self.after(UPDATE_INTERVAL, self._update_monitor)
            return
        
        try:
            # Get data from the queue safely
            with self.logger.data_lock:
                if self.logger.data_queue.empty():
                    self.after(UPDATE_INTERVAL, self._update_monitor)
                    return
                
                # Get the latest data point
                data_items = list(self.logger.data_queue.queue)
                if not data_items:
                    self.after(UPDATE_INTERVAL, self._update_monitor)
                    return
                    
                current_data = data_items[-1]  # Get the latest item
                
            # Clear existing items for a complete refresh
            for item in self.monitor_tree.get_children():
                self.monitor_tree.delete(item)
            
            # Add all items from the latest data point
            timestamp = current_data.get('timestamp', '')
            for key, value in current_data.items():
                if key != 'timestamp':
                    try:
                        # Extract IP and tag from the key
                        parts = key.split('_', 1)
                        if len(parts) == 2:
                            ip, tag = parts
                            status = "OK" if value is not None else "Error"
                            self.monitor_tree.insert('', 'end', values=(key, value, timestamp, status))
                    except Exception as e:
                        self.logger.error(f"Error processing tag {key}: {e}")
            
            # Update tag combo for trends if needed
            self.update_tag_combo()
            
        except RuntimeError as e:
            # Handle thread safety issues
            self.logger.error(f"GUI update error: {e}")
        except Exception as e:
            self.logger.error(f"Error updating monitor: {e}")
        finally:
            # Schedule next update with error handling
            try:
                self.after(UPDATE_INTERVAL, self._update_monitor)
            except Exception as e:
                self.logger.error(f"Error scheduling monitor update: {e}")

    def _update_trends(self):
        """Update trends with optimized performance"""
        if not self.canvas or not self.ax:
            self.after(UPDATE_INTERVAL * 2, self._update_trends)
            return
            
        try:
            selected_tag = self.tag_var.get()
            if not selected_tag:
                self.after(UPDATE_INTERVAL * 2, self._update_trends)
                return
                
            # Get data from the queue safely
            with self.logger.data_lock:
                if self.logger.data_queue.empty():
                    self.after(UPDATE_INTERVAL * 2, self._update_trends)
                    return
                
                # Convert queue to list for pandas
                data_items = list(self.logger.data_queue.queue)
            
            if data_items:
                # Clear previous plot
                self.ax.clear()
                
                # Convert data to pandas for efficient processing
                df = pd.DataFrame(data_items[-HISTORY_LIMIT:])
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
            
        except Exception as e:
            self.logger.error(f"Error updating trends: {e}")
        finally:
            # Schedule next update
            self.after(UPDATE_INTERVAL * 2, self._update_trends)

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
        finally:
            # Schedule next update
            self.after(5000, self.update_drive_status)

    def create_notebook(self) -> None:
        """Create the notebook for tabs"""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tab frames
        self.monitor_tab = ttk.Frame(self.notebook)
        self.trends_tab = ttk.Frame(self.notebook)
        self.settings_tab = ttk.Frame(self.notebook)
        
        # Add tabs to notebook
        self.notebook.add(self.monitor_tab, text="Monitor")
        self.notebook.add(self.trends_tab, text="Trends")
        self.notebook.add(self.settings_tab, text="Settings")

    def create_trends_tab(self) -> None:
        """Create trends tab with graph and controls"""
        # Create main frame
        frame = ttk.Frame(self.trends_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create controls frame
        controls_frame = ttk.Frame(frame)
        controls_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Tag selection
        ttk.Label(controls_frame, text="Tag:").pack(side=tk.LEFT, padx=5)
        self.tag_combo = ttk.Combobox(controls_frame, textvariable=self.tag_var)
        self.tag_combo.pack(side=tk.LEFT, padx=5)
        
        # Time range selection
        ttk.Label(controls_frame, text="Range:").pack(side=tk.LEFT, padx=5)
        range_combo = ttk.Combobox(controls_frame, textvariable=self.range_var,
                                 values=["1 hour", "6 hours", "12 hours", "24 hours"])
        range_combo.pack(side=tk.LEFT, padx=5)
        range_combo.set("1 hour")
        
        # Create matplotlib figure
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def create_settings_tab(self) -> None:
        """Create settings tab with configuration options"""
        # Create main frame
        frame = ttk.Frame(self.settings_tab)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Sampling settings
        sampling_frame = ttk.LabelFrame(frame, text="Sampling Settings")
        sampling_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Sample interval
        ttk.Label(sampling_frame, text="Sample Interval (seconds):").grid(row=0, column=0, padx=5, pady=5)
        sample_entry = ttk.Entry(sampling_frame, textvariable=self.sample_var)
        sample_entry.grid(row=0, column=1, padx=5, pady=5)
        
        # File rotation interval
        ttk.Label(sampling_frame, text="File Rotation (seconds):").grid(row=1, column=0, padx=5, pady=5)
        file_entry = ttk.Entry(sampling_frame, textvariable=self.file_var)
        file_entry.grid(row=1, column=1, padx=5, pady=5)
        
        # Data retention
        ttk.Label(sampling_frame, text="Data Retention (days):").grid(row=2, column=0, padx=5, pady=5)
        retention_entry = ttk.Entry(sampling_frame, textvariable=self.retention_var)
        retention_entry.grid(row=2, column=1, padx=5, pady=5)
        
        # Device management
        device_frame = ttk.LabelFrame(frame, text="Device Management")
        device_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # IP range entry
        ttk.Label(device_frame, text="IP Range:").grid(row=0, column=0, padx=5, pady=5)
        self.ip_range_entry = ttk.Entry(device_frame)
        self.ip_range_entry.insert(0, "10.13.50.0/24")
        self.ip_range_entry.grid(row=0, column=1, padx=5, pady=5)
        
        # Scan button
        scan_btn = ttk.Button(device_frame, text="Scan Devices",
                            command=lambda: self.scan_devices())
        scan_btn.grid(row=0, column=2, padx=5, pady=5)
        
        # Device list
        self.device_list = tk.Listbox(device_frame, height=5, selectmode=tk.MULTIPLE)
        self.device_list.grid(row=1, column=0, columnspan=3, sticky='nsew', padx=5, pady=5)
        
        # Buttons frame for device actions
        device_buttons_frame = ttk.Frame(device_frame)
        device_buttons_frame.grid(row=2, column=0, columnspan=3, sticky='ew', padx=5, pady=5)
        
        # Add device button
        add_device_btn = ttk.Button(device_buttons_frame, text="Add Selected Device",
                                command=lambda: self.add_selected_device())
        add_device_btn.pack(side=tk.LEFT, padx=5)
        
        # Import tags button
        import_tags_btn = ttk.Button(device_buttons_frame, text="Import Tags",
                                 command=lambda: self.import_tags())
        import_tags_btn.pack(side=tk.LEFT, padx=5)
        
        # Control buttons
        control_frame = ttk.Frame(frame)
        control_frame.pack(fill=tk.X, padx=5, pady=10)
        
        self.start_btn = ttk.Button(control_frame, text="Start Logging",
                                  command=lambda: self.start_logging())
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="Stop Logging",
                                 command=lambda: self.stop_logging())
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn.state(['disabled'])

    def validate_ip_range(self) -> bool:
        """Validate IP range input"""
        try:
            ipaddress.ip_network(self.ip_range_entry.get(), strict=False)
            return True
        except ValueError as e:
            messagebox.showerror("Invalid IP", f"Invalid IP range: {str(e)}")
            return False

    def scan_devices(self) -> None:
        """Scan for PLC devices on the network"""
        try:
            # Validate IP range first
            if not self.validate_ip_range():
                return
                
            ip_range = self.ip_range_entry.get()
            self.logger.ip_range = ip_range
            self.update_status(f"Scanning {ip_range}...")
            
            # Clear existing list
            self.device_list.delete(0, tk.END)
            
            # Start scan in a separate thread to prevent UI freezing
            threading.Thread(target=self._scan_thread, args=(ip_range,), daemon=True).start()
            
        except Exception as e:
            self.logger.error(f"Error scanning devices: {e}")
            messagebox.showerror("Error", f"Failed to scan devices: {str(e)}")

    def _scan_thread(self, ip_range: str) -> None:
        """Thread function for IP scanning"""
        try:
            # Start scan
            discovered = self.logger.scan_ip_range()
            
            # Update list in the main thread
            self.after(0, lambda: self._update_device_list(discovered))
            
        except Exception as e:
            self.logger.error(f"Error in scan thread: {e}")
            self.after(0, lambda: self.update_status(f"Scan error: {str(e)}"))

    def _update_device_list(self, discovered: List[str]) -> None:
        """Update device list with discovered devices"""
        # Clear existing list (just to be safe)
        self.device_list.delete(0, tk.END)
        
        # Add each discovered device
        for ip in discovered:
            device_info = self.logger.device_info.get(ip, {})
            device_type = device_info.get('type', 'Unknown')
            self.device_list.insert(tk.END, f"{ip} ({device_type})")
        
        self.update_status(f"Found {len(discovered)} devices")

    def add_selected_device(self):
        """Add the selected device from the list to the monitored devices"""
        try:
            selected_indices = self.device_list.curselection()
            if not selected_indices:
                messagebox.showinfo("Selection", "Please select a device first")
                return
                
            for idx in selected_indices:
                item = self.device_list.get(idx)
                # Extract IP address from the list item (format: "IP (Type)")
                ip = item.split(" ")[0]
                
                if ip not in self.logger.ip_addresses:
                    self.logger.ip_addresses.append(ip)
                    
                    # Initialize tags for this IP if not already present
                    if ip not in self.logger.tags_to_log:
                        self.logger.tags_to_log[ip] = []
                        
            self.update_status(f"Added {len(selected_indices)} device(s)")
            
        except Exception as e:
            self.logger.error(f"Error adding device: {e}")
            messagebox.showerror("Error", f"Failed to add device: {str(e)}")

    def import_tags(self):
        """Import tags from a file"""
        try:
            # Get the selected device first
            selected_indices = self.device_list.curselection()
            if not selected_indices:
                messagebox.showinfo("Selection", "Please select a device first")
                return
                
            # Use the first selected device
            idx = selected_indices[0]
            device_item = self.device_list.get(idx)
            ip = device_item.split(" ")[0]
            
            # Show file dialog
            filename = filedialog.askopenfilename(
                title="Select Tags File",
                filetypes=(
                    ("CSV files", "*.csv"),
                    ("Text files", "*.txt"),
                    ("XML files", "*.xml"),
                    ("All files", "*.*")
                )
            )
            
            if not filename:
                return  # User cancelled
                
            # Update status
            self.update_status(f"Importing tags from {filename}...")
            
            # Import tags in a background thread
            threading.Thread(
                target=self._import_tags_thread,
                args=(filename, ip),
                daemon=True
            ).start()
            
        except Exception as e:
            self.logger.error(f"Error starting tag import: {e}")
            messagebox.showerror("Error", f"Failed to import tags: {str(e)}")
            
    def _import_tags_thread(self, filename: str, ip: str):
        """Thread function for tag import"""
        try:
            # Import tags
            imported_tags = self.logger.import_tags_from_file(filename, ip)
            
            # Update UI in main thread
            self.after(0, lambda: self._update_after_import(ip, imported_tags))
            
        except Exception as e:
            self.logger.error(f"Error in import thread: {e}")
            self.after(0, lambda: self.update_status(f"Import error: {str(e)}"))
            
    def _update_after_import(self, ip: str, imported_tags: List[str]):
        """Update UI after tag import"""
        if imported_tags:
            # Show success message
            messagebox.showinfo(
                "Import Successful",
                f"Successfully imported {len(imported_tags)} tags for device {ip}"
            )
            
            # Update tag combo for trends
            self.update_tag_combo()
            
            # Update status
            self.update_status(f"Imported {len(imported_tags)} tags")
        else:
            messagebox.showwarning(
                "Import Issue",
                "No tags were imported. Check the file format and logs for details."
            )
            
            self.update_status("Import failed - no tags found")

    def start_logging(self) -> None:
        """Start the logging process"""
        try:
            # Update intervals
            self.logger.sample_interval = int(self.sample_var.get())
            self.logger.save_interval = int(self.file_var.get())
            self.logger.retention_days = int(self.retention_var.get())
            
            # Start logging
            self.logger.start_logging(update_callback=self.update_monitor_data)
            
            # Update UI
            self.start_btn.state(['disabled'])
            self.stop_btn.state(['!disabled'])
            self.update_status("Logging started")
            
        except Exception as e:
            self.logger.error(f"Error starting logging: {e}")
            messagebox.showerror("Error", f"Failed to start logging: {str(e)}")

    def stop_logging(self) -> None:
        """Stop the logging process"""
        try:
            self.logger.stop_logging()
            
            # Update UI
            self.stop_btn.state(['disabled'])
            self.start_btn.state(['!disabled'])
            self.update_status("Logging stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping logging: {e}")
            messagebox.showerror("Error", f"Failed to stop logging: {str(e)}")

    def update_monitor_data(self, data_point: Dict[str, Any]) -> None:
        """Update the monitor display with new data"""
        # This is handled by the _update_monitor method now
        pass

    def update_tag_combo(self) -> None:
        """Update the tag combo box with available tags"""
        try:
            if not self.tag_combo:
                return
                
            tags = set()
            for ip, tag_list in self.logger.tags_to_log.items():
                for tag in tag_list:
                    tags.add(f"{ip}_{tag}")
            
            self.tag_combo['values'] = sorted(list(tags))
            if tags and not self.tag_var.get():
                self.tag_combo.set(next(iter(tags)))
                
        except Exception as e:
            self.logger.error(f"Error updating tag combo: {e}")
            
    def _on_closing(self):
        """Handle application closing event"""
        try:
            if self.logger.running:
                if messagebox.askyesno("Quit", "Logging is active. Stop logging and quit?"):
                    self.logger.stop_logging()
                    self.quit()
                # If user selects "No", do nothing and return
            else:
                self.quit()
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            self.quit()

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
