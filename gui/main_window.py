import os
import queue
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QSplitter, QListView, QTabWidget, QHeaderView,
    QProgressBar, QStyledItemDelegate, QStyleOptionProgressBar,
    QApplication, QStyle, QFileDialog, QLabel, QListWidget, QInputDialog,
    QPushButton, QGraphicsDropShadowEffect, QSizePolicy, QSpacerItem, QMenu,
    QDialog, QLineEdit, QPlainTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint
from PyQt6.QtGui import QAction, QIcon, QColor, QPalette, QFont

from gui.models import TorrentListModel, TorrentCardDelegate, PeersTableModel
from gui.piece_map import PieceMapWidget

class MagnetInputDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(500, 200)
        
        self.magnet_uri = ""
        self._setup_ui()
        
    def _setup_ui(self):
        container = QWidget(self)
        container.setFixedSize(500, 200)
        container.setStyleSheet("""
            QWidget {
                background-color: #1A1A1A;
                border: 1px solid #333333;
                border-radius: 8px;
            }
            QLabel {
                color: #EAEAEA;
                font-weight: 600;
                font-size: 14px;
                border: none;
            }
            QLineEdit {
                background-color: #121212;
                border: 1px solid #333333;
                border-radius: 4px;
                color: #EAEAEA;
                padding: 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #555555;
            }
            QPushButton {
                background-color: #2A2A2A;
                border: 1px solid #333333;
                color: #EAEAEA;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #333333;
            }
            QPushButton#PrimaryBtn {
                background-color: #EAEAEA;
                color: #121212;
            }
            QPushButton#PrimaryBtn:hover {
                background-color: #FFFFFF;
            }
        """)
        
        # Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 5)
        container.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Add Magnet Link")
        layout.addWidget(title)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("magnet:?xt=urn:btih:...")
        layout.addWidget(self.input_field)
        
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        btn_add = QPushButton("Add")
        btn_add.setObjectName("PrimaryBtn")
        btn_add.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_add)
        
        layout.addLayout(btn_layout)
        
    def accept(self):
        self.magnet_uri = self.input_field.text().strip()
        super().accept()

class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(15, 10, 15, 10)
        self.setLayout(self.layout)
        self.setFixedHeight(40)
        
        # Branding
        self.brand = QLabel("TorBoar")
        self.brand.setObjectName("BrandLabel")
        self.layout.addWidget(self.brand)
        
        self.layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Controls
        self.btn_minimize = QPushButton("—")
        self.btn_minimize.setObjectName("TitleBtn")
        self.btn_minimize.setFixedSize(24, 24)
        self.btn_minimize.clicked.connect(self.parent.showMinimized)
        self.layout.addWidget(self.btn_minimize)
        
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("TitleBtnClose")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.clicked.connect(self.parent.close)
        self.layout.addWidget(self.btn_close)
        
        self.start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.start_pos:
            delta = event.globalPosition().toPoint() - self.start_pos
            self.parent.move(self.parent.pos() + delta)
            self.start_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.start_pos = None

