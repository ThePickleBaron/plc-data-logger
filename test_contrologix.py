#!/usr/bin/env python3
"""
ControlLogix 5*** Series Communication Test Script
This script tests basic connectivity and tag reading from a ControlLogix PLC.
"""

import sys
import time
import logging
from datetime import datetime
from pathlib import Path
import csv
from typing import List, Dict, Any
import tkinter as tk
from tkinter import ttk, messagebox
from pylogix import PLC

# Configure logging
def setup_logging():
    """Configure logging for the test script."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"contrologix_test_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

class ControlLogixTester:
    """Test class for ControlLogix PLC communication"""
    
    def __init__(self):
        """Initialize the tester"""
        self.logger = setup_logging()
        self.ip_address = None
        self.plc = None
        
        # Define test tags by equipment type
        self.test_tags = {
            "Coriolis Meters": [
                "Program:MainProgram.Coriolis1.FlowRate",  # Flow rate (REAL)
                "Program:MainProgram.Coriolis1.Density",   # Density (REAL)
                "Program:MainProgram.Coriolis1.Temperature", # Temperature (REAL)
                "Program:MainProgram.Coriolis1.TotalMass",   # Total mass (REAL)
                "Program:MainProgram.Coriolis1.Status",      # Status word (DINT)
            ],
            "Level Sensors": [
                "Program:MainProgram.Level1.Value",      # Level value (REAL)
                "Program:MainProgram.Level1.HighAlarm",  # High alarm (BOOL)
                "Program:MainProgram.Level1.LowAlarm",   # Low alarm (BOOL)
                "Program:MainProgram.Level1.Status",     # Status word (DINT)
            ],
            "Pressure Sensors": [
                "Program:MainProgram.Pressure1.Value",   # Pressure value (REAL)
                "Program:MainProgram.Pressure1.HighAlarm", # High alarm (BOOL)
                "Program:MainProgram.Pressure1.LowAlarm",  # Low alarm (BOOL)
                "Program:MainProgram.Pressure1.Status",    # Status word (DINT)
            ],
            "VFD Pumps": [
                "Program:MainProgram.Pump1.Speed",       # Speed (REAL)
                "Program:MainProgram.Pump1.Current",     # Current (REAL)
                "Program:MainProgram.Pump1.Status",      # Status word (DINT)
                "Program:MainProgram.Pump1.Fault",       # Fault word (DINT)
                "Program:MainProgram.Pump1.Running",     # Running status (BOOL)
            ],
            "Interlocks": [
                "Program:MainProgram.Interlock1.Status", # Interlock status (BOOL)
                "Program:MainProgram.Interlock1.Active", # Active status (BOOL)
                "Program:MainProgram.Interlock1.Reset",  # Reset status (BOOL)
                "Program:MainProgram.Interlock1.Fault",  # Fault status (BOOL)
            ],
            "Control Valves": [
                "Program:MainProgram.Valve1.Position",   # Position (REAL)
                "Program:MainProgram.Valve1.Output",     # Output (REAL)
                "Program:MainProgram.Valve1.Status",     # Status word (DINT)
                "Program:MainProgram.Valve1.Fault",      # Fault word (DINT)
            ],
            "On/Off Valves": [
                "Program:MainProgram.Valve2.Open",       # Open status (BOOL)
                "Program:MainProgram.Valve2.Closed",     # Closed status (BOOL)
                "Program:MainProgram.Valve2.Fault",      # Fault status (BOOL)
                "Program:MainProgram.Valve2.Status",     # Status word (DINT)
            ],
            "Solenoids": [
                "Program:MainProgram.Solenoid1.Status",  # Status (BOOL)
                "Program:MainProgram.Solenoid1.Fault",   # Fault status (BOOL)
                "Program:MainProgram.Solenoid1.Reset",   # Reset status (BOOL)
            ],
            "System Tags": [
                "Program:MainProgram.SystemTime",        # System time (DINT)
                "Program:MainProgram.SystemStatus",      # System status (DINT)
                "Program:MainProgram.AlarmStatus",       # Alarm status (DINT)
                "Program:MainProgram.CommunicationStatus", # Comm status (BOOL)
            ]
        }
        self.results = []
        
    def test_connection(self, ip: str) -> bool:
        """Test basic connection to the PLC
        
        Args:
            ip (str): IP address of the PLC
            
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.logger.info(f"Testing connection to {ip}")
            self.plc = PLC(ip)
            
            # Try to read a system tag to verify connection
            result = self.plc.Read("Program:MainProgram.SystemTime")
            if result.Status == "Success":
                self.logger.info("Connection successful")
                return True
            else:
                self.logger.error(f"Connection failed: {result.Status}")
                return False
                
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False
    
    def test_tag_read(self, tag: str) -> Dict[str, Any]:
        """Test reading a specific tag
        
        Args:
            tag (str): Tag name to read
            
        Returns:
            dict: Test results including value and status
        """
        try:
            self.logger.info(f"Testing tag read: {tag}")
            
            if not self.plc:
                raise Exception("PLC not connected")
            
            result = self.plc.Read(tag)
            
            if result.Status == "Success":
                return {
                    "tag": tag,
                    "status": "Success",
                    "value": result.Value,
                    "data_type": result.DataType
                }
            else:
                return {
                    "tag": tag,
                    "status": "Failed",
                    "value": None,
                    "data_type": None,
                    "error": result.Status
                }
                
        except Exception as e:
            self.logger.error(f"Tag read test failed for {tag}: {e}")
            return {
                "tag": tag,
                "status": "Failed",
                "value": None,
                "data_type": None,
                "error": str(e)
            }
    
    def run_tests(self, ip: str) -> List[Dict[str, Any]]:
        """Run all tests on the PLC
        
        Args:
            ip (str): IP address of the PLC
            
        Returns:
            list: List of test results
        """
        self.ip_address = ip
        self.results = []
        
        # Test connection
        connection_result = self.test_connection(ip)
        self.results.append({
            "test": "Connection",
            "status": "Success" if connection_result else "Failed",
            "timestamp": datetime.now().isoformat()
        })
        
        if not connection_result:
            return self.results
        
        # Test each equipment type
        for equipment_type, tags in self.test_tags.items():
            self.results.append({
                "test": f"=== {equipment_type} ===",
                "status": "Info",
                "timestamp": datetime.now().isoformat()
            })
            
            for tag in tags:
                result = self.test_tag_read(tag)
                result["timestamp"] = datetime.now().isoformat()
                self.results.append(result)
        
        return self.results
    
    def save_results(self):
        """Save test results to CSV file"""
        if not self.results:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs/contrologix_test_results_{timestamp}.csv"
        
        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.results[0].keys())
                writer.writeheader()
                writer.writerows(self.results)
            self.logger.info(f"Results saved to {filename}")
        except Exception as e:
            self.logger.error(f"Failed to save results: {e}")

