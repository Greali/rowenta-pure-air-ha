# Rowenta Pure Air (local) for Home Assistant

**100 % local** control of the **Rowenta Intense Pure Air Connect (PU4080)** purifier after Rowenta shut down
its app and cloud. **You do not have to open or modify the appliance**: it uses its original Wi-Fi module
(Broadlink, `devtype 0x4f9a`, name `supor_air`).

> Status: **initial version (0.1.0)**. The protocol and the Wi-Fi setup wizard have been tested against a real
> PU4080. **The integration has not been tested yet on a real Home Assistant installation** with the appliance
> connected. Other models of the PU408x series may work, but are untested.

## What it provides

| Entity | Type | Notes |
|---|---|---|
| Purifier | `fan` | Power on/off and modes: silent, night, auto, turbo. |
| Panel light | `select` | On / dim / off. In night mode the appliance turns the indicators off by itself. |
| PM2.5 | `sensor` | Reading of the appliance's particle sensor. |
| Motor speed | `sensor` (diagnostic) | Depends on the mode (1 in silent/night, 2 in auto, 5 in turbo). |
| Panel locked | `binary_sensor` (diagnostic) | Read-only. |
| Filter counter 1 to 4 | `sensor` (diagnostic) | See "Known limitations". |

## Installation

**With HACS:** HACS → ⋮ → *Custom repositories* → add this repository's URL as an *Integration* → install
**Rowenta Pure Air (local)** → restart Home Assistant.

**Manually:** copy the `custom_components/rowenta_pure_air` folder into the `custom_components` folder of your
Home Assistant and restart.

## Adding the purifier

*Settings → Devices & services → Add integration → Rowenta Pure Air.* The wizard asks where the purifier is
in the process:

### A) "It is not connected to my Wi-Fi yet": 3-step guide

The purifier's Wi-Fi module only accepts your Wi-Fi password while it is in **pairing mode**, and in that mode it
broadcasts its own network. Home Assistant (usually a wired machine, which would lose its own connection if it
used Wi-Fi) cannot join it, so **one step is done from a computer with Wi-Fi**. The config flow explains it with
these screens:

1. **Purifier pairing mode.** Plug it in and hold the **Wi-Fi** button for about **3 s**, until the Wi-Fi icon
   **blinks fast**. The appliance then creates a network named like `AIR PURIFIER XXXX` (the last four characters
   differ from one appliance to another); its password is on the **label**.
2. **Connect a computer to that network** (`AIR PURIFIER XXXX`, with the password from the label). Windows may warn
   about "no Internet": that is normal and temporary.
3. **Open the wizard that sends your Wi-Fi** (see below). Your Wi-Fi must be **2.4 GHz with WPA2** (mixed WPA2/WPA3
   is fine) and, if your router has **Smart Connect / band steering** (one name for 2.4 and 5 GHz), you must
   **disable it**: in testing the purifier could not join with it enabled, and could once it was disabled.

When the wizard says "Done!", go back to Home Assistant, which **searches** for the purifier on your network and
adds it.

### Wi-Fi wizard for Windows (`RowentaWifiSetup.exe`)

A single `.exe` (English interface), **no installation and no administrator rights** (the manifest requests
`asInvoker`; it only sends one outgoing UDP packet and reads the current Wi-Fi network name). It guides you through
four steps and a final screen:

1. **Put the purifier in pairing mode**: Wi-Fi button ~3 s, icon blinking fast, plus the network name that will
   appear (with an example, `AIR PURIFIER XXXX`) and where its password is.
2. **Connect the PC to that network**: it detects the connection by itself and does not let you continue until it
   sees it (✔).
3. **Type your Wi-Fi**: name (it suggests the networks Windows already knows, **names only**) and password (it never
   reads saved passwords); the requirements are repeated here: 2.4 GHz, WPA2 and no Smart Connect.
4. **Verify**: the PC reconnects to your Wi-Fi and you press **Find my purifier**; it checks that it shows up on
   your network and displays its IP. The final screen gives the **next steps in Home Assistant** (install the
   integration, add it and reserve the IP in your router).

