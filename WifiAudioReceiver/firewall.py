"""Optional helper: adds a Windows Firewall rule (UAC prompt) limited to the local subnet."""
import ctypes
import sys

RULE_NAME = "Wi-Fi Audio Receiver"


def add_rule() -> bool:
    if sys.platform != "win32":
        return False
    exe = sys.executable   # the .exe when frozen, python.exe when run from source
    params = (f'advfirewall firewall add rule name="{RULE_NAME}" dir=in action=allow '
              f'program="{exe}" enable=yes profile=private,public remoteip=localsubnet')
    try:
        # "runas" => standard Windows UAC prompt; returns > 32 when launched
        return ctypes.windll.shell32.ShellExecuteW(None, "runas", "netsh", params, None, 0) > 32
    except Exception:
        return False
