**DELL_MS3320W Wireless Mouse HID**  
# Dell MS3320W Wireless Mouse DPI Adjuster  
Python GUI application for changing DPI settings on the Dell MS3320W Wireless Mouse using direct HID feature reports.  
## Platform Support  
### Windows  
✅ Fully tested and confirmed working on:  
- Windows 10  
- Windows 11  
The application has been successfully validated for:  
- Receiver detection  
- USB port identification  
- HID collection enumeration  
- DPI preset selection  
- SET_REPORT transmission  
- GET_REPORT verification  
- DPI confirmation  
Supported firmware versions:  
- 0.2.4.0  
- 0.2.4.4  
---  
### Linux  
⚠ Debian Linux support is currently experimental.  
Working in Fedora   
The Linux version of the application has been implemented, but full verification has not yet been completed on actual hardware.  
The following items still require validation in a Linux environment:  
- HID device enumeration  
- Feature report write operations (SET_REPORT)  
- Feature report read operations (GET_REPORT)  
- DPI verification workflow  
- Multi-USB-port operation  
- Permission handling through udev rules  
- Compatibility across distributions  
Tested status:  
| Feature | Windows | Linux |  
|----------|----------|----------|  
| Device Detection | ✅ Verified | ⚠ Requires Validation for Debian |  
| USB Port Detection | ✅ Verified | ⚠ Requires Validation for Debian |  
| DPI Change | ✅ Verified | ⚠ Requires Validation for Debian |  
| DPI Verification | ✅ Verified | ⚠ Requires Validation for Debian |  
| HID Communication | ✅ Verified | ⚠ Requires Validation for Debian |  
| Multi-Port Operation | ✅ Verified | ⚠ Requires Validation for Debian |  
---  
## Linux Verification Required  
Before Linux support can be considered production-ready, verification is required for:  
1. Fedora Linux -> Working, Read FEDORA_SETUP.MD inside fedora folder.  
2. Debian Linux  
Recommended test procedure:  
1. Connect Dell MS3320W receiver.  
2. Run application with appropriate HID permissions.  
3. Change DPI to:  
   - 1000 DPI  
   - 1600 DPI  
   - 2400 DPI  
   - 4000 DPI  
4. Verify mouse sensitivity changes correctly.  
5. Confirm GET_REPORT returns expected DPI value.  
6. Test operation after moving receiver to different USB ports.  
7. Verify application behavior after reconnecting receiver.  
---  
## Notice  
This project is currently intended primarily for Windows systems.  
Linux functionality has been added based on the HID communication implementation; however, device-specific validation is still required before Linux support can be officially confirmed.  
Windows support status: ✅ Verified  
Linux support status: ⚠ Verification Required  