class TestGUI(tk.Tk):
    """GUI for running ControlLogix tests"""
    
    def __init__(self):
        super().__init__()
        self.title("ControlLogix Communication Test")
        self.geometry("800x600")
        
        self.tester = ControlLogixTester()
        self.create_widgets()
        
    def create_widgets(self):
        """Create GUI widgets"""
        # IP Address Entry
        ip_frame = ttk.LabelFrame(self, text="PLC Connection")
        ip_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(ip_frame, text="IP Address:").pack(side=tk.LEFT, padx=5)
        self.ip_var = tk.StringVar(value="192.168.1.100")
        ttk.Entry(ip_frame, textvariable=self.ip_var, width=15).pack(side=tk.LEFT, padx=5)
        
        # Test Button
        ttk.Button(ip_frame, text="Run Tests", command=self.run_tests).pack(side=tk.LEFT, padx=5)
        
        # Results Treeview
        results_frame = ttk.LabelFrame(self, text="Test Results")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        columns = ("Test", "Status", "Value", "Data Type", "Timestamp")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings")
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150)
        
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Status Label
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var).pack(pady=5)
        
    def run_tests(self):
        """Run the tests and update the GUI"""
        try:
            # Clear previous results
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            # Get IP address
            ip = self.ip_var.get().strip()
            if not ip:
                messagebox.showerror("Error", "Please enter an IP address")
                return
            
            # Update status
            self.status_var.set("Running tests...")
            self.update()
            
            # Run tests
            results = self.tester.run_tests(ip)
            
            # Update treeview
            for result in results:
                values = (
                    result.get("test", result.get("tag", "Unknown")),
                    result.get("status", "Unknown"),
                    str(result.get("value", "N/A")),
                    result.get("data_type", "N/A"),
                    result.get("timestamp", "N/A")
                )
                self.tree.insert("", "end", values=values)
            
            # Save results
            self.tester.save_results()
            
            # Update status
            self.status_var.set("Tests completed")
            
            # Show summary
            success_count = sum(1 for r in results if r.get("status") == "Success")
            messagebox.showinfo("Test Summary", 
                              f"Completed {len(results)} tests\n"
                              f"Successful: {success_count}\n"
                              f"Failed: {len(results) - success_count}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Test failed: {str(e)}")
            self.status_var.set("Test failed")
        finally:
            self.update()

def main():
    """Main entry point"""
    try:
        app = TestGUI()
        app.mainloop()
    except Exception as e:
        messagebox.showerror("Fatal Error", f"Application failed to start: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 