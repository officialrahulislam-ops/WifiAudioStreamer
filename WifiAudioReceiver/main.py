import socket
import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from discovery import Discovery
from protocol import TCP_PORT
from receiver import Receiver
from ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Wi-Fi Audio Receiver")
    app.setQuitOnLastWindowClosed(False)      # keep running in the tray

    settings = QSettings("WifiAudio", "Receiver")
    if not settings.value("code"):
        import random
        settings.setValue("code", str(random.randint(1000, 9999)))

    holder = {}
    receiver = Receiver(lambda: settings.value("code"))
    holder["receiver"] = receiver
    try:
        receiver.start()
    except OSError:
        QMessageBox.critical(None, "Wi-Fi Audio Receiver",
                             f"Port {TCP_PORT} is already in use.\nIs the receiver already running (check the system tray)?")
        return 1

    discovery = Discovery(socket.gethostname(), TCP_PORT)
    discovery_ok = True
    try:
        discovery.start()
    except OSError:
        discovery_ok = False                   # manual IP entry on the phone still works

    window = MainWindow(settings, receiver, discovery, discovery_ok)
    app.aboutToQuit.connect(lambda: (discovery.stop(), receiver.stop()))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
