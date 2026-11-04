# Descoberta original das portas COM no Windows.
import serial.tools.list_ports
import wmi
import pythoncom

def get_all_com_ports():
    ports = set()
    for port in serial.tools.list_ports.comports():
        ports.add(port.device)
    try:
        pythoncom.CoInitialize()
        w = wmi.WMI()
        for sp in w.query("SELECT * FROM Win32_SerialPort"):
            if sp.DeviceID and sp.DeviceID not in ports:
                ports.add(sp.DeviceID)
    except Exception as e:
        print(f"WMI error: {e}")
    finally:
        pythoncom.CoUninitialize()
    return sorted(list(ports))
