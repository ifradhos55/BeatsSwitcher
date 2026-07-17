# Beats Switcher

Beats Switcher is a lightweight menu bar utility for macOS that automates Bluetooth audio routing. It monitors system audio playback in the background and instantly connects to your preferred Bluetooth headphones the moment audio is detected.

## Features

* Automated Bluetooth Connection: Actively listens for macOS audio playback and forces an instant connection to your configured device.
* Menu Bar Interface: Runs silently in the background with a minimal, native macOS menu bar footprint.
* Configuration Management: Easily manage and save preferred Bluetooth devices without navigating system settings.
* Threaded Execution: Handles MAC address resolution and connection attempts asynchronously to prevent UI blocking.

## Requirements

* macOS 10.15 or newer
* Python 3.x
* `blueutil` (for command line Bluetooth management)
* `rumps` (for the macOS menu bar interface)
* `PyObjC` (for native macOS API interactions)

## Installation

You can install Beats Switcher directly via the terminal using the provided installation script. This method securely installs the compiled application directly to your Applications folder.

```bash
curl -sL https://beatsswitcher.store/install.sh | bash
```

Alternatively, to run the project from source:

1. Clone the repository.
2. Install the required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Ensure `blueutil` is installed on your system. If using Homebrew:
   ```bash
   brew install blueutil
   ```
4. Run the application:
   ```bash
   python3 beats_switcher.py
   ```

## Configuration

Device settings and preferences are stored locally in `config.json`. The application uses this file to identify your primary device and handle connection protocols. Do not manually edit this file unless necessary; use the menu bar interface to configure your devices.

## Architecture

* **beats_switcher.py**: Core application logic containing the audio monitoring thread, Bluetooth connection protocols, and the menu bar implementation.
* **DownloadPage/**: Contains the source code for the landing page and the script used for distribution.
* **setup.py**: Configuration file used for building the standalone macOS application bundle.

## License

Copyright 2026 Beats Switcher. All rights reserved.
