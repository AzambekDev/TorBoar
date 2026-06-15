# TorBoar 🐗

A premium, high-performance BitTorrent client written entirely in Python from the ground up, featuring a massive modern UI overhaul and a unique **Sequential Streaming Mode**.

## Features

- **Sequential Streaming Mode**: Unlike standard BitTorrent clients that download pieces randomly to maximize swarm availability, TorBoar allows you to toggle "Stream Mode". This forces the engine to download file pieces perfectly in numerical order (0, 1, 2...). You can open unfinished `.mp4` and `.mkv` files natively in VLC or other media players and watch them stream live while downloading!
- **Premium Dracula UX**: The entire application is styled with a highly intricate, handcrafted Qt Style Sheet (QSS) utilizing the universally acclaimed **Dracula Theme**. 
- **Modern Torrent Cards**: Abandons the traditional clunky spreadsheet view for massive, beautiful Torrent Cards that feature inline speed stats and glowing progress bars.
- **Physical Piece Map Visualizer**: Watch your files download in real-time. The Piece Map dynamically renders a physical matrix of thousands of tiny colored squares that flash a brilliant pastel green as blocks complete and commit to your hard drive.
- **Full Protocol Support**: Fully async architecture supporting BEP 0003 (Core Protocol), BEP 0009 (Extension for Peers to Send Metadata Files), BEP 0015 (UDP Tracker Protocol), and modern Magnet Links.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/AzambekDev/TorBoar.git
   cd TorBoar
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run TorBoar:
   ```bash
   python main.py
   ```

## Usage
- Click **"Add Magnet Link"** and paste a torrent URI to begin.
- Click the **"Piece Map"** tab at the bottom to watch the physical bytes hitting your disk in real-time.
- Toggle **"Stream Mode"** (the skip-forward icon) to force sequential downloading and open the media file in VLC immediately.

## Architecture
TorBoar utilizes a pure, custom-built asynchronous P2P engine.
- **`EngineRunner`**: The central orchestrator running the `asyncio` event loop.
- **`DownloadManager`**: Handles disk I/O, physical piece assembly, cryptographic hash verification, and dynamic state transitions.
- **`PeerConnection`**: Individual non-blocking worker tasks that negotiate the Extension Handshake, parse `MSG_BITFIELD` structures, and blast sliding-window block requests across the active swarm.
