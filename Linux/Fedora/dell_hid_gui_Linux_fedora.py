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
DPI_PRESETS = {"1000 DPI": 0x01, "1600 DPI": 0x02, "2400 DPI": 0x03, "4000 DPI": 0x04}
DPI_BY_CODE = {v: k for k, v in DPI_PRESETS.items()}


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
        if (read_text(node / "idVendor").lower() == f"{VID:04x}" and
                read_text(node / "idProduct").lower() == f"{PID:04x}"):
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
    nodes = [root / n for n in names]
    nodes += [p for p in sorted(root.glob("hidraw*")) if p not in nodes]
    for hidraw in nodes:
        parent = find_usb_parent(hidraw / "device")
        if parent:
            bus = read_text(parent / "busnum") or "?"
            dev = read_text(parent / "devnum") or "?"
            port = read_text(parent / "devpath") or parent.name
            product = read_text(parent / "product")
            result = f"USB bus {bus}, device {dev}, port path {port}"
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
    return len(data) == 32 and data[:3] == b"\x08\x11\x01" and data[3] in DPI_BY_CODE


def hex_dump(data):
    data = bytes(data)
    return "\n".join(f"{i:04X}: " + " ".join(f"{b:02X}" for b in data[i:i+8])
                     for i in range(0, len(data), 8))


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
        ttk.Label(box, text=MOUSE_NAME, font=("Segoe UI", 10, "bold"), foreground="#005A9E").grid(row=0, column=1, columnspan=5, sticky="w")
        ttk.Label(box, text="Model:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(box, text=MODEL, relief="sunken", padding=(5, 3)).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Label(box, text=f"VID: 0x{VID:04X}").grid(row=1, column=2, padx=15, pady=(8, 0))
        ttk.Label(box, text=f"PID: 0x{PID:04X}").grid(row=1, column=3, pady=(8, 0))
        self.refresh_btn = ttk.Button(box, text="Refresh devices", command=self.refresh)
        self.refresh_btn.grid(row=1, column=5, sticky="e", pady=(8, 0))
        ttk.Label(box, text="USB port:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(box, textvariable=self.port_var, relief="sunken", padding=(5, 3)).grid(row=2, column=1, columnspan=5, sticky="ew", pady=(8, 0))
        ttk.Label(box, text=f"NOTE: Working with firmware versions {FIRMWARE}", font=("Segoe UI", 10, "bold"), foreground="#C00000").grid(row=3, column=0, columnspan=6, sticky="w", pady=(8, 0))
        box.columnconfigure(4, weight=1)

        controls = ttk.LabelFrame(main, text="DPI presets", padding=10)
        controls.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(controls, text="Preset:").grid(row=0, column=0)
        self.combo = ttk.Combobox(controls, textvariable=self.preset_var, values=list(DPI_PRESETS), state="readonly", width=16)
        self.combo.grid(row=0, column=1, padx=5)
        self.apply_btn = ttk.Button(controls, text="Apply DPI", command=self.apply)
        self.apply_btn.grid(row=0, column=2, padx=5)
        ttk.Label(controls, textvariable=self.dpi_var, font=("Segoe UI", 10, "bold")).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(controls, textvariable=self.verify_var).grid(row=2, column=0, columnspan=4, sticky="w")

        report = ttk.LabelFrame(main, text="32-byte Feature Report", padding=10)
        report.pack(fill=tk.X, pady=(0, 8))
        self.report_text = tk.Text(report, height=5, font=("Monospace", 10), state="disabled")
        self.report_text.pack(fill=tk.X)
        self.show_report(make_report(1))

        response = ttk.LabelFrame(main, text="Response and verification", padding=10)
        response.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.output = tk.Text(response, height=13, font=("Monospace", 10), state="disabled")
        self.output.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill=tk.X)

    def set_busy(self, value, text=None):
        self.busy = value
        state = "disabled" if value else "normal"
        self.refresh_btn.configure(state=state)
        self.apply_btn.configure(state=state)
        self.status_var.set(text or ("Working..." if value else "Ready"))

    def display(self, widget, text):
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
            devices = [d for d in hid.enumerate(VID, PID) if d.get("path")]
            self.messages.put(("devices", (devices, usb_location(devices[0] if devices else None))))
        except Exception as exc:
            self.messages.put(("error", str(exc)))
        finally:
            self.messages.put(("busy", False))

    def apply(self):
        if self.busy:
            return
        code = DPI_PRESETS[self.preset_var.get()]
        report = make_report(code)
        self.show_report(report)
        self.set_busy(True, "Applying and verifying DPI...")
        threading.Thread(target=self.io_worker, args=(report, code), daemon=True).start()

    def io_worker(self, report, expected):
        failures = []
        location = usb_location(self.devices[0] if self.devices else None)
        for info in [d for d in hid.enumerate(VID, PID) if d.get("path")]:
            dev = hid.device()
            try:
                dev.open_path(info["path"])
                sent = dev.send_feature_report(report)
                if sent < 0:
                    raise OSError("SET_REPORT failed")
                time.sleep(0.05)
                response = normalize(dev.get_feature_report(REPORT_ID, REPORT_LENGTH))
                if not valid_response(response):
                    raise OSError("Invalid DPI GET_REPORT response")
                if response[3] != expected:
                    raise OSError("Returned DPI does not match requested DPI")
                self.messages.put(("result", (sent, response, info, location)))
                return
            except Exception as exc:
                failures.append(f"interface={info.get('interface_number')}: {exc}")
            finally:
                try:
                    dev.close()
                except Exception:
                    pass
        self.messages.put(("error", "No HID collection completed the operation.\n" + "\n".join(failures)))
        self.messages.put(("busy", False))

    def process_messages(self):
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "devices":
                    self.devices, location = payload
                    self.port_var.set(location if self.devices else "Receiver not found")
                    self.status_var.set(f"Found {len(self.devices)} HID collection(s)" if self.devices else "Receiver not found")
                elif kind == "result":
                    sent, response, info, location = payload
                    code = response[3]
                    dpi = DPI_BY_CODE[code]
                    self.dpi_var.set(f"Current DPI: {dpi} (0x{code:02X})")
                    self.verify_var.set("Verification: PASS")
                    self.display(self.output, f"Mouse: {MOUSE_NAME}\nUSB: {location}\nInterface: {info.get('interface_number')}\nSET_REPORT returned: {sent} bytes\nGET_REPORT returned: {len(response)} bytes\n\n{hex_dump(response)}\n\nVerification: PASS")
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
