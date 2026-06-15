import asyncio
import threading
import time
import queue
from typing import Dict, Any, Callable
from engine.torrent_file import TorrentFile
from engine.magnet import MagnetLink
from engine.tracker import TrackerClient, generate_peer_id
from engine.download_manager import DownloadManager
from engine.logger import global_logger, log

class EngineSnapshot:
    """A thread-safe snapshot of the engine state passed to the GUI."""
    def __init__(self):
        self.torrents: Dict[str, Dict[str, Any]] = {}
        self.logs: list[str] = []

class EngineRunner(threading.Thread):
    def __init__(self, command_queue: queue.Queue, snapshot_callback: Callable[[EngineSnapshot], None]):
        super().__init__(daemon=True)
        self.command_queue = command_queue
        self.snapshot_callback = snapshot_callback
        self.loop = asyncio.new_event_loop()
        
        self.peer_id = generate_peer_id()
        self.downloads: Dict[str, DownloadManager] = {} # info_hash (hex) -> DownloadManager
        self.last_log_idx = -1

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.create_task(self._snapshot_loop())
        self.loop.create_task(self._command_loop())
        self.loop.create_task(self._tracker_loop())
        self.loop.run_forever()

    async def _tracker_loop(self):
        """Periodically polls trackers for active downloads to find new peers."""
        while True:
            for info_hash_hex, dm in list(self.downloads.items()):
                if dm.is_running and len(dm.active_peers) + len(dm.pending_peers) < 30:
                    trackers_to_try = []
                    if dm.torrent and dm.torrent.announce:
                        trackers_to_try.append(dm.torrent.announce)
                    elif dm.magnet and dm.magnet.trackers:
                        trackers_to_try.extend(dm.magnet.trackers)
                        
                    info_hash = bytes.fromhex(info_hash_hex)
                    left = dm.torrent.total_size - dm.downloaded if dm.torrent else 1
                    
                    for announce_url in trackers_to_try:
                        tracker = TrackerClient(announce_url, info_hash, self.peer_id)
                        
                        peers = await tracker.announce(
                            uploaded=int(dm.uploaded),
                            downloaded=int(dm.downloaded),
                            left=int(left)
                        )
                        
                        if peers:
                            existing_ips = {p.ip for p in dm.active_peers + dm.pending_peers}
                            for ip, port in peers:
                                if ip not in existing_ips:
                                    from engine.peer_protocol import PeerConnection
                                    peer = PeerConnection(ip, port, info_hash, self.peer_id)
                                    dm.add_peer(peer)
                            break
                            
            await asyncio.sleep(15)

    async def _command_loop(self):
        while True:
            try:
                # Non-blocking check for commands from the GUI
                cmd = self.command_queue.get_nowait()
                if cmd['action'] == 'add_torrent':
                    self._add_torrent(cmd['file_path'], cmd['save_path'])
                elif cmd['action'] == 'add_magnet':
                    self._add_magnet(cmd['magnet_uri'], cmd['save_path'])
                elif cmd['action'] == 'pause':
                    self._pause_torrent(cmd['info_hash_hex'])
                elif cmd['action'] == 'resume':
                    self._resume_torrent(cmd['info_hash_hex'])
                elif cmd['action'] == 'delete':
                    self._delete_torrent(cmd['info_hash_hex'])
                elif cmd['action'] == 'toggle_stream_mode':
                    self._toggle_stream_mode(cmd['info_hash_hex'])
            except queue.Empty:
                pass
            await asyncio.sleep(0.1)

    async def _snapshot_loop(self):
        """Builds a state snapshot and sends it to the GUI every 500ms."""
        while True:
            snapshot = EngineSnapshot()
            
            # Fetch new logs
            new_logs, highest_idx = global_logger.get_new_logs(self.last_log_idx)
            snapshot.logs = new_logs
            self.last_log_idx = highest_idx
            
            for info_hash_hex, dm in self.downloads.items():
                progress = 0
                size = 0
                name = ""
                status = "Downloading" if dm.is_running else "Paused"
                
                if dm.fetching_metadata:
                    status = "Fetching Metadata..."
                    name = dm.magnet.name
                else:
                    if dm.torrent:
                        name = dm.torrent.name
                        size = dm.torrent.total_size
                        if size > 0:
                            progress = (dm.downloaded / size) * 100
                            
                        if len(dm.completed_pieces) == len(dm.pieces) and len(dm.pieces) > 0:
                            status = "Seeding"
                            progress = 100
                        
                # Extract peer info
                peers_info = []
                for p in dm.active_peers:
                    flags = []
                    if p.am_choking: flags.append('c')
                    if p.am_interested: flags.append('i')
                    if p.peer_choking: flags.append('C')
                    if p.peer_interested: flags.append('I')
                    
                    peers_info.append({
                        'ip': p.ip,
                        'port': p.port,
                        'flags': "".join(flags),
                        'down_speed': 0,
                        'up_speed': 0
                    })
                    
                snapshot.torrents[info_hash_hex] = {
                    'name': name,
                    'size': size,
                    'progress': min(progress, 100),
                    'status': status,
                    'down_speed': dm.down_speed,
                    'up_speed': dm.up_speed,
                    'peers_connected': len([p for p in dm.active_peers if p.connected]),
                    'peers_total': len(dm.active_peers),
                    'sequential_mode': dm.sequential_mode,
                    
                    # Detailed stats
                    'info_hash': info_hash_hex,
                    'save_path': dm.save_path,
                    'piece_size': dm.torrent.piece_length if dm.torrent else 0,
                    'total_pieces': len(dm.pieces),
                    'completed_pieces': list(dm.completed_pieces),
                    
                    # Peer list
                    'peers_list': peers_info,
                    
                    # File list
                    'files': dm.torrent.files if dm.torrent else []
                }
                
            self.snapshot_callback(snapshot)
            await asyncio.sleep(0.5) # 500ms throttle

    def _add_torrent(self, file_path: str, save_path: str):
        try:
            torrent = TorrentFile(file_path=file_path)
            info_hash_hex = torrent.info_hash.hex()
            if info_hash_hex not in self.downloads:
                dm = DownloadManager(torrent, save_path)
                self.downloads[info_hash_hex] = dm
                self.loop.create_task(dm.run())
        except Exception as e:
            print(f"Error adding torrent: {e}")

    def _add_magnet(self, magnet_uri: str, save_path: str):
        try:
            magnet = MagnetLink(magnet_uri)
            info_hash_hex = magnet.info_hash.hex()
            if info_hash_hex not in self.downloads:
                dm = DownloadManager(magnet, save_path)
                self.downloads[info_hash_hex] = dm
                self.loop.create_task(dm.run())
        except Exception as e:
            print(f"Error adding magnet: {e}")

    def _pause_torrent(self, info_hash_hex: str):
        if info_hash_hex in self.downloads:
            self.downloads[info_hash_hex].is_running = False

    def _resume_torrent(self, info_hash_hex: str):
        if info_hash_hex in self.downloads:
            dm = self.downloads[info_hash_hex]
            if not dm.is_running:
                self.loop.create_task(dm.run())

    def _delete_torrent(self, info_hash_hex: str):
        if info_hash_hex in self.downloads:
            dm = self.downloads[info_hash_hex]
            dm.is_running = False
            for p in dm.active_peers:
                p.disconnect()
            del self.downloads[info_hash_hex]

    def _toggle_stream_mode(self, info_hash_hex: str):
        if info_hash_hex in self.downloads:
            dm = self.downloads[info_hash_hex]
            dm.sequential_mode = not dm.sequential_mode
