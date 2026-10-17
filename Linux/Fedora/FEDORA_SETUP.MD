# Dell MS3320W DPI Tool for Fedora Linux

A graphical utility for changing and verifying the DPI setting of the **Dell MS3320W Wireless Mouse** through its USB receiver.

## Supported hardware

- Mouse: Dell MS3320W Wireless Mouse
- Model: MS3320W
- USB Vendor ID: `413c`
- USB Product ID: `4503`
- Tested firmware versions: **0.2.4.0** and **0.2.4.4**
- DPI presets: `1000`, `1600`, `2400`, and `4000` DPI

> [!IMPORTANT]
> Linux verification may vary by receiver firmware, HID interface, Fedora version, and the installed Python HID binding. The program supports both `hid.Device(...)` and legacy `hid.device()` APIs.

## Requirements

- Fedora Linux
- Python 3
- Tkinter
- HIDAPI
- A Dell MS3320W USB receiver
- Permission to access the receiver's `/dev/hidraw*` device

## 1. Download or clone the project

If the project is already present locally, open a terminal in its Fedora directory:

```bash
cd ~/Git/DELL_HID/Linux/Fedora
```

Confirm that the script is present:

```bash
ls -l dell_hid_gui_Linux_fedora_updated.py
```

## 2. Install Fedora dependencies

Update package metadata and install Python, Tkinter, HIDAPI, and the Fedora Python HID binding:

```bash
sudo dnf upgrade --refresh
sudo dnf install python3 python3-pip python3-tkinter hidapi python3-hidapi
```

Test the installation:

```bash
python3 -c "import tkinter; import hid; print('HID module:', hid.__file__); print('Tkinter and HID imports: OK')"
```

### Alternative: install the `hid` binding with pip

Use this only if `python3-hidapi` is unavailable or the application cannot import `hid`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install hid
```

Test the virtual environment:

```bash
python3 -c "import hid; print('HID module:', hid.__file__); print('Device API:', hasattr(hid, 'Device')); print('Legacy API:', hasattr(hid, 'device'))"
```

When using the virtual environment, activate it before every launch:

```bash
source .venv/bin/activate
```

> [!NOTE]
> Do not install several unrelated packages that all provide a module named `hid` into the same Python environment. If the wrong module is imported, verify it with `python3 -c "import hid; print(hid.__file__)"`.

## 3. Configure HID permissions with a udev rule

Without a udev rule, the receiver may be detected but opening `/dev/hidraw*` can fail with `Permission denied`.

Create the rule:

```bash
sudo tee /etc/udev/rules.d/99-dell-ms3320w.rules > /dev/null <<'EOF'
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="413c", ATTRS{idProduct}=="4503", TAG+="uaccess"
EOF
```

Reload the rules:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Disconnect and reconnect the Dell USB receiver. Logging out and back in may also be required before the new access rule is applied to the desktop session.

Verify the rule file:

```bash
cat /etc/udev/rules.d/99-dell-ms3320w.rules
```

## 4. Verify that Fedora detects the receiver

Check the USB device list:

```bash
lsusb | grep -i '413c:4503'
```

List matching HID interfaces through Python:

```bash
python3 - <<'PY'
import hid

devices = hid.enumerate(0x413C, 0x4503)
print(f"Found {len(devices)} HID collection(s)")
for index, device in enumerate(devices, start=1):
    print(f"\nCollection {index}")
    print("  path:", device.get("path"))
    print("  interface:", device.get("interface_number"))
    print("  product:", device.get("product_string"))
PY
```

At least one HID collection should be listed. Multiple collections are normal for a multifunction receiver.

## 5. Run the application

```bash
python3 dell_hid_gui_Linux_fedora_updated.py
```

If the filename is different, replace it with the actual filename.

## 6. Change the DPI

1. Connect the Dell MS3320W receiver.
2. Start the application.
3. Click **Refresh devices**.
4. Select a DPI preset.
5. Click **Apply DPI**.
6. Confirm that the application displays **Verification: PASS**.

The application sends a 32-byte HID feature report, reads the report back, and checks that the returned DPI code matches the requested preset.

