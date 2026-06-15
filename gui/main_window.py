import os
import queue
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QToolBar, QSplitter, QTableView, QListView,
    QTabWidget, QHeaderView,
    QProgressBar, QStyledItemDelegate, QStyleOptionProgressBar,
    QApplication, QStyle, QFileDialog, QLabel, QListWidget, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon, QColor, QPalette, QFont
from PyQt6.QtWidgets import QStyle

from gui.models import TorrentListModel, TorrentCardDelegate, PeersTableModel
from gui.piece_map import PieceMapWidget

class MainWindow(QMainWindow):
    snapshot_received = pyqtSignal(object)

    def __init__(self, command_queue: queue.Queue):
        super().__init__()
        self.command_queue = command_queue
        self.setWindowTitle("TorBoar")
        self._setup_ui()
        self._apply_dark_theme()
        
        # Set global font
        app_font = QFont("Segoe UI", 10)
        app_font.setStyleHint(QFont.StyleHint.SansSerif)
        QApplication.instance().setFont(app_font)
        
        self.snapshot_received.connect(self._on_snapshot_received)
        
        self.current_selected_hash = None
        
    def _apply_dark_theme(self):
        dark_stylesheet = """
        QMainWindow, QWidget {
            background-color: #282A36;
            color: #F8F8F2;
            font-family: "Segoe UI", sans-serif;
        }
        QToolBar {
            background-color: #21222C;
            border-bottom: 2px solid #191A21;
            spacing: 12px;
            padding: 5px;
        }
        QToolButton {
            color: #F8F8F2;
            padding: 8px 12px;
            border: 1px solid transparent;
            border-radius: 6px;
            font-weight: 600;
        }
        QToolButton:hover {
            background-color: #44475A;
            border: 1px solid #6272A4;
        }
        QToolButton:pressed {
            background-color: #191A21;
        }
        QListView {
            background-color: #282A36;
            border: none;
            outline: none;
        }
        QTableView {
            background-color: #21222C;
            alternate-background-color: #282A36;
            gridline-color: transparent;
            border: 1px solid #44475A;
            border-radius: 8px;
            selection-background-color: #6272A4;
            selection-color: white;
            padding: 2px;
        }
        QTableView::item {
            border: none;
            padding: 4px;
        }
        QHeaderView::section {
            background-color: #21222C;
            color: #6272A4;
            padding: 8px;
            border: none;
            border-bottom: 1px solid #44475A;
            font-weight: bold;
            text-transform: uppercase;
        }
        QTabWidget::pane {
            border: 1px solid #44475A;
            background-color: #282A36;
            border-radius: 8px;
            margin-top: -1px;
        }
        QTabBar::tab {
            background-color: #21222C;
            color: #6272A4;
            padding: 10px 20px;
            border: 1px solid #44475A;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            font-weight: bold;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background-color: #6272A4;
            color: #FFFFFF;
            border: 1px solid #6272A4;
        }
        QTabBar::tab:hover:!selected {
            background-color: #44475A;
            color: #F8F8F2;
        }
        QListWidget {
            background-color: #21222C;
            border: 1px solid #44475A;
            border-radius: 8px;
            padding: 5px;
        }
        QListWidget::item {
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 2px;
        }
        QListWidget::item:selected {
            background-color: #6272A4;
            color: white;
            font-weight: bold;
        }
        QListWidget::item:hover:!selected {
            background-color: #44475A;
        }
        QSplitter::handle {
            background-color: #44475A;
        }
        QStatusBar {
            background-color: #21222C;
            color: #6272A4;
            border-top: 1px solid #44475A;
            font-weight: bold;
        }
        QLabel#BrandLabel {
            font-size: 24px;
            font-weight: 900;
            color: #FF79C6;
            padding: 10px;
            letter-spacing: 2px;
        }
        """
        self.setStyleSheet(dark_stylesheet)

    def _setup_ui(self):
        # 1. Top Toolbar
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        # Brand Label inside Toolbar
        brand_label = QLabel(" TORBOAR ")
        brand_label.setObjectName("BrandLabel")
        toolbar.addWidget(brand_label)
        toolbar.addSeparator()

        style = self.style()

        add_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileIcon), "Add Torrent", self)
        add_action.triggered.connect(self._on_add_torrent)
        toolbar.addAction(add_action)

        add_magnet_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "Add Magnet Link", self)
        add_magnet_action.triggered.connect(self._on_add_magnet)
        toolbar.addAction(add_magnet_action)

        pause_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaPause), "Pause", self)
        pause_action.triggered.connect(self._on_pause_torrent)
        toolbar.addAction(pause_action)

        resume_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Resume", self)
        resume_action.triggered.connect(self._on_resume_torrent)
        toolbar.addAction(resume_action)

        delete_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon), "Delete", self)
        delete_action.triggered.connect(self._on_delete_torrent)
        toolbar.addAction(delete_action)
        
        toolbar.addSeparator()
        
        stream_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward), "Toggle Stream Mode", self)
        stream_action.triggered.connect(self._on_toggle_stream)
        toolbar.addAction(stream_action)

        # Main splitter for Sidebar + (Table/Details)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(main_splitter)
        main_splitter.setContentsMargins(10, 10, 10, 10)

        # 2. Left Sidebar
        self.sidebar = QListWidget()
        self.sidebar.addItems(["All", "Downloading", "Seeding", "Completed", "Active", "Inactive"])
        self.sidebar.setMaximumWidth(200)
        main_splitter.addWidget(self.sidebar)

        # Right splitter for Table (Top) + Details (Bottom)
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(right_splitter)

        # 3. Main Central ListView (Replaces TableView)
        self.table_model = TorrentListModel(self)
        self.table_view = QListView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.table_view.setSpacing(5)
        
        # Apply custom card delegate
        delegate = TorrentCardDelegate(self.table_view)
        self.table_view.setItemDelegate(delegate)
        
        self.table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        right_splitter.addWidget(self.table_view)

        # 4. Bottom Tabbed Detail Panel
        self.tabs = QTabWidget()
        right_splitter.addWidget(self.tabs)
        right_splitter.setSizes([500, 268]) # Default ratio

        # Tab 1: General
        self.tab_general = QWidget()
        gen_layout = QVBoxLayout(self.tab_general)
        self.lbl_info_hash = QLabel("Info Hash: ")
        self.lbl_save_path = QLabel("Save Path: ")
        self.lbl_piece_size = QLabel("Piece Size: ")
        self.lbl_total_pieces = QLabel("Total Pieces: ")
        gen_layout.addWidget(self.lbl_info_hash)
        gen_layout.addWidget(self.lbl_save_path)
        gen_layout.addWidget(self.lbl_piece_size)
        gen_layout.addWidget(self.lbl_total_pieces)
        gen_layout.addStretch()
        self.tabs.addTab(self.tab_general, "General")

        # Tab 2: Peers
        self.tab_peers = QWidget()
        peers_layout = QVBoxLayout(self.tab_peers)
        self.peers_model = PeersTableModel(self)
        self.peers_view = QTableView()
        self.peers_view.setModel(self.peers_model)
        self.peers_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        peers_layout.addWidget(self.peers_view)
        self.tabs.addTab(self.tab_peers, "Peers")

        # Tab 3: Files
        self.tab_files = QWidget()
        files_layout = QVBoxLayout(self.tab_files)
        self.files_list = QListWidget()
        files_layout.addWidget(self.files_list)
        self.tabs.addTab(self.tab_files, "Files")
        
        # Tab 4: Piece Map
        self.tab_piece_map = QWidget()
        piece_map_layout = QVBoxLayout(self.tab_piece_map)
        self.piece_map_widget = PieceMapWidget()
        piece_map_layout.addWidget(self.piece_map_widget)
        self.tabs.addTab(self.tab_piece_map, "Piece Map")
        
        # 5. Bottom Status Bar
        self.statusBar().showMessage("Ready")
        self.lbl_global_speed = QLabel("D: 0 B/s | U: 0 B/s")
        self.lbl_global_peers = QLabel("0 Connections")
        self.statusBar().addPermanentWidget(self.lbl_global_speed)
        self.statusBar().addPermanentWidget(self.lbl_global_peers)

    @pyqtSlot(object)
    def _on_snapshot_received(self, snapshot):
        if self.isHidden():
            return
            
        self.table_model.update_snapshot(snapshot)
        
        # Calculate globals
        total_down = sum(t.get('down_speed', 0) for t in snapshot.torrents.values())
        total_up = sum(t.get('up_speed', 0) for t in snapshot.torrents.values())
        total_peers = sum(t.get('peers_connected', 0) for t in snapshot.torrents.values())
        
        from gui.models import format_size
        self.lbl_global_speed.setText(f"D: {format_size(total_down)}/s | U: {format_size(total_up)}/s")
        self.lbl_global_peers.setText(f"{total_peers} Connections")
        
        # Update details if a row is selected
        if self.current_selected_hash and self.current_selected_hash in snapshot.torrents:
            t = snapshot.torrents[self.current_selected_hash]
            
            # Update General
            self.lbl_info_hash.setText(f"Info Hash: {t.get('info_hash')}")
            self.lbl_save_path.setText(f"Save Path: {t.get('save_path')}")
            self.lbl_piece_size.setText(f"Piece Size: {t.get('piece_size')} bytes")
            self.lbl_total_pieces.setText(f"Total Pieces: {t.get('total_pieces')}")
            
            # Update Peers
            self.peers_model.update_peers(t.get('peers_list', []))
            
            # Update Piece Map
            self.piece_map_widget.update_map(
                t.get('total_pieces', 0), 
                t.get('completed_pieces', [])
            )

    def _on_selection_changed(self, selected, deselected):
        indexes = self.table_view.selectionModel().selectedIndexes()
        if indexes:
            row = indexes[0].row()
            t = self.table_model._torrents[row]
            self.current_selected_hash = t.get('info_hash')
            
            # Populate files right away
            self.files_list.clear()
            for f in t.get('files', []):
                self.files_list.addItem(f"{f['path']} ({f['length']} bytes)")
        else:
            self.current_selected_hash = None
            self.peers_model.update_peers([])
            self.files_list.clear()
            self.lbl_info_hash.setText("Info Hash: ")
            self.lbl_save_path.setText("Save Path: ")

    def _on_add_torrent(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Torrent File", "", "Torrent Files (*.torrent);;All Files (*)")
        if file_path:
            save_path = QFileDialog.getExistingDirectory(self, "Select Save Directory")
            if save_path:
                self.command_queue.put({
                    'action': 'add_torrent',
                    'file_path': file_path,
                    'save_path': save_path
                })

    def _on_add_magnet(self):
        magnet_uri, ok = QInputDialog.getText(self, "Add Magnet Link", "Enter Magnet URI:")
        if ok and magnet_uri.strip().startswith("magnet:?"):
            save_path = QFileDialog.getExistingDirectory(self, "Select Save Directory")
            if save_path:
                self.command_queue.put({
                    'action': 'add_magnet',
                    'magnet_uri': magnet_uri.strip(),
                    'save_path': save_path
                })

    def _get_selected_hash(self):
        indexes = self.table_view.selectionModel().selectedIndexes()
        if indexes:
            row = indexes[0].row()
            t = self.table_model._torrents[row]
            return t.get('info_hash')
        return None

    def _on_pause_torrent(self):
        h = self._get_selected_hash()
        if h:
            self.command_queue.put({'action': 'pause', 'info_hash_hex': h})

    def _on_resume_torrent(self):
        h = self._get_selected_hash()
        if h:
            self.command_queue.put({'action': 'resume', 'info_hash_hex': h})

    def _on_delete_torrent(self):
        h = self._get_selected_hash()
        if h:
            self.command_queue.put({'action': 'delete', 'info_hash_hex': h})
            
    def _on_toggle_stream(self):
        h = self._get_selected_hash()
        if h:
            self.command_queue.put({'action': 'toggle_stream_mode', 'info_hash_hex': h})
