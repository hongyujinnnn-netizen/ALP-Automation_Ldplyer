import os
import subprocess
import threading
import time
from datetime import datetime

# ==================== LOCAL IMPORTS ====================
# Define our own LDPlayer class for compatibility
class LDPlayer:
    def __init__(self, ld_dir):
        self.ld_dir = ld_dir
        self.emulators = {}
        print(f"LDPlayer initialized with directory: {ld_dir}")
    
    def sort_window(self):
        print("LDPlayer: sort_window called")
        # Your implementation here

# New: import uiautomator2 (optional fallback if not installed)
try:
    import uiautomator2 as u2
    U2_AVAILABLE = True
except Exception as e:
    u2 = None
    U2_AVAILABLE = False
    print("uiautomator2 not available:", e)

class SimpleLDPlayer:
    def __init__(self, ld_path="C:\\LDPlayer\\LDPlayer9"):
        self.ld_path = ld_path
        self.console_path = os.path.join(ld_path, "dnconsole.exe")
        
    def list_emulators(self):
        try:
            result = subprocess.run([self.console_path, "list2"], 
                                  capture_output=True, text=True)
            print("Console output:", result.stdout)
            return result.stdout
        except Exception as e:
            error_str = str(e)
            if "740" in error_str or "elevation" in error_str.lower():
                print("LDPlayer console requires administrator privileges.")
            else:
                print(f"Error: {e}")
            return None

