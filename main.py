"""
Entry point for the Money Trail Report Generator desktop app.

Run with:
    python main.py

This is also the entry point PyInstaller builds into a native
Windows .exe / macOS .app (see build_windows.bat / build_macos.sh).
"""

from gui.app import main

if __name__ == "__main__":
    main()
