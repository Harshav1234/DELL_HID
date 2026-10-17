import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import hid


MOUSE_NAME = "Dell MS3320W Wireless Mouse"
MODEL = "MS3320W"
FIRMWARE = "0.2.4.0 and 0.2.4.4"
VID, PID = 0x413C, 0x4503
REPORT_ID, REPORT_LENGTH = 0x08, 32

DPI_PRESETS = {
    "1000 DPI": 0x01,
    "1600 DPI": 0x02,
    "2400 DPI": 0x03,
    "4000 DPI": 0x04,
}
DPI_BY_CODE = {value: name for name, value in DPI_PRESETS.items()}


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def find_usb_parent(path):
    try:
        current = Path(path).resolve()
    except OSError:
        return None

    for node in (current, *current.parents):
        if (
            read_text(node / "idVendor").lower() == f"{VID:04x}"
            and read_text(node / "idProduct").lower() == f"{PID:04x}"
        ):
            return node
    return None


def usb_location(info=None):
    names = []

    if info:
        path = info.get("path")
        if isinstance(path, bytes):
            path = path.decode(errors="replace")
        name = os.path.basename(str(path or ""))
        if name.startswith("hidraw"):
            names.append(name)

    root = Path("/sys/class/hidraw")
    nodes = [root / name for name in names]
    nodes += [path for path in sorted(root.glob("hidraw*")) if path not in nodes]

    for hidraw in nodes:
        parent = find_usb_parent(hidraw / "device")
        if parent:
            bus = read_text(parent / "busnum") or "?"
            device = read_text(parent / "devnum") or "?"
            port = read_text(parent / "devpath") or parent.name
            product = read_text(parent / "product")
            result = f"USB bus {bus}, device {device}, port path {port}"
            return result + (f" | {product}" if product else "")

    return "USB location unavailable"


def make_report(code):
    if code not in DPI_BY_CODE:
        raise ValueError("Unsupported DPI code")
    return bytes([REPORT_ID, 0x11, 0x01, code] + [0] * 28)


def normalize(data):
    data = bytes(data)

    if len(data) == 33 and data[:2] == b"\x00\x08":
        return data[1:]
    if len(data) == 33 and data[0] == REPORT_ID:
        return data[:32]
    return data


def valid_response(data):
    data = normalize(data)
    return (
        len(data) == 32
        and data[:3] == b"\x08\x11\x01"
        and data[3] in DPI_BY_CODE
    )


def hex_dump(data):
    data = bytes(data)
    return "\n".join(
        f"{offset:04X}: " + " ".join(f"{byte:02X}" for byte in data[offset:offset + 8])
        for offset in range(0, len(data), 8)
    )


def open_hid_device(path):
    """Open a HID device with either supported Python HID API style."""
    if hasattr(hid, "Device"):
        # Newer API, for example: hid.Device(path=...)
        try:
            return hid.Device(path=path)
        except TypeError:
            return hid.Device(path)

    if hasattr(hid, "device"):
        # Legacy hidapi API: hid.device(), followed by open_path(...)
        device = hid.device()
        device.open_path(path)
        return device

    raise RuntimeError(
        "Unsupported Python HID module. The imported module provides neither "
        "hid.Device nor hid.device. Imported from: "
        f"{getattr(hid, '__file__', 'unknown location')}"
    )


def send_feature_report(device, report):
    """Send a feature report across common hid/hidapi Python bindings."""
    if hasattr(device, "send_feature_report"):
        result = device.send_feature_report(report)
    elif hasattr(device, "send_feature_report_data"):
        result = device.send_feature_report_data(report)
    else:
        raise RuntimeError("The HID device has no feature-report send method")

    # Some bindings return None after a successful write.
    return len(report) if result is None else result


def get_feature_report(device, report_id, length):
    """Read a feature report across common hid/hidapi Python bindings."""
    if not hasattr(device, "get_feature_report"):
        raise RuntimeError("The HID device has no get_feature_report method")

    try:
        return device.get_feature_report(report_id, length)
    except TypeError:
        # Some bindings accept a single length argument.
        return device.get_feature_report(length)