class MainWindow(QMainWindow):
    snapshot_received = pyqtSignal(object)

    def __init__(self, command_queue: queue.Queue):
        super().__init__()
        self.command_queue = command_queue
        
        # Frameless Window setup
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1100, 700)
        self.setAcceptDrops(True)
        
        # Set global font
        app_font = QFont("Segoe UI", 9)
        app_font.setStyleHint(QFont.StyleHint.SansSerif)
        QApplication.instance().setFont(app_font)
        
        self._setup_ui()
        self._apply_dark_theme()
        
        self.snapshot_received.connect(self._on_snapshot_received)
        self.current_selected_hash = None
        
    def _apply_dark_theme(self):
        dark_stylesheet = """
        /* Main Container */
        QWidget#MainContainer {
            background-color: #121212;
            border: 1px solid #2A2A2A;
            border-radius: 8px;
        }
        
        /* Typography */
        QLabel, QAbstractItemView, QPushButton {
            color: #EAEAEA;
            font-family: "Segoe UI", sans-serif;
        }
        
        /* Title Bar */
        CustomTitleBar {
            background-color: #1A1A1A;
            border-bottom: 1px solid #2A2A2A;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        }
        QLabel#BrandLabel {
            font-size: 12px;
            font-weight: 700;
            color: #888888;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        QPushButton#TitleBtn, QPushButton#TitleBtnClose {
            background: transparent;
            border: none;
            color: #888888;
            font-weight: bold;
            font-size: 10px;
            border-radius: 4px;
        }
        QPushButton#TitleBtn:hover, QPushButton#TitleBtnClose:hover {
            background: #2A2A2A;
            color: #EAEAEA;
        }
        
        /* Sidebar */
        QWidget#Sidebar {
            background-color: #1A1A1A;
            border-right: 1px solid #2A2A2A;
            border-bottom-left-radius: 8px;
        }
        QPushButton.SidebarBtn {
            text-align: left;
            padding: 8px 16px;
            background: transparent;
            border: none;
            color: #888888;
            font-size: 13px;
            font-weight: 500;
            border-radius: 4px;
            margin: 2px 10px;
        }
        QPushButton.SidebarBtn:hover {
            background: #222222;
            color: #EAEAEA;
        }
        QPushButton.SidebarBtn[active="true"] {
            background: #2A2A2A;
            color: #EAEAEA;
            font-weight: 600;
        }
        
        /* Minimalist Action Header */
        QWidget#ActionHeader {
            background-color: transparent;
            border-bottom: 1px solid #2A2A2A;
        }
        QPushButton.ActionBtn {
            background: transparent;
            border: 1px solid #333333;
            color: #EAEAEA;
            padding: 6px 12px;
            font-weight: 500;
            border-radius: 4px;
            font-size: 12px;
        }
        QPushButton.ActionBtn:hover {
            background: #2A2A2A;
        }
        QPushButton.ActionBtnPrimary {
            background: #EAEAEA;
            border: none;
            color: #121212;
            padding: 6px 14px;
            font-weight: 600;
            border-radius: 4px;
            font-size: 12px;
        }
        QPushButton.ActionBtnPrimary:hover {
            background: #FFFFFF;
        }
        
        /* List View (Torrent Cards) */
        QListView {
            background-color: #121212;
            border: none;
            outline: none;
            padding: 10px;
        }
        
        /* Tabs & Splitters */
        QSplitter::handle {
            background-color: #2A2A2A;
        }
        QTabWidget::pane {
            border: 1px solid #2A2A2A;
            background-color: #1A1A1A;
            border-radius: 4px;
            margin-top: -1px;
        }
        QTabBar::tab {
            background-color: #121212;
            color: #888888;
            padding: 8px 16px;
            border: 1px solid #2A2A2A;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            font-weight: 500;
            margin-right: 2px;
            font-size: 12px;
        }
        QTabBar::tab:selected {
            background-color: #2A2A2A;
            color: #EAEAEA;
            border: 1px solid #2A2A2A;
        }
        QTabBar::tab:hover:!selected {
            background-color: #1A1A1A;
            color: #EAEAEA;
        }
        
        /* Status Bar */
        QStatusBar {
            background-color: #1A1A1A;
            color: #888888;
            border-top: 1px solid #2A2A2A;
            font-weight: 500;
            border-bottom-left-radius: 8px;
            border-bottom-right-radius: 8px;
            font-size: 11px;
        }
        """
        self.setStyleSheet(dark_stylesheet)

    def _setup_ui(self):
        # 1. Main Container (Rounded edges)
        self.main_container = QWidget()
        self.main_container.setObjectName("MainContainer")
        self.setCentralWidget(self.main_container)
        
        # Add Drop Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 10)
        self.main_container.setGraphicsEffect(shadow)
        
        main_layout = QVBoxLayout(self.main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 2. Title Bar
        self.title_bar = CustomTitleBar(self)
        main_layout.addWidget(self.title_bar)
        
        # 3. Main Content Area
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        main_layout.addLayout(content_layout)
        
        # 3a. Sidebar
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 15, 0, 0)
        sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        btn_all = QPushButton("All Torrents")
        btn_all.setProperty("class", "SidebarBtn")
        btn_all.setProperty("active", "true")
        
        btn_down = QPushButton("Downloading")
        btn_down.setProperty("class", "SidebarBtn")
        
        btn_comp = QPushButton("Completed")
        btn_comp.setProperty("class", "SidebarBtn")
        
        sidebar_layout.addWidget(btn_all)
        sidebar_layout.addWidget(btn_down)
        sidebar_layout.addWidget(btn_comp)
        
        content_layout.addWidget(sidebar)
        
        # 3b. Dashboard Area
        dashboard_widget = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_widget)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(0)
        content_layout.addWidget(dashboard_widget, 1)
        
        # Minimalist Action Header
        action_header = QWidget()
        action_header.setObjectName("ActionHeader")
        action_header.setFixedHeight(45)
        header_layout = QHBoxLayout(action_header)
        header_layout.setContentsMargins(15, 0, 15, 0)
        
        btn_add_magnet = QPushButton("Add Magnet")
        btn_add_magnet.setProperty("class", "ActionBtnPrimary")
        btn_add_magnet.clicked.connect(self._on_add_magnet)
        
        btn_add_file = QPushButton("Open File")
        btn_add_file.setProperty("class", "ActionBtn")
        btn_add_file.clicked.connect(self._on_add_torrent)
        
        header_layout.addWidget(btn_add_magnet)
        header_layout.addWidget(btn_add_file)
        header_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        dashboard_layout.addWidget(action_header)
        
        # 4. Main Splitter (Torrent Cards vs Piece Map)
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        dashboard_layout.addWidget(right_splitter, 1)

        # 4a. Main Central ListView (Torrent Cards)
        self.table_model = TorrentListModel(self)
        self.table_view = QListView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.table_view.setSpacing(2)
        
        # Apply custom card delegate
        delegate = TorrentCardDelegate(self.table_view)
        # Update colors for delegate to match industrial aesthetic
        delegate.bg_color = QColor("#1A1A1A")
        delegate.bg_hover = QColor("#222222")
        delegate.bg_selected = QColor("#2A2A2A")
        delegate.text_color = QColor("#EAEAEA")
        delegate.text_muted = QColor("#888888")
        delegate.prog_bg = QColor("#121212")
        delegate.prog_chunk1 = QColor("#555555")
        delegate.prog_chunk2 = QColor("#EAEAEA")
        
        self.table_view.setItemDelegate(delegate)
        self.table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        
        # Context Menu
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)
        
        right_splitter.addWidget(self.table_view)
        
        # 4b. Details Pane
        self.tabs = QTabWidget()
        
        # Piece Map Tab
        self.piece_map_widget = PieceMapWidget()
        self.tabs.addTab(self.piece_map_widget, "Piece Map")
        
        # Peers Tab
        peers_tab = QWidget()
        peers_layout = QVBoxLayout(peers_tab)
        self.peers_list = QListWidget()
        self.peers_list.setStyleSheet("background-color: #1A1A1A; border: none; font-size: 12px; color: #EAEAEA;")
        peers_layout.addWidget(self.peers_list)
        self.tabs.addTab(peers_tab, "Peers")
        
        # Console Tab
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: #1A1A1A; border: none; font-family: 'Consolas', 'JetBrains Mono', monospace; font-size: 11px; color: #50FA7B;")
        self.tabs.addTab(self.console, "Console")
        
        right_splitter.addWidget(self.tabs)
        right_splitter.setSizes([500, 150])

        # 5. Status Bar
        self.status_lbl = QLabel(" Ready")
        self.statusBar().addWidget(self.status_lbl)
        self.statusBar().setStyleSheet("border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;")

    # Drag and Drop Events
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.endswith('.torrent'):
                save_path = QFileDialog.getExistingDirectory(self, "Select Save Directory for Dropped Torrent")
                if save_path:
                    self.command_queue.put({
                        'action': 'add_torrent',
                        'file_path': file_path,
                        'save_path': save_path
                    })
        event.accept()

    @pyqtSlot(object)
    def _on_snapshot_received(self, snapshot):
        if self.isHidden():
            return
            
        self.table_model.update_snapshot(snapshot)
        
        # Calculate globals
        total_d = 0
        total_u = 0
        total_peers = 0
        
        for h, dm in snapshot.torrents.items():
            total_d += dm.get('down_speed', 0)
            total_u += dm.get('up_speed', 0)
            total_peers += dm.get('peers_connected', 0)
            
        d_mb = total_d / 1024 / 1024
        u_mb = total_u / 1024 / 1024
        
        self.status_lbl.setText(f" Active Peers: {total_peers}   |   D: {d_mb:.2f} MB/s   |   U: {u_mb:.2f} MB/s")
        
        # Append new logs
        if hasattr(snapshot, 'logs') and snapshot.logs:
            for log_msg in snapshot.logs:
                self.console.appendPlainText(log_msg)
        
        # Update details pane for selected torrent
        h = self.current_selected_hash
        if h and h in snapshot.torrents:
            t = snapshot.torrents[h]
            
            # Update Peers list
            self.peers_list.clear()
            for p in t.get('peers_list', []):
                p_ip = p.get('ip', '')
                p_port = p.get('port', '')
                self.peers_list.addItem(f"Peer: {p_ip}:{p_port}")
            
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
        else:
            self.current_selected_hash = None
            self.peers_list.clear()

    def _show_context_menu(self, position):
        indexes = self.table_view.selectionModel().selectedIndexes()
        if not indexes:
            return
            
        menu = QMenu(self.table_view)
        menu.setStyleSheet("""
            QMenu { 
                background-color: #1A1A1A; 
                color: #EAEAEA; 
                border: 1px solid #333333; 
                border-radius: 4px; 
                padding: 4px;
                font-size: 12px;
            } 
            QMenu::item {
                padding: 6px 20px;
                border-radius: 2px;
            }
            QMenu::item:selected { 
                background-color: #2A2A2A; 
            }
        """)
        
        pause_action = QAction("Pause Torrent", self)
        pause_action.triggered.connect(self._on_pause_torrent)
        menu.addAction(pause_action)
        
        resume_action = QAction("Resume Torrent", self)
        resume_action.triggered.connect(self._on_resume_torrent)
        menu.addAction(resume_action)
        
        menu.addSeparator()
        
        stream_action = QAction("Toggle Stream Mode", self)
        stream_action.triggered.connect(self._on_toggle_stream)
        menu.addAction(stream_action)
        
        menu.addSeparator()
        
        delete_action = QAction("Delete Torrent", self)
        delete_action.triggered.connect(self._on_delete_torrent)
        menu.addAction(delete_action)
        
        menu.exec(self.table_view.viewport().mapToGlobal(position))

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
        dialog = MagnetInputDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.magnet_uri:
            save_path = QFileDialog.getExistingDirectory(self, "Select Save Directory")
            if save_path:
                self.command_queue.put({
                    'action': 'add_magnet',
                    'magnet_uri': dialog.magnet_uri,
                    'save_path': save_path
                })

    def add_magnet_from_args(self, magnet_uri: str):
        save_path = QFileDialog.getExistingDirectory(self, "Select Save Directory for Magnet Link")
        if save_path:
            self.command_queue.put({
                'action': 'add_magnet',
                'magnet_uri': magnet_uri,
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