* **Windows SmartScreen:** since it is not signed, it may show "Windows protected your PC". Click *More info →
  Run anyway*. Some antivirus programs distrust `.exe` files built with PyInstaller: compare the **SHA-256**
  published next to the file, or use the Python script.
* **macOS / Linux, or if you prefer not to use the `.exe`:** `python3 rowenta_wifi_setup.py` (the same windowed
  wizard; `--cli` for the text version; `ROWENTA_WIFI_LANG=es` switches it to Spanish). It only uses the Python
  standard library.
* **Build the `.exe` yourself:** `powershell -ExecutionPolicy Bypass -File scripts\build_windows_exe.ps1`
  (output in `dist\RowentaWifiSetup.exe`). The script prints its SHA-256 so you can compare it with the release's.
* The tool is also available from the Home Assistant config flow itself, which serves `rowenta_wifi_setup.py` for
  download.

It sends nothing to the Internet and does not store the password (it is cleared from the form after sending). Code
in `custom_components/rowenta_pure_air/tools/rowenta_wifi_setup.py`.

### B) "It is already connected"

*Search for it* sweeps Home Assistant's subnet (about 10 s) or *enter the IP* manually. If the appliance shows up
through DHCP, Home Assistant proposes it by itself.

> **Recommendation:** reserve a fixed IP in your router (DHCP reservation) for the purifier's MAC address.

## Locked panel

With the panel locked the appliance's buttons do not respond, but commands over the network do. **Turning off over
the network clears the lock, and it cannot be set again over the network.** That is why, if you turn off while the
panel is locked, the integration **warns instead of turning off** (this can be allowed in *Options*). To unlock by
hand: hold the LOCK button for 3 s.

## Known limitations

* It is **not possible** to set the lock, program the timer or reset the filters over the network (the timer does not
  even appear in the status; the lock and the reset did not accept any tested write).
* There is **no manual speed**: on this model the speed depends on the mode.
* **Filter counters.** The status carries four 16-bit counters. After resetting the filter with the physical
  button, the first one went from 0 to 1000 and decreases with use; the other three did not move. **The order of
  the filters (pre-filter, carbon, Allergy+, NanoCaptur) and the unit are not confirmed**, which is why they are
  called "Filter counter 1 to 4" and there are no remaining-life estimates yet.
* The purifier must be on the **same local network** as Home Assistant (the scan sweeps the /24).
* PM2.5 is published as µg/m³; the exact unit is not confirmed.

## Troubleshooting

* **The Wi-Fi icon blinks slowly and turns off after sending the password:** it could not join. Check 2.4 GHz, WPA2,
  disable Smart Connect and repeat step 3. Make sure there are no accented characters or ñ in the name or password.
* **Windows disconnects from `AIR PURIFIER XXXX` by itself:** untick "Connect automatically" on your home Wi-Fi
  while the process runs. The "no Internet" warning is normal.
* **It cannot find it:** the Wi-Fi icon must be solid and Home Assistant on the same network (not an isolated
  VLAN/guest network). Use "enter the IP" as an alternative.

## Development

The protocol layer (`protocol.py`) does not depend on Home Assistant. The format of the MCU's UART frames comes from
the documentation of the project
[acvx93/rowenta-pure-air-cloud-rescue](https://github.com/acvx93/rowenta-pure-air-cloud-rescue); what this project
adds is how to send them through the original Broadlink module: command `0x6A` with the payload
`[length (2 B, little-endian)] + UART frame`, with no additional authentication.

## Disclaimer

Independent project, not affiliated with Rowenta/Groupe SEB or Broadlink. Use it at your own risk: writing
undocumented values to the board can leave it in an odd state; this integration only sends the verified writes
(power, mode and light).

## License

Code: **MIT** (`LICENSE`). Documentation and icons: **CC BY 4.0** (`LICENSE-DOCS.md`).