class App:
    def __init__(self, root):
        self.root = root
        root.title("Dell MS3320W DPI Tool for Fedora Linux")
        root.geometry("1000x760")
        root.minsize(820, 620)

        self.messages = queue.Queue()
        self.devices = []
        self.busy = False

        self.port_var = tk.StringVar(value="Searching...")
        self.preset_var = tk.StringVar(value="1000 DPI")
        self.dpi_var = tk.StringVar(value="Current DPI: detecting...")
        self.verify_var = tk.StringVar(value="Status: starting")
        self.status_var = tk.StringVar(value="Ready")

        self.build_ui()
        root.after(100, self.process_messages)
        root.after(300, self.refresh)

    def build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        box = ttk.LabelFrame(main, text="Dell mouse and receiver", padding=10)
        box.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(box, text="Mouse:").grid(row=0, column=0, sticky="w")
        ttk.Label(
            box,
            text=MOUSE_NAME,
            font=("Segoe UI", 10, "bold"),
            foreground="#005A9E",
        ).grid(row=0, column=1, columnspan=5, sticky="w")

        ttk.Label(box, text="Model:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(box, text=MODEL, relief="sunken", padding=(5, 3)).grid(
            row=1, column=1, sticky="w", pady=(8, 0)
        )
        ttk.Label(box, text=f"VID: 0x{VID:04X}").grid(
            row=1, column=2, padx=15, pady=(8, 0)
        )
        ttk.Label(box, text=f"PID: 0x{PID:04X}").grid(
            row=1, column=3, pady=(8, 0)
        )

        self.refresh_btn = ttk.Button(box, text="Refresh devices", command=self.refresh)
        self.refresh_btn.grid(row=1, column=5, sticky="e", pady=(8, 0))

        ttk.Label(box, text="USB port:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(
            box,
            textvariable=self.port_var,
            relief="sunken",
            padding=(5, 3),
        ).grid(row=2, column=1, columnspan=5, sticky="ew", pady=(8, 0))

        ttk.Label(
            box,
            text=f"NOTE: Working with firmware versions {FIRMWARE}",
            font=("Segoe UI", 10, "bold"),
            foreground="#C00000",
        ).grid(row=3, column=0, columnspan=6, sticky="w", pady=(8, 0))

        box.columnconfigure(4, weight=1)

        controls = ttk.LabelFrame(main, text="DPI presets", padding=10)
        controls.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(controls, text="Preset:").grid(row=0, column=0)
        self.combo = ttk.Combobox(
            controls,
            textvariable=self.preset_var,
            values=list(DPI_PRESETS),
            state="readonly",
            width=16,
        )
        self.combo.grid(row=0, column=1, padx=5)

        self.apply_btn = ttk.Button(controls, text="Apply DPI", command=self.apply)
        self.apply_btn.grid(row=0, column=2, padx=5)

        ttk.Label(
            controls,
            textvariable=self.dpi_var,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(controls, textvariable=self.verify_var).grid(
            row=2, column=0, columnspan=4, sticky="w"
        )

        report = ttk.LabelFrame(main, text="32-byte Feature Report", padding=10)
        report.pack(fill=tk.X, pady=(0, 8))

        self.report_text = tk.Text(
            report, height=5, font=("Monospace", 10), state="disabled"
        )
        self.report_text.pack(fill=tk.X)
        self.show_report(make_report(0x01))

        response = ttk.LabelFrame(main, text="Response and verification", padding=10)
        response.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.output = tk.Text(
            response, height=13, font=("Monospace", 10), state="disabled"
        )
        self.output.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief="sunken",
            anchor="w",
        ).pack(fill=tk.X)

    def set_busy(self, value, text=None):
        self.busy = value
        state = "disabled" if value else "normal"
        self.refresh_btn.configure(state=state)
        self.apply_btn.configure(state=state)
        self.status_var.set(text or ("Working..." if value else "Ready"))

    @staticmethod
    def display(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def show_report(self, data):
        self.display(self.report_text, hex_dump(data))

    def refresh(self):
        if self.busy:
            return
        self.set_busy(True, "Searching for the Dell receiver...")
        threading.Thread(target=self.refresh_worker, daemon=True).start()

    def refresh_worker(self):
        try:
            devices = [item for item in hid.enumerate(VID, PID) if item.get("path")]
            location = usb_location(devices[0] if devices else None)
            self.messages.put(("devices", (devices, location)))
        except Exception as exc:
            self.messages.put(("error", f"Device enumeration failed:\n{exc}"))
        finally:
            self.messages.put(("busy", False))

    def apply(self):
        if self.busy:
            return

        preset = self.preset_var.get()
        if preset not in DPI_PRESETS:
            messagebox.showerror("DPI error", "Select a valid DPI preset.")
            return

        code = DPI_PRESETS[preset]
        report = make_report(code)
        self.show_report(report)
        self.set_busy(True, "Applying and verifying DPI...")
        threading.Thread(
            target=self.io_worker,
            args=(report, code),
            daemon=True,
        ).start()

    def io_worker(self, report, expected):
        failures = []

        try:
            devices = [item for item in hid.enumerate(VID, PID) if item.get("path")]
        except Exception as exc:
            self.messages.put(("error", f"Device enumeration failed:\n{exc}"))
            return
        finally:
            # Do not clear busy here; each result/error path handles it in the UI thread.
            pass

        if not devices:
            self.messages.put(
                (
                    "error",
                    "Dell receiver not found. Disconnect and reconnect the receiver, "
                    "then click Refresh devices.",
                )
            )
            return

        for info in devices:
            device = None
            path = info.get("path")
            location = usb_location(info)

            try:
                device = open_hid_device(path)
                sent = send_feature_report(device, report)

                if isinstance(sent, int) and sent < 0:
                    raise OSError("SET_REPORT failed")

                time.sleep(0.05)
                response = normalize(
                    get_feature_report(device, REPORT_ID, REPORT_LENGTH)
                )

                if not valid_response(response):
                    raise OSError(
                        "Invalid DPI GET_REPORT response. Raw response:\n"
                        + hex_dump(response)
                    )

                if response[3] != expected:
                    raise OSError(
                        "Returned DPI does not match requested DPI: "
                        f"requested=0x{expected:02X}, returned=0x{response[3]:02X}"
                    )

                self.messages.put(("result", (sent, response, info, location)))
                return

            except Exception as exc:
                failures.append(
                    f"interface={info.get('interface_number')}, "
                    f"path={path!r}: {exc}"
                )
            finally:
                if device is not None:
                    try:
                        device.close()
                    except Exception:
                        pass

        self.messages.put(
            (
                "error",
                "No HID collection completed the operation.\n\n"
                + "\n".join(failures),
            )
        )

    def process_messages(self):
        try:
            while True:
                kind, payload = self.messages.get_nowait()

                if kind == "devices":
                    self.devices, location = payload
                    self.port_var.set(location if self.devices else "Receiver not found")
                    if self.devices:
                        self.status_var.set(
                            f"Found {len(self.devices)} HID collection(s)"
                        )
                    else:
                        self.status_var.set("Receiver not found")

                elif kind == "result":
                    sent, response, info, location = payload
                    code = response[3]
                    dpi = DPI_BY_CODE[code]
                    self.dpi_var.set(f"Current DPI: {dpi} (0x{code:02X})")
                    self.verify_var.set("Verification: PASS")
                    self.display(
                        self.output,
                        f"Mouse: {MOUSE_NAME}\n"
                        f"USB: {location}\n"
                        f"Interface: {info.get('interface_number')}\n"
                        f"SET_REPORT returned: {sent} bytes\n"
                        f"GET_REPORT returned: {len(response)} bytes\n\n"
                        f"{hex_dump(response)}\n\n"
                        "Verification: PASS",
                    )
                    self.set_busy(False, f"Current DPI: {dpi}")

                elif kind == "error":
                    self.verify_var.set("Verification: ERROR")
                    self.display(self.output, payload)
                    self.set_busy(False, "Operation failed")
                    messagebox.showerror("HID error", payload)

                elif kind == "busy":
                    self.set_busy(payload)

        except queue.Empty:
            pass

        self.root.after(100, self.process_messages)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()