"""Generates assets/icon.ico (run from the project folder: python assets\\make_icon.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from PySide6.QtWidgets import QApplication  # noqa: E402

from app_icon import make_pixmap  # noqa: E402

app = QApplication([])
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
print("saved" if make_pixmap(256).save(out, "ICO") else "FAILED", out)