# ==================== EMULATOR CONTROL ====================
class ControlEmulator:
    def __init__(self):
        # Use raw string for Windows paths
        self.ld_dir = r"C:\LDPlayer\LDPlayer9"
        
        # Create proper emulator mapping without external module
        self.em = {}
        self.name_to_serial = {}
        self.boot_delay = 20
        self.task_duration = 900
        self.fb = "com.facebook.katana"  # Facebook package
        
        # Try to detect actual LDPlayer emulators
        self._detect_emulators()
        self._verify_adb()
        
    def _detect_emulators(self):
        """Try to detect actual LDPlayer instances"""
        try:
            # Try using dnconsole.exe to list emulators
            dnconsole_path = os.path.join(self.ld_dir, "dnconsole.exe")
            if os.path.exists(dnconsole_path):
                result = subprocess.run(
                    [dnconsole_path, "list2"], 
                    capture_output=True, 
                    text=True,
                    encoding='utf-8',
                    timeout=10
                )
                
                if result.returncode == 0:
                    # Parse the output
                    lines = result.stdout.strip().split('\n')
                    print(f"Console output lines: {len(lines)}")
                    
                    for line in lines:
                        if line.strip():
                            parts = line.split(',')
                            print(f"Parsing line: {line}, parts: {parts}")
                            
                            if len(parts) >= 2:
                                # The format appears to be: index,name,...
                                emu_index = parts[0].strip()
                                emu_name = parts[1].strip()
                                
                                try:
                                    index_num = int(emu_index)
                                    port = 5554 + (index_num * 2)
                                    serial = f"emulator-{port}"
                                except:
                                    serial = f"emulator-5554"
                                
                                # Create emulator object
                                emu_obj = type('obj', (object,), {
                                    'name': emu_name,
                                    'index': emu_index,
                                    'serial': serial
                                })()
                                
                                self.em[emu_name] = emu_obj
                                self.name_to_serial[emu_name] = serial
                                print(f"Found emulator: '{emu_name}' -> {serial}")
                    
                    if self.em:
                        print(f"Total emulators found: {len(self.em)}")
                        return
                    else:
                        print("No emulators parsed from output")
                        
        except Exception as e:
            error_str = str(e)
            if "740" in error_str or "elevation" in error_str.lower():
                print("LDPlayer console requires administrator privileges. Using test emulators instead.")
            else:
                print(f"Error detecting emulators via dnconsole: {e}")
        
        # Fallback: create test emulators if none found
        if not self.em:
            self._create_test_emulators()
    
    def _create_test_emulators(self):
        """Create test emulators for development"""
        # Based on your console output
        test_emulators = ['US - clone', 'US - 01', 'US - 02', 'US - 03', 'US - 04', 'US - 05']
        for i, name in enumerate(test_emulators):
            port = 5555 + (i * 2)
            serial = f"127.0.0.1:{port}"
            
            emu_obj = type('obj', (object,), {
                'name': name,
                'index': i,
                'serial': serial
            })()
            
            self.em[name] = emu_obj
            self.name_to_serial[name] = serial
    
    def _build_serial_mapping(self):
        """Build or refresh the serial mapping for emulators"""
        if not self.em:
            self._detect_emulators()
    
    def _verify_adb(self):
        """Verify ADB is available and working"""
        # First, check if ADB is in LDPlayer directory
        ld_adb_path = os.path.join(self.ld_dir, "adb.exe")
        
        if os.path.exists(ld_adb_path):
            # Add LDPlayer directory to PATH temporarily
            os.environ["PATH"] = self.ld_dir + os.pathsep + os.environ["PATH"]
            print(f"Added LDPlayer ADB to PATH: {self.ld_dir}")
        
        try:
            # Test ADB
            result = subprocess.run(
                ["adb", "version"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            
            if result.returncode == 0:
                print(f"ADB is working: {result.stdout.splitlines()[0]}")
                return True
            else:
                print("ADB command failed")
                return False
                
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            print(f"ADB verification failed: {e}")
            
            # Try to start ADB server
            try:
                if os.path.exists(ld_adb_path):
                    subprocess.run([ld_adb_path, "start-server"], timeout=10)
                    print("Started ADB server")
                    return True
            except Exception as e2:
                print(f"Failed to start ADB server: {e2}")
            
            return False
    
    def list_emulators(self):
        """List all detected emulators"""
        print(f"Total emulators: {len(self.em)}")
        for name, emu in self.em.items():
            serial = self.name_to_serial.get(name, "N/A")
            status = "Active" if self.is_ld_running(name) else "Inactive"
            print(f"  '{name}': {serial} ({status})")
    
    def is_ld_running(self, name):
        """Check if LDPlayer is running"""
        serial = self.name_to_serial.get(name)
        if not serial:
            print(f"No serial found for '{name}'")
            return False
            
        try:
            result = subprocess.run(
                ["adb", "devices"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            
            # Check if serial is in the output and marked as device
            for line in result.stdout.split('\n'):
                if serial in line and "device" in line:
                    return True
                    
            # Also try without the "127.0.0.1:" prefix
            if ":" in serial:
                port = serial.split(':')[1]
                for line in result.stdout.split('\n'):
                    if port in line and "device" in line:
                        return True
                        
        except Exception as e:
            print(f"Error checking if LD is running: {e}")
            
        return False
    
    def start_ld(self, name, delay_between_starts=10):
        """Start an LDPlayer instance"""
        try:
            dnconsole_path = os.path.join(self.ld_dir, "dnconsole.exe")
            
            if os.path.exists(dnconsole_path):
                # Use dnconsole to launch
                print(f"Starting LD: '{name}'")
                result = subprocess.run(
                    [dnconsole_path, "launch", "--name", name],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=30
                )
                
                if result.returncode == 0:
                    print(f"LD '{name}' started successfully")
                    time.sleep(delay_between_starts)
                    
                    # Try to connect via ADB
                    serial = self.name_to_serial.get(name)
                    if serial:
                        self._connect_adb(serial)
                    
                    return True
                else:
                    print(f"Failed to start LD '{name}': {result.stderr}")
                    return False
            else:
                print(f"dnconsole.exe not found at {dnconsole_path}")
                # Simulate start for testing
                print(f"LD '{name}' started (simulated)")
                time.sleep(5)
                return True
                
        except Exception as e:
            print(f"Error starting LD '{name}': {e}")
            return False
    
    def _connect_adb(self, serial):
        """Connect to device via ADB"""
        try:
            result = subprocess.run(
                ["adb", "connect", serial],
                capture_output=True,
                text=True,
                timeout=10
            )
            print(f"ADB connect result: {result.stdout}")
            return "connected" in result.stdout.lower()
        except Exception as e:
            print(f"Error connecting ADB: {e}")
            return False

    def _is_serial_online(self, serial):
        """Check whether a serial appears as an online adb device."""
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return False

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            if serial in line and "\tdevice" in line:
                return True
        return False

    def wait_for_ld_ready(self, name, timeout=120, poll_interval=2):
        """
        Wait until LD is adb-online and Android reports boot completed.
        Returns True when ready, False on timeout/failure.
        """
        serial = self.name_to_serial.get(name)
        if not serial:
            print(f"No serial found for '{name}'")
            return False

        deadline = time.time() + timeout
        while time.time() < deadline:
            self._connect_adb(serial)

            if not self._is_serial_online(serial):
                time.sleep(poll_interval)
                continue

            try:
                boot = subprocess.run(
                    ["adb", "-s", serial, "shell", "getprop", "sys.boot_completed"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if boot.returncode == 0 and boot.stdout.strip() == "1":
                    return True
            except Exception:
                pass

            time.sleep(poll_interval)

        print(f"Timeout waiting for LD '{name}' to be ready")
        return False
    
    def quit_ld(self, name):
        """Quit an LDPlayer instance"""
        try:
            dnconsole_path = os.path.join(self.ld_dir, "dnconsole.exe")
            
            if os.path.exists(dnconsole_path):
                result = subprocess.run(
                    [dnconsole_path, "quit", "--name", name],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=10
                )
                
                if result.returncode == 0:
                    print(f"LD '{name}' quit successfully")
                else:
                    print(f"Failed to quit LD '{name}': {result.stderr}")
            else:
                print(f"LD '{name}' quit (simulated)")
                
            return True
        except Exception as e:
            print(f"Error quitting LD '{name}': {e}")
            return False
    
    def open_facebook(self, name):
        """Open Facebook on the specified LDPlayer"""
        serial = self.name_to_serial.get(name)
        if not serial:
            print(f"No serial found for '{name}'")
            return False

        # Ensure ADB is connected
        self._connect_adb(serial)
        if not self.wait_for_ld_ready(name, timeout=90, poll_interval=2):
            print(f"LD '{name}' is not ready yet; skip opening Facebook")
            return False
        
        try:
            # First, try to start Facebook via package name
            result = subprocess.run([
                "adb", "-s", serial, "shell", "am", "start",
                "-n", "com.facebook.katana/com.facebook.katana.LoginActivity"
            ], capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                print(f"Facebook app launched on LD '{name}'")
                return True
            else:
                print(f"Failed to launch Facebook via activity: {result.stderr}")
                
                # Fallback: use monkey command
                result = subprocess.run([
                    "adb", "-s", serial, "shell", "monkey",
                    "-p", "com.facebook.katana",
                    "-c", "android.intent.category.LAUNCHER", "1"
                ], capture_output=True, text=True, timeout=15)
                
                if result.returncode == 0:
                    print(f"Facebook app launched on LD '{name}' (fallback)")
                    return True
                else:
                    print(f"Failed to launch Facebook on LD '{name}': {result.stderr}")
                    return False
                    
        except subprocess.TimeoutExpired:
            print(f"Timeout launching Facebook on LD '{name}'")
            return False
        except Exception as e:
            print(f"Error launching Facebook on LD '{name}': {e}")
            return False

    def cleanup_adb(self):
        """Clean up ADB connections when done"""
        try:
            subprocess.run(["adb", "kill-server"], timeout=10)
            print("ADB server killed")
        except Exception as e:
            print(f"Error killing ADB server: {e}")

    def set_boot_delay(self, delay):
        """Set boot delay for emulator startup"""
        self.boot_delay = delay
    
    def set_task_duration(self, duration):
        """Set task duration in minutes"""
        self.task_duration = duration * 60  # Convert to seconds
