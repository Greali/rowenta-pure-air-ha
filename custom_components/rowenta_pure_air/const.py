"""Constants of the Rowenta Pure Air integration."""

DOMAIN = "rowenta_pure_air"

DEFAULT_SCAN_INTERVAL = 30  # seconds
CONF_ALLOW_OFF_LOCKED = "allow_off_when_locked"

# The Wi-Fi setup tool is served by Home Assistant itself.
STATIC_URL = "/rowenta_pure_air_static"
TOOL_FILENAME = "rowenta_wifi_setup.py"
TOOL_URL = f"{STATIC_URL}/{TOOL_FILENAME}"
# Download of the Windows executable (published in the repository's releases).
EXE_NAME = "RowentaWifiSetup.exe"
RELEASES_URL = "https://github.com/Greali/rowenta-pure-air-ha/releases/latest"
