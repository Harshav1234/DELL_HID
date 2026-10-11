# Dell MS3320W Wireless Mouse DPI Adjuster

A Python Tkinter GUI application for changing and verifying DPI settings on the Dell MS3320W Wireless Mouse using HID feature reports.

This tool communicates directly with the Dell USB receiver through HIDAPI and allows users to:

- Detect Dell MS3320W receiver automatically
- Display current USB port location
- Apply predefined DPI presets
- Verify DPI settings using GET_REPORT responses
- Display raw 32-byte HID feature reports
- Monitor device activity through an integrated log window

## Supported Devices

### Mouse
- Dell MS3320W Wireless Mouse

### Receiver
- Vendor ID (VID): `0x413C`
- Product ID (PID): `0x4503`

### Supported Firmware Versions

**0.2.4.0**

**0.2.4.4**

> Other firmware versions have not been verified.

---

# Features

## Device Detection

- Automatically finds Dell receiver connected to any USB port.
- Enumerates all available HID collections.
- Displays USB hub and port information using Windows PnP APIs.

## DPI Presets

Supported DPI values:

| DPI Setting | HID Code |
|------------|----------|
| 1000 DPI | 0x01 |
| 1600 DPI | 0x02 |
| 2400 DPI | 0x03 |
| 4000 DPI | 0x04 |

## HID Verification

After applying a DPI preset the application:

1. Sends a SET_REPORT request
2. Reads back data using GET_REPORT
3. Validates:
   - Report length
   - Report ID
   - Command byte
   - DPI code
   - Report padding
4. Displays PASS or FAIL status

## USB Port Tracking

The application displays:

- Current USB hub location
- Current USB port
- Device location path

Example:

```

Port\_#0002.Hub\_#0004 |
PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(2)

```

---

# Requirements

## Operating System

- Windows 10
- Windows 11

## Python

Python 3.10 or newer recommended.

---

# Python Dependencies

Install required packages:

```bash
pip install hidapi
```

or

```bash
pip install hid
```

Depending on your HIDAPI distribution.

---

# Installation

## 1. Clone or Download

Save the script as:

```text
dell_ms3320w_dpi_gui.py
```

---

## 2. Install Dependencies

```bash
pip install hidapi
```

---

## 3. Run

```bash
python dell_ms3320w_dpi_gui.py
```

---

# Usage

## Step 1

Connect the Dell MS3320W receiver.

The application should detect:

```text
Dell MS3320W Wireless Mouse
VID=0x413C
PID=0x4503
```

---

## Step 2

Select a DPI preset:

```text
1000 DPI
1600 DPI
2400 DPI
4000 DPI
```

---

## Step 3

Click:

```text
Load Preset
```

This generates the HID feature report.

---

## Step 4

Click:

```text
Apply DPI
```

The application will:

- Send SET_REPORT
- Read GET_REPORT
- Verify response
- Display current DPI

---

# Feature Report Format

Report Length:

```text
32 Bytes
```

Report ID:

```text
0x08
```

Example 1600 DPI Report:

```text
08 11 01 02
00 00 00 00
00 00 00 00
00 00 00 00
00 00 00 00
00 00 00 00
00 00 00 00
00 00 00 00
```

Meaning:

| Byte | Value |
|--------|--------|
| 0 | 0x08 (Report ID) |
| 1 | 0x11 (Command) |
| 2 | 0x01 (Parameter) |
| 3 | DPI Code |
| 4-31 | Zero Padding |

---

# Verification Logic

A response is considered valid if:

- Length equals 32 bytes
- Report ID equals 0x08
- Command equals 0x11
- Parameter equals 0x01
- DPI code is between 0x01 and 0x04
- Remaining bytes are zero

Example:

```text
Overall Verification: PASS
```

---

# Application Screens

The GUI contains:

### Device Information

Displays:

- Mouse Name
- Model
- VID
- PID
- USB Port Location

### DPI Presets

Allows users to select:

- 1000 DPI
- 1600 DPI
- 2400 DPI
- 4000 DPI

### Feature Report Viewer

Displays raw outgoing HID report.

### Response Viewer

Displays device responses and verification results.

### Activity Log

Records:

- Device detection
- USB port changes
- DPI updates
- Verification results
- Errors

---

# Troubleshooting

## Receiver Not Found

Verify:

- Receiver is connected
- Mouse is powered on
- Driver is installed
- VID and PID match

Click:

```text
Refresh Devices
```

---

## HID Permission Errors

Run:

```bash
python
```

from an elevated Command Prompt:

```text
Run as Administrator
```

---

## GET_REPORT Failure

Possible causes:

- Receiver firmware does not support standalone GET_REPORT
- Device not fully initialized
- Unsupported firmware version

---

## Verification Fail

Verify that:

- Firmware is supported
- Correct receiver is connected
- Mouse is paired to receiver

---

# Technical Details

## Receiver

| Item | Value |
|--------|--------|
| VID | 0x413C |
| PID | 0x4503 |
| Report ID | 0x08 |
| Report Length | 32 |

## DPI Code Map

| DPI | Code |
|------|------|
| 1000 | 0x01 |
| 1600 | 0x02 |
| 2400 | 0x03 |
| 4000 | 0x04 |

---

# Disclaimer

This project is intended for educational and research purposes.

Use at your own risk. Modifying HID reports may behave differently across firmware revisions and operating system versions.

---

# Author

Dell MS3320W DPI Adjustment Utility

Compatible with:

**Dell MS3320W Wireless Mouse**

**Firmware 0.2.4.0**

**Firmware 0.2.4.4**