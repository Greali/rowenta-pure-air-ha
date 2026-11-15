# Rowenta Pure Air (local) for Home Assistant

**100 % local** control of the **Rowenta Intense Pure Air Connect (PU4080)** purifier after Rowenta shut down
its app and cloud. **You do not have to open or modify the appliance**: it uses its original Wi-Fi module
(Broadlink, `devtype 0x4f9a`, name `supor_air`).

> Status: **early version**. Developed and tested on a real **PU4080**: the protocol, the Wi-Fi setup wizard and the
> installation through HACS into a real Home Assistant (device added, panel light changed from Home Assistant).
>
> **Other models:** the integration recognises the appliance by its Wi-Fi module (Broadlink `devtype 0x4f9a`,
> `supor_air`), not by its name, so **other Rowenta purifiers of the same "Pure Air Connect" family that use
> that module may work too**. They are untested: if you try one, please open an issue
> telling whether it worked. A device with a different module type is not accepted.

## What it provides

| Entity | Type | Notes |
|---|---|---|
| Purifier | `fan` | Power on/off and modes (presets): silent, night, auto, turbo. |
| Mode | `select` | The same four modes as a dropdown, shown in the device's controls. |
| Auto-off timer | `number` | Minutes until the purifier is turned off (0 = no timer). Runs in Home Assistant, see below. |
| Auto-off at | `sensor` | When the timer will turn the purifier off. |
| Panel light | `select` | On / dim / off. In night mode the appliance turns the indicators off by itself. |
| PM2.5 | `sensor` | Reading of the appliance's particle sensor. |
| Motor speed | `sensor` (diagnostic) | Depends on the mode (1 in silent/night, 2 in auto, 5 in turbo). |
| Panel locked | `binary_sensor` (diagnostic) | Read-only. |
| Pre-filter: time until cleaning | `sensor` (diagnostic) | Operating time left, in days by default. See "Filter life". |
| Activated carbon / Allergy+ / NanoCaptur: time left | `sensor` (diagnostic) | Operating time left until replacement. See "Filter life". |

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

A single `.exe` (Spanish or English, following your Windows display language), **no installation and no administrator rights** (the manifest requests
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
* The Home Assistant screens follow Home Assistant's own language (English and Spanish are included).
* **macOS / Linux, or if you prefer not to use the `.exe`:** `python3 rowenta_wifi_setup.py` (the same windowed
  wizard; `--cli` for the text version; `ROWENTA_WIFI_LANG=es` / `=en` forces the language). It only uses the Python
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

## Auto-off timer

The appliance's own timer cannot be programmed over the network (it is not part of the status and no write was
accepted), so the integration offers a **timer that runs inside Home Assistant**: set *Auto-off timer* to N
minutes and Home Assistant turns the purifier off when it expires. It is cancelled if you set it to 0 or the
purifier is turned off, it is **lost if Home Assistant restarts**, and it never turns the purifier off while the
panel is locked (that would clear the lock) unless you allow it in *Options*.

## Filter life

The appliance keeps four 16-bit counters that count down from 1000 **only while it is running**. The integration turns
them into **operating time left** for each filter (shown in days; each sensor also has the raw `counter` as an
attribute). The rate of each counter was measured on a real unit over about 10 hours in auto mode:

| Counter | Filter (inferred) | Drops 1 unit every | Full life (1000 units) | Manual's interval |
|---|---|---|---|---|
| 1 | Pre-filter (clean it) | ~21 min | ~14 days | clean every 2 to 4 weeks |
| 2 | Activated carbon | ~135 min | ~94 days | replace every 12 months |
| 3 | Allergy+ | ~271 min | ~188 days | replace every 2 years |
| 4 | NanoCaptur | ~135 min (always equal to counter 2) | ~94 days | replace when its color changes |

The manual's intervals assume 8 hours of use per day; the counters run faster than that (they behave as if the
appliance ran all day), so **read the numbers as "days of continuous operation left"**. Counter 3 is exactly
half as fast as counter 2, which matches the manual's 12 and 24 months, and counter 1 matches the pre-filter
being the short one; that is how the counters were assigned to filters. **It is an inference**: counters 2 and 4
behave identically, so which of them is the carbon and which the NanoCaptur is a guess (the two would only swap names).
Only counter 1 changed when the filters were reset with the physical button (from 0 to 1000); the others had not
reached 0 and were left as they were.

Resetting a filter is only possible with the physical button (hold FILTER ~3 s).

## Which option should I choose?

There are three ways to bring this purifier back after the cloud shutdown. They are not equivalent:

| | This project | [acvx93/rowenta-pure-air-cloud-rescue](https://github.com/acvx93/rowenta-pure-air-cloud-rescue) | [vpxavier/rowenta-esp32-mqtt-bridge](https://github.com/vpxavier/rowenta-esp32-mqtt-bridge) |
|---|---|---|---|
| Opening / soldering the appliance | **No** (keeps the original Wi-Fi module) | Yes: ESP32-S3 replaces the module | Yes: ESP32 on the UART plus transistors on the buttons |
| Needs Home Assistant | Yes | No (local web page, voice control) | No (built-in web interface, optional Home Assistant via MQTT) |
| On-device schedules | No (a timer that runs in Home Assistant) | Yes | See its README |
| Tested model | PU4080 | PU4080 | PU6080 (XL) |

If you are comfortable soldering and want schedules stored in the appliance itself, the ESP32 projects are the
better fit. If you would rather not open the purifier and already use Home Assistant, this project is an
alternative. Details of the other projects may have changed: check their READMEs.

**Credit:** the format of the MCU's UART frames and the command layout come from the documentation of
[acvx93/rowenta-pure-air-cloud-rescue](https://github.com/acvx93/rowenta-pure-air-cloud-rescue). What this
project adds is how to reach that UART through the original Broadlink module (command `0x6A`), how to
put it on your Wi-Fi without cloud or hardware changes, and the status/write details found by testing on a real unit.

## Known limitations

* It is **not possible** to set the lock, program the appliance's own timer or reset the filters over the network
  (the timer does not even appear in the status; the lock and the reset did not accept any tested write).
* There is **no manual speed**: on this model the speed depends on the mode.
* **Filter life** is inferred from measurements, see "Filter life".
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
