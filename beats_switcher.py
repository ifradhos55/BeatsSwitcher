"""
BeatsSwitcher - Seamless Bluetooth auto-connect for Beats headphones on macOS.

Monitors audio output and automatically connects your Beats headphones when
media starts playing. Sits in the menu bar and provides status at a glance.
"""

__version__ = "1.0.0"

import rumps
import subprocess
import json
import os
import threading
import time
import sys
import logging
from logging.handlers import RotatingFileHandler
from enum import Enum, auto

def restart_app():
    """Helper to restart the app dynamically."""
    app_path = os.path.dirname(os.path.dirname(os.path.dirname(sys.executable)))
    if not app_path.endswith(".app"):
        app_path = os.path.expanduser("~/Applications/BeatsSwitcher.app")
    script = f'sleep 1 && open -a "{app_path}"'
    subprocess.Popen(["/bin/bash", "-c", script])
    rumps.quit_application()

# ---------------------------------------------------------------------------
# Paths & Logging
# ---------------------------------------------------------------------------
HOME_DIR = os.path.expanduser("~")
CONFIG_FILE = os.path.join(HOME_DIR, ".beats_switcher_config.json")
LOG_FILE = os.path.join(HOME_DIR, ".beats_switcher.log")

log_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8")
logging.basicConfig(
    handlers=[log_handler],
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# ---------------------------------------------------------------------------
# Connection State Machine
# ---------------------------------------------------------------------------
class ConnectionState(Enum):
    """Possible states for the Bluetooth connection lifecycle."""
    IDLE = auto()           # Waiting for audio — will connect on playback.
    CONNECTING = auto()     # Actively attempting to pair.
    CONNECTED = auto()      # Device is connected. Polling for disconnect.
    DISCONNECTED = auto()   # Was connected but lost — reconnect on next audio.
    BT_OFF = auto()         # Bluetooth radio is off — all monitoring paused.


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------
def load_config():
    """Load device configuration from disk, migrating old formats if necessary."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                
                needs_save = False
                # Migrate from single-device format to multi-device format
                if "devices" not in config:
                    logging.info("Migrating old config format to multi-device format.")
                    config = {
                        "active_device_serial": config.get("serial_number", "HQK4KJWYD2"),
                        "devices": [config]
                    }
                    needs_save = True
                    
                if needs_save:
                    save_config(config)
                    
                return config
        except Exception as e:
            logging.error(f"Error loading config: {e}")

    # Default initial configuration
    return {
        "active_device_serial": "YOUR_SERIAL_HERE",
        "devices": [
            {
                "model_name": "Beats Solo Pods",
                "model_number": "AXXXX",
                "serial_number": "YOUR_SERIAL_HERE",
                "version": "XXXXX",
                "cached_mac": "",
            }
        ]
    }


def save_config(config):
    """Persist device configuration to disk."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        logging.info("Configuration saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save config: {e}")


def get_active_device(config):
    """Return the currently active device dictionary from the config."""
    serial = config.get("active_device_serial")
    devices = config.get("devices", [])
    
    for device in devices:
        if device.get("serial_number") == serial:
            return device
            
    # Fallback to the first device if the active one isn't found
    if devices:
        return devices[0]
    return {}


# ---------------------------------------------------------------------------
# Settings dialog (native macOS — no tkinter, no subprocess)
# ---------------------------------------------------------------------------
def show_settings_window(app_instance):
    """Show a single native dialog to add a new device in a multi-line text area."""
    config = load_config()

    fields = [
        ("Model Name", "model_name"),
        ("Model Number", "model_number"),
        ("Serial Number", "serial_number"),
        ("Version", "version"),
    ]

    default_text = "Model Name: \nModel Number: \nSerial Number: \nVersion: \n"

    w = rumps.Window(
        message="Add a new Beats device below.\nKeep the format  Label: Value  on each line.",
        title="Add New Device",
        default_text=default_text,
        ok="Save",
        cancel="Cancel",
        dimensions=(320, 120),
    )
    response = w.run()

    if not response.clicked:
        return

    new_device = {"cached_mac": ""}
    for line in response.text.strip().splitlines():
        if ":" not in line:
            continue
        label_part, _, value_part = line.partition(":")
        label_part = label_part.strip()
        value_part = value_part.strip()
        for label, key in fields:
            if label_part.lower() == label.lower() and value_part:
                new_device[key] = value_part

    if new_device.get("serial_number") and new_device.get("model_name"):
        devices = config.get("devices", [])
        
        # Update if it already exists, otherwise append
        existing = next((d for d in devices if d.get("serial_number") == new_device["serial_number"]), None)
        if existing:
            existing.update(new_device)
            existing["cached_mac"] = ""
        else:
            devices.append(new_device)
            
        config["active_device_serial"] = new_device["serial_number"]
        config["devices"] = devices
        
        save_config(config)
        
        logging.info("New device added. Restarting app...")
        restart_app()


# ---------------------------------------------------------------------------
# Bluetooth helpers
# ---------------------------------------------------------------------------
def is_bluetooth_on():
    """Check whether the Bluetooth radio is powered on using IOBluetoothHostController."""
    try:
        import objc
        from Foundation import NSBundle

        NSBundle.bundleWithPath_(
            "/System/Library/Frameworks/IOBluetooth.framework"
        ).load()
        IOBluetoothHostController = objc.lookUpClass("IOBluetoothHostController")
        controller = IOBluetoothHostController.defaultController()
        return controller is not None and controller.powerState() == 1
    except Exception as e:
        logging.error(f"Bluetooth state check failed: {e}")
        return False


def get_device_mac(serial_number, model_name):
    """Resolve the Bluetooth MAC address for a device by serial number or model name."""
    try:
        logging.info("Searching for MAC address using system_profiler…")
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPBluetoothDataType"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        current_address = None

        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("Address:"):
                current_address = stripped.replace("Address:", "").strip()
            if stripped.startswith("Serial Number:"):
                sn = stripped.replace("Serial Number:", "").strip()
                if serial_number.lower() in sn.lower() and current_address:
                    logging.info(f"Found via system_profiler: {current_address}")
                    return current_address

        logging.warning("system_profiler lookup missed. Falling back to IOBluetooth API…")
        import objc
        from Foundation import NSBundle

        NSBundle.bundleWithPath_(
            "/System/Library/Frameworks/IOBluetooth.framework"
        ).load()
        IOBluetoothDevice = objc.lookUpClass("IOBluetoothDevice")

        paired_devices = IOBluetoothDevice.pairedDevices()
        if paired_devices:
            for device in paired_devices:
                if device.name() and model_name.lower() in device.name().lower():
                    mac = device.addressString()
                    logging.info(f"Found via IOBluetooth API: {mac}")
                    return mac

    except Exception as e:
        logging.error(f"Error resolving MAC address: {e}")

    return None


def get_blueutil_path():
    """Find the path to the blueutil executable if installed."""
    for path in ["/opt/homebrew/bin/blueutil", "/usr/local/bin/blueutil"]:
        if os.path.exists(path):
            return path
    try:
        result = subprocess.run(["which", "blueutil"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None

import os
import subprocess

SWIFT_CHECKER = os.path.join(HOME_DIR, ".beats_switcher_audio_check")

def compile_audio_checker():
    if os.path.exists(SWIFT_CHECKER):
        return True
    
    swift_code = """
import Foundation
import CoreAudio

func isAudioPlaying() -> Bool {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyDefaultOutputDevice,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    
    var deviceID: AudioDeviceID = kAudioObjectUnknown
    var dataSize: UInt32 = UInt32(MemoryLayout<AudioDeviceID>.size)
    
    var status = AudioObjectGetPropertyData(
        AudioObjectID(kAudioObjectSystemObject),
        &address,
        0,
        nil,
        &dataSize,
        &deviceID
    )
    
    if status != noErr { return false }
    
    address.mSelector = kAudioDevicePropertyDeviceIsRunningSomewhere
    address.mScope = kAudioObjectPropertyScopeGlobal
    
    var isRunning: UInt32 = 0
    dataSize = UInt32(MemoryLayout<UInt32>.size)
    
    status = AudioObjectGetPropertyData(
        deviceID,
        &address,
        0,
        nil,
        &dataSize,
        &isRunning
    )
    
    if status != noErr { return false }
    return isRunning != 0
}

if isAudioPlaying() {
    print("PLAYING")
} else {
    print("SILENT")
}
"""
    swift_path = "/tmp/beats_audio_check.swift"
    try:
        with open(swift_path, "w") as f:
            f.write(swift_code)
        
        logging.info("Compiling native CoreAudio Swift checker...")
        subprocess.run(["/usr/bin/swiftc", swift_path, "-o", SWIFT_CHECKER], check=True)
        return True
    except Exception as e:
        logging.error(f"Failed to compile Swift audio checker: {e}")
        return False

compile_audio_checker()

def is_audio_playing():
    """Detect whether any audio is actively playing on the system using CoreAudio."""
    try:
        if not os.path.exists(SWIFT_CHECKER):
            compile_audio_checker()
            
        if os.path.exists(SWIFT_CHECKER):
            result = subprocess.run(
                [SWIFT_CHECKER],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return "PLAYING" in result.stdout
    except Exception as e:
        logging.error(f"Audio check failed: {e}")
        
    # Fallback to pmset if swift fails
    try:
        result = subprocess.run(
            ["/usr/bin/pmset", "-g", "assertions"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return (
            "coreaudiod" in result.stdout
            and "PreventUserIdleSystemSleep" in result.stdout
        )
    except:
        return False


# ---------------------------------------------------------------------------
# Menu bar status helpers
# ---------------------------------------------------------------------------
_STATUS_LABELS = {
    ConnectionState.IDLE: "Idle — waiting for audio",
    ConnectionState.CONNECTING: "Connecting…",
    ConnectionState.CONNECTED: "Connected",
    ConnectionState.DISCONNECTED: "Disconnected",
    ConnectionState.BT_OFF: "Bluetooth is off",
}

_MENU_TITLES = {
    ConnectionState.IDLE: "🎧",
    ConnectionState.CONNECTING: "🎧 ⋯",
    ConnectionState.CONNECTED: "🎧",
    ConnectionState.DISCONNECTED: "🎧",
    ConnectionState.BT_OFF: "🎧 ✕",
}


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
class BeatsSwitcherApp(rumps.App):
    """macOS menu-bar application that auto-connects Beats headphones on audio playback."""

    POLL_INTERVAL = {
        ConnectionState.IDLE: 0.5,
        ConnectionState.CONNECTING: 1.0,
        ConnectionState.CONNECTED: 3.0,
        ConnectionState.DISCONNECTED: 0.5,
        ConnectionState.BT_OFF: 5.0,
    }

    MAX_RETRIES = 3
    RETRY_BACKOFF = [0, 5, 15]

    def __init__(self):
        super(BeatsSwitcherApp, self).__init__(
            "🎧", icon="menubar_iconTemplate.png", template=True
        )

        # --- State ---
        self.config = load_config()
        self.active_device = get_active_device(self.config)
        self.mac_address = self.active_device.get("cached_mac", "")
        self.state = ConnectionState.IDLE
        self.is_active = True
        self.last_audio_state = False
        self.retry_count = 0
        self._bt_off_logged = False

        # --- Menu ---
        self.status_item = rumps.MenuItem("Status: Idle — waiting for audio")
        self.status_item.set_callback(None)  # non-clickable
        
        # Build "Saved Devices" Submenu
        self.saved_devices_menu = rumps.MenuItem("Saved Devices")
        
        active_serial = self.config.get("active_device_serial")
        for device in self.config.get("devices", []):
            name = device.get("model_name", "Unknown")
            serial = device.get("serial_number", "Unknown")
            is_active = (serial == active_serial)
            title = f"{'✓ ' if is_active else ''}{name} ({serial})"
            
            item = rumps.MenuItem(title)
            # Create a closure to capture the serial number for the callback
            def create_switch_callback(s):
                return lambda sender: self.switch_device(s)
            
            item.set_callback(create_switch_callback(serial))
            self.saved_devices_menu.add(item)
            
        self.saved_devices_menu.add(rumps.separator)
        
        add_new_item = rumps.MenuItem("Add New Device...")
        add_new_item.set_callback(self.on_settings)
        self.saved_devices_menu.add(add_new_item)
        
        scan_item = rumps.MenuItem("Scan for Audio Devices...")
        scan_item.set_callback(self.on_scan_devices)
        self.saved_devices_menu.add(scan_item)
        
        remove_item = rumps.MenuItem("Remove Saved Device...")
        remove_item.set_callback(self.on_remove_device)
        self.saved_devices_menu.add(remove_item)
        
        self.menu = [
            self.status_item,
            None,
            self.saved_devices_menu,
            "Toggle Auto-Connect",
            None,
            f"About BeatsSwitcher v{__version__}",
        ]

        # --- IOBluetooth ---
        import objc
        from Foundation import NSBundle

        NSBundle.bundleWithPath_(
            "/System/Library/Frameworks/IOBluetooth.framework"
        ).load()
        self.IOBluetoothDevice = objc.lookUpClass("IOBluetoothDevice")

        logging.info(f"BeatsSwitcher v{__version__} started.")

        if not self.mac_address:
            threading.Thread(target=self.update_mac_address, daemon=True).start()
        else:
            logging.info(f"Using cached MAC address: {self.mac_address}")

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------
    def switch_device(self, serial):
        """Switch the active device, disconnect the old one if connected, and restart the app."""
        if serial == self.config.get("active_device_serial"):
            return # Already active
            
        logging.info(f"Switching active device to {serial}.")
        
        # Disconnect the current device if it's connected
        if self.mac_address:
            try:
                current_device = self.IOBluetoothDevice.deviceWithAddressString_(self.mac_address)
                if current_device and current_device.isConnected():
                    logging.info(f"Disconnecting previous device ({self.mac_address}) before switching...")
                    current_device.closeConnection()
                    # Brief pause to ensure the disconnection is registered by macOS
                    time.sleep(1.0)
            except Exception as e:
                logging.error(f"Failed to cleanly disconnect previous device: {e}")
                
        self.config["active_device_serial"] = serial
        save_config(self.config)
        
        logging.info("Restarting app...")
        restart_app()

    def on_settings(self, _):
        """Open the device-settings dialog."""
        show_settings_window(self)

    def on_scan_devices(self, _):
        """Scan for connected/paired audio devices using system_profiler and let the user select one."""
        try:
            # Let the user know it might take a second.
            rumps.notification("BeatsSwitcher", "Scanning...", "Looking for paired audio devices...")
            import json
            result = subprocess.run(
                ["/usr/sbin/system_profiler", "SPBluetoothDataType", "-json"],
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
            data = json.loads(result.stdout)
            
            audio_devices = []
            
            for bt_data in data.get("SPBluetoothDataType", []):
                for status_group in ["device_connected", "device_not_connected"]:
                    for dev_dict in bt_data.get(status_group, []):
                        for dev_name, attrs in dev_dict.items():
                            minor_type = attrs.get("device_minorType", "")
                            if minor_type in ["Headphones", "Headset", "Speaker"] or "device_serialNumber" in attrs:
                                audio_devices.append({
                                    "name": dev_name,
                                    "serial": attrs.get("device_serialNumber", ""),
                                    "mac": attrs.get("device_address", ""),
                                })
            
            if not audio_devices:
                rumps.alert("BeatsSwitcher", "No Bluetooth audio devices found on this system.")
                return
                
            from AppKit import NSAlert, NSPopUpButton, NSMakeRect, NSApplication
            
            alert = NSAlert.alloc().init()
            alert.setMessageText_("Scan Results")
            alert.setInformativeText_("Select a compatible audio device to add to BeatsSwitcher:")
            alert.addButtonWithTitle_("Add Device")
            alert.addButtonWithTitle_("Cancel")
            
            popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 300, 24), False)
            options = []
            for d in audio_devices:
                label = d['name']
                if d['serial']:
                    label += f" (Serial: {d['serial']})"
                options.append(label)
                
            popup.addItemsWithTitles_(options)
            alert.setAccessoryView_(popup)
            
            # Bring app to front
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            response = alert.runModal()
            
            if response == 1000: # First button clicked
                idx = popup.indexOfSelectedItem()
                if 0 <= idx < len(audio_devices):
                    selected = audio_devices[idx]
                    
                    new_device = {
                        "model_name": selected["name"],
                        "serial_number": selected["serial"] if selected["serial"] else f"mac-{selected['mac']}",
                        "cached_mac": selected["mac"]
                    }
                    
                    self.config.setdefault("devices", []).append(new_device)
                    self.config["active_device_serial"] = new_device["serial_number"]
                    save_config(self.config)
                    restart_app()
                    
        except Exception as e:
            logging.error(f"Scan failed: {e}")
            rumps.alert("BeatsSwitcher", "Failed to scan for devices.")

    def on_remove_device(self, _):
        """Prompt user to remove a saved device."""
        devices = self.config.get("devices", [])
        if not devices:
            rumps.alert("BeatsSwitcher", "No devices saved.")
            return
            
        from AppKit import NSAlert, NSPopUpButton, NSMakeRect, NSApplication
        
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Remove Saved Device")
        alert.setInformativeText_("Select the device you want to remove:")
        alert.addButtonWithTitle_("Remove Device")
        alert.addButtonWithTitle_("Cancel")
        
        popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 300, 24), False)
        options = []
        for d in devices:
            options.append(f"{d.get('model_name', 'Unknown')} ({d.get('serial_number', 'Unknown')})")
            
        popup.addItemsWithTitles_(options)
        alert.setAccessoryView_(popup)
        
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        response = alert.runModal()
        
        if response == 1000:
            idx = popup.indexOfSelectedItem()
            if 0 <= idx < len(devices):
                removed = devices.pop(idx)
                self.config["devices"] = devices
                
                if removed.get("serial_number") == self.config.get("active_device_serial"):
                    if devices:
                        self.config["active_device_serial"] = devices[0]["serial_number"]
                    else:
                        self.config["active_device_serial"] = ""
                        
                save_config(self.config)
                restart_app()

    @rumps.clicked("Toggle Auto-Connect")
    def on_toggle_active(self, sender):
        """Enable or disable automatic connection."""
        self.is_active = not self.is_active
        sender.state = self.is_active
        status = "Enabled" if self.is_active else "Disabled"
        msg = (
            "Will connect when audio plays"
            if self.is_active
            else "Will not automatically connect"
        )
        rumps.notification("Beats Switcher", f"Auto-Connect {status}", msg)

    @rumps.clicked(f"About BeatsSwitcher v{__version__}")
    def on_about(self, _):
        """Show version and copyright info."""
        rumps.alert(
            title="BeatsSwitcher",
            message=(
                f"Version {__version__}\n\n"
                "Seamless Bluetooth auto-connect\nfor Beats headphones on macOS.\n"
            ),
        )

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def _set_state(self, new_state):
        """Transition to a new connection state, updating the UI."""
        if new_state == self.state:
            return
        old = self.state
        self.state = new_state
        logging.info(f"State: {old.name} → {new_state.name}")

        self.title = _MENU_TITLES.get(new_state, "🎧")

        device_name = self.active_device.get("model_name", "Beats")
        if new_state == ConnectionState.CONNECTED:
            self.status_item.title = f"Status: Connected to {device_name}"
        else:
            self.status_item.title = f"Status: {_STATUS_LABELS.get(new_state, '—')}"

    # ------------------------------------------------------------------
    # MAC address resolution
    # ------------------------------------------------------------------
    def update_mac_address(self):
        """Re-resolve the target device MAC address from config."""
        self.config = load_config()
        self.active_device = get_active_device(self.config)
        new_mac = get_device_mac(
            self.active_device.get("serial_number"), self.active_device.get("model_name")
        )
        if new_mac:
            self.mac_address = new_mac
            self.active_device["cached_mac"] = new_mac
            
            # Update the specific device in the devices list
            for device in self.config.get("devices", []):
                if device.get("serial_number") == self.active_device.get("serial_number"):
                    device["cached_mac"] = new_mac
                    
            save_config(self.config)
            logging.info(f"MAC address resolved and cached: {self.mac_address}")
        else:
            logging.warning("Failed to resolve target MAC address.")

    # ------------------------------------------------------------------
    # Core polling loop
    # ------------------------------------------------------------------
    @rumps.timer(0.5)
    def poll(self, _):
        """Main polling loop — adapts behaviour based on connection state."""
        if not is_bluetooth_on():
            if self.state != ConnectionState.BT_OFF:
                self._set_state(ConnectionState.BT_OFF)
                self._bt_off_logged = False
            if not self._bt_off_logged:
                logging.info("Bluetooth is off — monitoring paused.")
                self._bt_off_logged = True
            return

        if self.state == ConnectionState.BT_OFF:
            logging.info("Bluetooth is back on — resuming monitoring.")
            self._bt_off_logged = False
            self._set_state(ConnectionState.IDLE)

        if not self.is_active:
            return

        if self.state == ConnectionState.CONNECTING:
            return

        current_audio = is_audio_playing()

        if current_audio and not self.last_audio_state:
            logging.info("Audio started playing. Checking connection…")
            self._handle_audio_started()
        elif not current_audio and self.last_audio_state:
            logging.info("Audio stopped playing. Remaining connected to Mac.")

        self.last_audio_state = current_audio
        
        if self.state == ConnectionState.CONNECTED:
            self._check_still_connected()
            return

    def _handle_audio_started(self):
        """Handle an audio-started event, resolving the MAC address if necessary before connecting."""
        if not self.mac_address:
            logging.info("MAC address missing. Resolving in background before connecting...")
            def resolve_and_connect():
                self.update_mac_address()
                if self.mac_address:
                    self._check_and_initiate_connection()
                else:
                    logging.warning("Could not resolve MAC address. Cannot connect.")
            threading.Thread(target=resolve_and_connect, daemon=True).start()
        else:
            self._check_and_initiate_connection()

    def _check_and_initiate_connection(self):
        """Evaluate the connection state of the target MAC and force connect."""
        device = self.IOBluetoothDevice.deviceWithAddressString_(self.mac_address)
        if device:
            # Always forcefully initiate a connection, even if macOS claims it's connected.
            # When Beats switch to an iPhone, macOS sometimes still reports them as "connected" 
            # internally, which breaks the switching logic if we trust it.
            logging.info("Forcing connection attempt to ensure audio routing...")
            self.retry_count = 0
            self._initiate_connection()
        else:
            logging.warning("Could not create device handle — invalid MAC?")

    # ------------------------------------------------------------------
    # Connection check (while in CONNECTED state)
    # ------------------------------------------------------------------
    def _check_still_connected(self):
        """Verify the device is still connected; transition to DISCONNECTED if not."""
        try:
            device = self.IOBluetoothDevice.deviceWithAddressString_(self.mac_address)
            if device and not device.isConnected():
                logging.info("Device disconnected (likely switched to another device).")
                self._set_state(ConnectionState.DISCONNECTED)
                self.last_audio_state = False
        except Exception as e:
            logging.error(f"Error checking connection state: {e}")

    # ------------------------------------------------------------------
    # Connection attempt
    # ------------------------------------------------------------------
    def _initiate_connection(self):
        """Start a background thread to connect to the Beats device."""
        if self.state == ConnectionState.CONNECTING:
            return

        self._set_state(ConnectionState.CONNECTING)

        def connect_worker():
            start = time.time()
            success = False

            device = self.IOBluetoothDevice.deviceWithAddressString_(self.mac_address)
            if device:
                logging.info(f"Attempting to connect to {self.mac_address}…")

                # 1. Aggressively steal connection using blueutil if available
                blueutil_path = get_blueutil_path()
                if blueutil_path:
                    try:
                        logging.info("Using blueutil to force connection stealing...")
                        subprocess.run([blueutil_path, "--connect", self.mac_address], timeout=10)
                        time.sleep(2)  # Give macOS a moment to register the connection state
                        if device.isConnected():
                            success = True
                            logging.info("Successfully connected via blueutil!")
                    except Exception as e:
                        logging.warning(f"blueutil connection attempt failed or timed out: {e}")

                # 2. Standard fallback loop using IOBluetooth
                while not success and time.time() - start < 20:
                    if device.isConnected():
                        success = True
                        break

                    device.openConnection()
                    time.sleep(1.5)

                    if device.isConnected():
                        success = True
                        logging.info("Successfully connected via IOBluetooth!")
                        break

            if success:
                self._set_state(ConnectionState.CONNECTED)
                self.retry_count = 0
            else:
                elapsed = time.time() - start
                logging.warning(f"Connection failed after {elapsed:.1f}s.")
                self._handle_failed_connection()

        threading.Thread(target=connect_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Retry logic with exponential backoff
    # ------------------------------------------------------------------
    def _handle_failed_connection(self):
        """Handle a failed connection attempt with exponential backoff."""
        if not is_bluetooth_on():
            self._set_state(ConnectionState.BT_OFF)
            return

        if self.retry_count >= self.MAX_RETRIES:
            logging.info(
                f"Exhausted {self.MAX_RETRIES} retries. "
                "Will try again on next audio event."
            )
            self.retry_count = 0
            self._set_state(ConnectionState.DISCONNECTED)
            self.last_audio_state = False
            return

        backoff = self.RETRY_BACKOFF[min(self.retry_count, len(self.RETRY_BACKOFF) - 1)]
        self.retry_count += 1

        logging.info(
            f"Automatically retrying {self.retry_count}/{self.MAX_RETRIES}"
            + (f" after {backoff}s backoff." if backoff else ".")
        )
        
        # Reset last_audio_state to False so that if the user pauses and plays audio again
        # during or after the retry process, it triggers a new connection attempt
        self.last_audio_state = False

        if backoff:
            time.sleep(backoff)
            
        self._set_state(ConnectionState.IDLE)
        self._initiate_connection()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = BeatsSwitcherApp()
    app.menu["Toggle Auto-Connect"].state = True
    app.run()
