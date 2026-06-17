import sys
import queue
import argparse
import os
import winreg
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from engine.engine_runner import EngineRunner
from gui.main_window import MainWindow

def register_magnet_handler():
    if sys.platform != "win32":
        return
        
    try:
        exe_path = sys.executable
        if not exe_path.lower().endswith(".exe"):
            exe_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
        else:
            exe_path = f'"{exe_path}"'
            
        key_path = r"Software\Classes\magnet"
        
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:magnet protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
            
            with winreg.CreateKey(key, r"shell\open\command") as command_key:
                winreg.SetValueEx(command_key, "", 0, winreg.REG_SZ, f'{exe_path} "%1"')
    except Exception as e:
        print(f"Failed to register magnet handler: {e}")

def main():
    register_magnet_handler()

    parser = argparse.ArgumentParser(description="Antigravity BitTorrent Client")
    parser.add_argument("magnet_uri", nargs='?', help="Magnet URI to open")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    
    # Thread-safe queue for UI -> Engine commands
    command_queue = queue.Queue()
    
    # Setup GUI
    main_window = MainWindow(command_queue)
    
    # The callback to route engine snapshots to the GUI main thread
    # In PyQt, signals emitted from background threads are thread-safe 
    # and properly queued for the main thread event loop.
    def on_snapshot(snapshot):
        try:
            main_window.snapshot_received.emit(snapshot)
        except RuntimeError:
            pass # Window has been deleted, app is closing
        
    # Setup Background Engine
    engine = EngineRunner(command_queue, on_snapshot)
    engine.start()
    
    # Show GUI
    main_window.show()
    
    if args.magnet_uri and args.magnet_uri.startswith("magnet:"):
        QTimer.singleShot(500, lambda: main_window.add_magnet_from_args(args.magnet_uri))
    
    # Start Event Loop
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
