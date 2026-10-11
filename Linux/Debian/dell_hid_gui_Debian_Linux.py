import queue
import threading
import time
import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import hid


# Dell MS3320W receiver and feature-report configuration
MOUSE_MANUFACTURER = "Dell"
MOUSE_MODEL = "MS3320W"
MOUSE_DISPLAY_NAME = f"{MOUSE_MANUFACTURER} {MOUSE_MODEL} Wireless Mouse"
SUPPORTED_FIRMWARE = "0.2.4.0 and 0.2.4.4"

VID = 0x413C
PID = 0x4503
REPORT_ID = 0x08
REPORT_LENGTH = 32
READBACK_DELAY = 0.05

# Confirmed from captured SET_REPORT and GET_REPORT transactions.
DPI_PRESETS = {
    "1000 DPI": 0x01,
    "1600 DPI": 0x02,
    "2400 DPI": 0x03,
    "4000 DPI": 0x04,
}
DPI_BY_CODE = {code: name for name, code in DPI_PRESETS.items()}


def safe_int(value):
    return value if isinstance(value, int) else 0


def read_sysfs_text(path):
    """Read one Linux sysfs attribute and return an empty string on failure."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, UnicodeError):
        return ""


def find_usb_parent(start_path):
    """Walk upward from a sysfs node until a USB device node is found."""
    try:
        current = Path(start_path).resolve()
    except OSError:
        return None

    for candidate in (current, *current.parents):
        vendor = read_sysfs_text(candidate / "idVendor").lower()
        product = read_sysfs_text(candidate / "idProduct").lower()
        if vendor == f"{VID:04x}" and product == f"{PID:04x}":
            return candidate
    return None


def get_usb_port_location(device_info=None):
    """Return the Linux USB topology location for the Dell receiver."""
    candidate_names = []

    if device_info:
        raw_path = device_info.get("path")
        if isinstance(raw_path, bytes):
            raw_path = raw_path.decode("utf-8", errors="replace")
        if raw_path:
            base_name = os.path.basename(str(raw_path))
            if base_name.startswith("hidraw"):
                candidate_names.append(base_name)

    sysfs_root = Path("/sys/class/hidraw")
    try:
        available = sorted(sysfs_root.glob("hidraw*"))
    except OSError:
        available = []

    ordered = []
    for name in candidate_names:
        node = sysfs_root / name
        if node.exists():
            ordered.append(node)
    ordered.extend(node for node in available if node not in ordered)

    for hidraw_node in ordered:
        usb_parent = find_usb_parent(hidraw_node / "device")
        if usb_parent is None:
            continue

        bus = read_sysfs_text(usb_parent / "busnum") or "?"
        device_number = read_sysfs_text(usb_parent / "devnum") or "?"
        port_path = read_sysfs_text(usb_parent / "devpath") or usb_parent.name
        product_name = read_sysfs_text(usb_parent / "product")

        location = f"USB bus {bus}, device {device_number}, port path {port_path}"
        if product_name:
            location += f" | {product_name}"
        return location

    return "USB location unavailable"


def format_hex(data):
    raw = bytes(data)
    return "\n".join(
        f"{offset:04X}: " + " ".join(f"{byte:02X}" for byte in raw[offset:offset + 8])
        for offset in range(0, len(raw), 8)
    )


def build_dpi_report(dpi_code):
    if dpi_code not in DPI_BY_CODE:
        raise ValueError(f"Unsupported DPI code: 0x{dpi_code:02X}")
    return bytes([REPORT_ID, 0x11, 0x01, dpi_code] + [0x00] * 28)


def normalize_feature_response(response):
    """Normalize common HIDAPI feature-report return layouts to 32 bytes."""
    data = bytes(response)

    if len(data) == REPORT_LENGTH and data[0] == REPORT_ID:
        return data

    if len(data) == REPORT_LENGTH + 1 and data[0] == 0x00 and data[1] == REPORT_ID:
        return data[1:]

    if len(data) == REPORT_LENGTH + 1 and data[0] == REPORT_ID:
        return data[:REPORT_LENGTH]

    return data


def verify_dpi_response(response, expected_code=None):
    response = normalize_feature_response(response)
    result = {
        "valid_length": len(response) == REPORT_LENGTH,
        "valid_report_id": len(response) >= 1 and response[0] == REPORT_ID,
        "valid_command": len(response) >= 2 and response[1] == 0x11,
        "valid_fixed_parameter": len(response) >= 3 and response[2] == 0x01,
        "dpi_code": response[3] if len(response) >= 4 else None,
        "dpi_name": None,
        "known_dpi": False,
        "matches_expected": None,
        "padding_is_zero": False,
    }

    code = result["dpi_code"]
    if code in DPI_BY_CODE:
        result["known_dpi"] = True
        result["dpi_name"] = DPI_BY_CODE[code]

    if expected_code is not None and code is not None:
        result["matches_expected"] = code == expected_code

    if len(response) >= 4:
        result["padding_is_zero"] = all(value == 0 for value in response[4:])

    result["fully_valid"] = (
        result["valid_length"]
        and result["valid_report_id"]
        and result["valid_command"]
        and result["valid_fixed_parameter"]
        and result["known_dpi"]
        and result["padding_is_zero"]
        and result["matches_expected"] is not False
    )
    return result


def is_valid_dpi_response(response):
    data = normalize_feature_response(response)
    return (
        len(data) == REPORT_LENGTH
        and data[0] == REPORT_ID
        and data[1] == 0x11
        and data[2] == 0x01
        and data[3] in DPI_BY_CODE
    )


class DellDpiGui:
    def __init__(self, root):
        self.root = root
        self.root.title("Dell MS3320W Wireless Mouse DPI Tool for Linux")
        self.root.geometry("1040x800")
        self.root.minsize(880, 680)

        self.devices = []
        self.messages = queue.Queue()
        self.is_busy = False
        self.auto_dpi_check = False
        self.selected_device_info = None
        self.current_usb_port = "USB location unavailable"

        self.collection_status_var = tk.StringVar(value="Searching...")
        self.preset_var = tk.StringVar(value="1000 DPI")
        self.current_dpi_var = tk.StringVar(value="Current DPI: detecting...")
        self.verify_var = tk.StringVar(value="Status: checking receiver on startup")
        self.status_var = tk.StringVar(value=f"{MOUSE_DISPLAY_NAME} - Ready")

        self.build_ui()
        self.root.after(100, self.process_messages)
        self.root.after(300, self.refresh_devices)

    def build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        device = ttk.LabelFrame(main, text="Dell mouse and receiver", padding=10)
        device.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(device, text="Mouse name:").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            device,
            text=MOUSE_DISPLAY_NAME,
            font=("Segoe UI", 10, "bold"),
            foreground="#005A9E",
        ).grid(row=0, column=1, columnspan=6, sticky=tk.W, padx=(5, 0))

        ttk.Label(device, text="Model:").grid(row=1, column=0, sticky=tk.W, pady=(10, 0))
        ttk.Label(
            device,
            text=MOUSE_MODEL,
            width=14,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=(5, 3),
        ).grid(row=1, column=1, padx=(5, 15), pady=(10, 0), sticky=tk.W)

        ttk.Label(device, text="Vendor ID:").grid(row=1, column=2, sticky=tk.W, pady=(10, 0))
        ttk.Label(
            device,
            text=f"0x{VID:04X}",
            width=12,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=(5, 3),
        ).grid(row=1, column=3, padx=(5, 15), pady=(10, 0), sticky=tk.W)

        ttk.Label(device, text="Product ID:").grid(row=1, column=4, sticky=tk.W, pady=(10, 0))
        ttk.Label(
            device,
            text=f"0x{PID:04X}",
            width=12,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=(5, 3),
        ).grid(row=1, column=5, padx=(5, 15), pady=(10, 0), sticky=tk.W)

        self.refresh_button = ttk.Button(device, text="Refresh devices", command=self.refresh_devices)
        self.refresh_button.grid(row=1, column=6, pady=(10, 0), sticky=tk.E)

        ttk.Label(device, text="USB port:").grid(row=2, column=0, sticky=tk.W, pady=(10, 0))
        ttk.Label(
            device,
            textvariable=self.collection_status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=(5, 3),
        ).grid(row=2, column=1, columnspan=6, sticky=tk.EW, pady=(10, 0))

        ttk.Label(
            device,
            text=(
                "The receiver is detected by VID 0x413C and PID 0x4503. "
                "The USB field shows the current Linux USB bus and port path."
            ),
            foreground="#555555",
            wraplength=950,
        ).grid(row=3, column=0, columnspan=7, sticky=tk.W, pady=(8, 0))

        ttk.Label(
            device,
            text=f"NOTE: Working with firmware versions {SUPPORTED_FIRMWARE}",
            font=("Segoe UI", 10, "bold"),
            foreground="#C00000",
        ).grid(row=4, column=0, columnspan=7, sticky=tk.W, pady=(8, 0))

        device.columnconfigure(6, weight=1)

        preset = ttk.LabelFrame(main, text=f"{MOUSE_MODEL} DPI presets", padding=10)
        preset.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(preset, text="Preset:").grid(row=0, column=0, sticky=tk.W)
        self.preset_combo = ttk.Combobox(
            preset,
            textvariable=self.preset_var,
            values=list(DPI_PRESETS),
            state="readonly",
            width=18,
        )
        self.preset_combo.grid(row=0, column=1, padx=(5, 8))

        self.load_button = ttk.Button(preset, text="Load preset", command=self.load_preset)
        self.load_button.grid(row=0, column=2, padx=4)

        self.apply_button = ttk.Button(preset, text="Apply DPI", command=self.apply_and_verify)
        self.apply_button.grid(row=0, column=3, padx=4)

        ttk.Label(
            preset,
            textvariable=self.current_dpi_var,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(10, 2))
        ttk.Label(preset, textvariable=self.verify_var).grid(
            row=2, column=0, columnspan=5, sticky=tk.W
        )

        report_frame = ttk.LabelFrame(main, text="32-byte Feature Report", padding=10)
        report_frame.pack(fill=tk.X, pady=(0, 8))
        self.report_text = tk.Text(
            report_frame,
            height=6,
            wrap=tk.NONE,
            font=("Consolas", 10),
            state=tk.DISABLED,
            background="#F3F3F3",
        )
        self.report_text.pack(fill=tk.X)
        self.set_report_display(build_dpi_report(0x01))

        buttons = ttk.Frame(main)
        buttons.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(buttons, text="Clear", command=self.clear).pack(side=tk.RIGHT)

        response = ttk.LabelFrame(main, text="Response and verification", padding=10)
        response.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.response_text = tk.Text(
            response,
            height=13,
            wrap=tk.NONE,
            font=("Consolas", 10),
            state=tk.DISABLED,
        )
        self.response_text.pack(fill=tk.BOTH, expand=True)

        log_frame = ttk.LabelFrame(main, text="Activity log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(
            log_frame,
            height=7,
            wrap=tk.NONE,
            font=("Consolas", 9),
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            self.root,
            textvariable=self.status_var,
            anchor=tk.W,
            relief=tk.SUNKEN,
        ).pack(fill=tk.X)

    def set_busy(self, busy, status=None):
        self.is_busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for control in (self.refresh_button, self.load_button, self.apply_button):
            control.configure(state=state)
        self.status_var.set(status or ("Working..." if busy else f"{MOUSE_DISPLAY_NAME} - Ready"))

    def log(self, text):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def show_response(self, text):
        self.response_text.configure(state=tk.NORMAL)
        self.response_text.delete("1.0", tk.END)
        self.response_text.insert(tk.END, text)
        self.response_text.configure(state=tk.DISABLED)

    def set_report_display(self, report_data):
        self.report_text.configure(state=tk.NORMAL)
        self.report_text.delete("1.0", tk.END)
        self.report_text.insert("1.0", format_hex(report_data))
        self.report_text.configure(state=tk.DISABLED)

    def clear(self):
        self.show_response("")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self.verify_var.set("Status: output cleared")

    def load_preset(self):
        name = self.preset_var.get()
        code = DPI_PRESETS.get(name)
        if code is None:
            messagebox.showerror("DPI preset", "Select a valid DPI preset.")
            return False

        report = build_dpi_report(code)
        self.set_report_display(report)
        self.log(f"Loaded {name} for {MOUSE_DISPLAY_NAME}: prefix 08 11 01 {code:02X}")
        self.status_var.set(f"{MOUSE_MODEL}: loaded {name}")
        return True

    def apply_and_verify(self):
        if self.load_preset():
            self.start_operation("set_get")

    def refresh_devices(self):
        if self.is_busy:
            return

        self.selected_device_info = None
        self.collection_status_var.set("Searching...")
        self.set_busy(True, f"Searching for {MOUSE_DISPLAY_NAME} across all USB ports...")
        threading.Thread(target=self.refresh_worker, args=(VID, PID), daemon=True).start()

    def refresh_worker(self, vid, pid):
        try:
            devices = [item for item in hid.enumerate(vid, pid) if item.get("path")]
            usb_port = get_usb_port_location(devices[0] if devices else None)
            self.messages.put(("devices", (devices, usb_port)))
        except Exception as exc:
            self.messages.put(("error", f"Device enumeration failed: {exc}"))
        finally:
            self.messages.put(("busy", False))

    def update_devices(self, payload):
        devices, usb_port = payload
        self.devices = list(devices)
        self.selected_device_info = None
        self.current_usb_port = usb_port

        if not self.devices:
            self.collection_status_var.set("Receiver not found")
            self.log(
                f"{MOUSE_DISPLAY_NAME} receiver was not found. "
                f"VID=0x{VID:04X}, PID=0x{PID:04X}."
            )
            self.current_dpi_var.set("Current DPI: unavailable")
            self.status_var.set(f"{MOUSE_MODEL} receiver not found")
            return

        self.collection_status_var.set(usb_port)
        self.log(
            f"{MOUSE_DISPLAY_NAME} detected. VID=0x{VID:04X}, PID=0x{PID:04X}. "
            f"HID collections: {len(self.devices)}. USB port: {usb_port}"
        )
        self.status_var.set(f"{MOUSE_DISPLAY_NAME} detected")

        if not self.auto_dpi_check:
            self.auto_dpi_check = True
            self.current_dpi_var.set("Current DPI: detecting...")
            self.verify_var.set("Status: reading DPI automatically")
            self.root.after(250, lambda: self.start_operation("get"))

    def selected_device(self):
        if not self.devices:
            raise RuntimeError(
                f"The {MOUSE_DISPLAY_NAME} receiver is not available. "
                "Connect it to any USB port and click Refresh devices."
            )
        return self.devices[0]

    def current_report(self):
        preset_name = self.preset_var.get()
        dpi_code = DPI_PRESETS.get(preset_name)
        if dpi_code is None:
            raise ValueError("Select a valid DPI preset.")

        report = build_dpi_report(dpi_code)
        self.set_report_display(report)
        return report

    def start_operation(self, operation):
        if self.is_busy:
            return

        try:
            device_info = self.selected_device()
            report = self.current_report() if operation in ("set", "set_get") else None
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("Cannot start", str(exc))
            return

        operation_status = {
            "set": f"Sending {MOUSE_MODEL} DPI setting...",
            "get": f"Reading current {MOUSE_MODEL} DPI...",
            "set_get": f"Applying and verifying {MOUSE_MODEL} DPI...",
        }
        self.set_busy(True, operation_status.get(operation, "Running HID operation..."))
        threading.Thread(
            target=self.operation_worker,
            args=(operation, device_info, report),
            daemon=True,
        ).start()

    @staticmethod
    def enumerate_matching_collections():
        return [item for item in hid.enumerate(VID, PID) if item.get("path")]

    def operation_worker(self, operation, device_info, report):
        failures = []
        usb_port = get_usb_port_location(device_info)
        self.messages.put(("usb_port", usb_port))
        candidates = self.enumerate_matching_collections()

        if not candidates:
            self.messages.put(
                (
                    "error",
                    f"Mouse: {MOUSE_DISPLAY_NAME}\n"
                    f"USB port: {usb_port}\n"
                    f"No matching HID collections were found for VID=0x{VID:04X}, PID=0x{PID:04X}.",
                )
            )
            self.messages.put(("busy", False))
            return

        for item in candidates:
            device = hid.device()
            interface = item.get("interface_number")
            usage_page = safe_int(item.get("usage_page"))
            usage = safe_int(item.get("usage"))
            description = (
                f"interface={interface}, usage_page=0x{usage_page:04X}, usage=0x{usage:04X}"
            )

            try:
                device.open_path(item["path"])
                sent = None
                response = None

                if operation in ("set", "set_get"):
                    sent = device.send_feature_report(report)
                    if sent < 0:
                        raise OSError("SET_REPORT failed")

                if operation == "set_get":
                    time.sleep(READBACK_DELAY)

                if operation in ("get", "set_get"):
                    raw_response = bytes(device.get_feature_report(REPORT_ID, REPORT_LENGTH))
                    if not raw_response:
                        raise OSError("GET_REPORT returned no data")

                    response = normalize_feature_response(raw_response)
                    if not is_valid_dpi_response(response):
                        raise OSError(
                            "GET_REPORT did not contain the Dell DPI signature 08 11 01 <01-04>"
                        )

                self.selected_device_info = item
                self.messages.put(
                    (
                        "result",
                        {
                            "sent": sent,
                            "response": response,
                            "report": report,
                            "collection": description,
                            "usb_port": usb_port,
                        },
                    )
                )
                self.messages.put(("busy", False))
                return

            except Exception as exc:
                error_text = str(exc)
                if "permission" in error_text.lower() or "access" in error_text.lower():
                    error_text += (
                        " | Linux access denied. Install the udev rule shown in the "
                        "README instructions, then reconnect the receiver."
                    )
                failures.append(
                    f"USB port: {usb_port} | {description}: "
                    f"{type(exc).__name__}: {error_text}"
                )
            finally:
                try:
                    device.close()
                except Exception:
                    pass

        self.messages.put(
            (
                "error",
                f"{MOUSE_DISPLAY_NAME}\n\n"
                "No matching HID collection completed the requested operation.\n\n"
                + "\n".join(failures),
            )
        )
        self.messages.put(("busy", False))

    def display_result(self, result):
        usb_port = result.get("usb_port", "USB location unavailable")
        collection = result.get("collection", "Unknown HID collection")
        lines = [
            f"Mouse: {MOUSE_DISPLAY_NAME}",
            f"Model: {MOUSE_MODEL}",
            f"Supported firmware: {SUPPORTED_FIRMWARE}",
            f"USB port: {usb_port}",
            f"HID collection: {collection}",
            "",
        ]

        report = result["report"]
        expected_code = report[3] if report is not None else None

        if result["sent"] is not None:
            lines.append(f"SET_REPORT returned: {result['sent']} bytes")
            lines.append(f"Requested DPI: {DPI_BY_CODE.get(expected_code, 'Unknown')}")
            lines.append("")

        response = result["response"]
        if response is not None:
            verification = verify_dpi_response(response, expected_code)
            lines.extend(
                (
                    f"GET_REPORT returned: {len(response)} bytes",
                    "",
                    format_hex(response),
                    "",
                    "Verification",
                    "------------",
                    f"Length is 32 bytes: {verification['valid_length']}",
                    f"Report ID is 0x08: {verification['valid_report_id']}",
                    f"Command byte is 0x11: {verification['valid_command']}",
                    f"Fixed byte 2 is 0x01: {verification['valid_fixed_parameter']}",
                )
            )

            code = verification["dpi_code"]
            code_text = f"0x{code:02X}" if code is not None else "missing"
            lines.append(f"Returned DPI code: {code_text}")
            lines.append(f"Decoded DPI: {verification['dpi_name'] or 'Unknown'}")
            lines.append(f"Bytes 4-31 are zero: {verification['padding_is_zero']}")

            if verification["matches_expected"] is not None:
                lines.append(f"Matches requested DPI: {verification['matches_expected']}")

            verification_status = "PASS" if verification["fully_valid"] else "FAIL"
            lines.append(f"Overall verification: {verification_status}")

            self.current_dpi_var.set(
                f"Current DPI: {verification['dpi_name'] or 'Unknown'} ({code_text})"
            )

            if report is None:
                self.verify_var.set(f"Status: startup DPI detection {verification_status}")
                self.auto_dpi_check = False
            else:
                self.verify_var.set(f"Verification: {verification_status}")

        self.show_response("\n".join(lines))

        if response is not None:
            verification = verify_dpi_response(response, expected_code)
            dpi_name = verification["dpi_name"] or "Unknown"

            if report is None:
                self.log(
                    f"{MOUSE_MODEL} current DPI read successfully: {dpi_name}. USB port: {usb_port}"
                )
            else:
                self.log(
                    f"{MOUSE_MODEL} DPI applied and confirmed: {dpi_name}. USB port: {usb_port}"
                )

            self.status_var.set(f"{MOUSE_MODEL} current DPI: {dpi_name}")
        else:
            self.log(
                f"{MOUSE_MODEL} SET_REPORT completed successfully. USB port: {usb_port}"
            )
            self.status_var.set(f"{MOUSE_MODEL} DPI setting sent")

    def process_messages(self):
        try:
            while True:
                kind, payload = self.messages.get_nowait()

                if kind == "devices":
                    self.update_devices(payload)
                elif kind == "usb_port":
                    self.current_usb_port = payload
                    self.collection_status_var.set(payload)
                elif kind == "result":
                    self.display_result(payload)
                elif kind == "busy":
                    self.set_busy(payload)
                elif kind == "error":
                    self.log("ERROR: " + payload)
                    self.collection_status_var.set(self.current_usb_port)

                    if self.auto_dpi_check:
                        self.auto_dpi_check = False
                        self.current_dpi_var.set(
                            "Current DPI: unavailable from standalone GET_REPORT"
                        )
                        self.verify_var.set(
                            "Status: receiver does not expose current DPI before a DPI command"
                        )
                        self.status_var.set(f"{MOUSE_MODEL} startup DPI query unavailable")
                    else:
                        self.show_response(payload)
                        self.verify_var.set("Verification: ERROR")
                        messagebox.showerror("HID error", payload)

        except queue.Empty:
            pass

        self.root.after(100, self.process_messages)


def main():
    root = tk.Tk()

    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except tk.TclError:
        pass

    DellDpiGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
