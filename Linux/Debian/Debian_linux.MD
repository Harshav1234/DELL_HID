\# Dell MS3320W DPI Tool for Linux



\## Install requirements



For Ubuntu, Debian, or Linux Mint:



```bash

sudo apt update

sudo apt install python3-tk python3-pip libhidapi-hidraw0

python3 -m pip install hidapi

```



If your distribution prevents system-wide `pip` installation, use a virtual environment:



```bash

python3 -m venv dell-dpi-env

source dell-dpi-env/bin/activate

pip install hidapi

```



\## Run the application



```bash

python3 dell\_ms3320w\_dpi\_tool\_linux.py

```



\## HID permission setup



If the receiver is detected but feature reports return a permission or access error, create a udev rule:



```bash

sudo nano /etc/udev/rules.d/99-dell-ms3320w.rules

```



Add:



```udev

SUBSYSTEM=="hidraw", ATTRS{idVendor}=="413c", ATTRS{idProduct}=="4503", MODE="0660", TAG+="uaccess"

```



Reload the rules:



```bash

sudo udevadm control --reload-rules

sudo udevadm trigger

```



Unplug and reconnect the Dell receiver, then start the application again:



```bash

python3 dell\_ms3320w\_dpi\_tool\_linux.py

```



> \*\*Important:\*\* Avoid running the entire GUI with `sudo`. The udev rule is the preferred method for granting access.



