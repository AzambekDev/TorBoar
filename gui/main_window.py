import os
import queue
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QSplitter, QListView, QTabWidget, QHeaderView,
    QProgressBar, QStyledItemDelegate, QStyleOptionProgressBar,
    QApplication, QStyle, QFileDialog, QLabel, QListWidget, QInputDialog,
    QPushButton, QGraphicsDropShadowEffect, QSizePolicy, QSpacerItem, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint
from PyQt6.QtGui import QAction, QIcon, QColor, QPalette, QFont

from gui.models import TorrentListModel, TorrentCardDelegate, PeersTableModel
from gui.piece_map import PieceMapWidget

class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(15, 10, 15, 10)
        self.setLayout(self.layout)
        self.setFixedHeight(50)
        
        # Branding
        self.brand = QLabel("TorBoar")
        self.brand.setObjectName("BrandLabel")
        self.layout.addWidget(self.brand)
        
        self.layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Controls
        self.btn_minimize = QPushButton("—")
        self.btn_minimize.setObjectName("TitleBtn")
        self.btn_minimize.setFixedSize(30, 30)
        self.btn_minimize.clicked.connect(self.parent.showMinimized)
        self.layout.addWidget(self.btn_minimize)
        
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("TitleBtnClose")
        self.btn_close.setFixedSize(30, 30)
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
        
        # Set global font
        app_font = QFont("Segoe UI", 10)
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
            background-color: #282A36;
            border: 1px solid #44475A;
            border-radius: 12px;
        }
        
        /* Typography */
        QLabel, QAbstractItemView, QPushButton {
            color: #F8F8F2;
            font-family: "Segoe UI", sans-serif;
        }
        
        /* Title Bar */
        CustomTitleBar {
            background-color: transparent;
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        }
        QLabel#BrandLabel {
            font-size: 20px;
            font-weight: 900;
            color: #FF79C6;
            letter-spacing: 2px;
        }
        QPushButton#TitleBtn, QPushButton#TitleBtnClose {
            background: transparent;
            border: none;
            color: #6272A4;
            font-weight: bold;
            font-size: 14px;
            border-radius: 6px;
        }
        QPushButton#TitleBtn:hover {
            background: #44475A;
            color: #F8F8F2;
        }
        QPushButton#TitleBtnClose:hover {
            background: #FF5555;
            color: white;
        }
        
        /* Sidebar */
        QWidget#Sidebar {
            background-color: #21222C;
            border-right: 1px solid #44475A;
            border-bottom-left-radius: 12px;
        }
        QPushButton.SidebarBtn {
            text-align: left;
            padding: 12px 20px;
            background: transparent;
            border: none;
            color: #6272A4;
            font-size: 14px;
            font-weight: bold;
            border-radius: 8px;
            margin: 5px 10px;
        }
        QPushButton.SidebarBtn:hover {
            background: #44475A;
            color: #F8F8F2;
        }
        QPushButton.SidebarBtn[active="true"] {
            background: #6272A4;
            color: #F8F8F2;
        }
        
        /* Action Pill */
        QWidget#ActionPill {
            background-color: #21222C;
            border: 1px solid #44475A;
            border-radius: 20px;
        }
        QPushButton.ActionBtn {
            background: transparent;
            border: none;
            color: #F8F8F2;
            padding: 8px 15px;
            font-weight: bold;
            border-radius: 15px;
        }
        QPushButton.ActionBtn:hover {
            background: #44475A;
        }
        QPushButton.ActionBtnPrimary {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #BD93F9, stop:1 #FF79C6);
            border: none;
            color: #282A36;
            padding: 8px 20px;
            font-weight: 900;
            border-radius: 15px;
        }
        QPushButton.ActionBtnPrimary:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF79C6, stop:1 #BD93F9);
        }
        
        /* List View (Torrent Cards) */
        QListView {
            background-color: #282A36;
            border: none;
            outline: none;
            padding: 10px;
        }
        
        /* Tabs & Splitters */
        QSplitter::handle {
            background-color: #44475A;
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
        
        /* Status Bar */
        QStatusBar {
            background-color: #21222C;
            color: #6272A4;
            border-top: 1px solid #44475A;
            font-weight: bold;
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
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
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 5)
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
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 20, 0, 0)
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
        dashboard_layout.setContentsMargins(20, 10, 20, 20)
        dashboard_layout.setSpacing(15)
        content_layout.addWidget(dashboard_widget, 1)
        
        # Action Pill (Replaces ToolBar)
        action_pill = QWidget()
        action_pill.setObjectName("ActionPill")
        action_pill.setFixedHeight(50)
        pill_layout = QHBoxLayout(action_pill)
        pill_layout.setContentsMargins(10, 0, 10, 0)
        
        btn_add_magnet = QPushButton("+ Add Magnet")
        btn_add_magnet.setProperty("class", "ActionBtnPrimary")
        btn_add_magnet.clicked.connect(self._on_add_magnet)
        
        btn_add_file = QPushButton("Add File")
        btn_add_file.setProperty("class", "ActionBtn")
        btn_add_file.clicked.connect(self._on_add_torrent)
        pill_layout.addWidget(btn_add_magnet)
        pill_layout.addWidget(btn_add_file)
        pill_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        dashboard_layout.addWidget(action_pill)
        
        # 4. Main Splitter (Torrent Cards vs Piece Map)
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        dashboard_layout.addWidget(right_splitter, 1)

        # 4a. Main Central ListView (Torrent Cards)
        self.table_model = TorrentListModel(self)
        self.table_view = QListView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.table_view.setSpacing(5)
        
        # Apply custom card delegate
        delegate = TorrentCardDelegate(self.table_view)
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
        # Using a simple QListView for peers or reusing the old TableModel...
        # Wait, the old one was a QTableView, let's keep it simple for now as a QListView of strings to fit the modern UI
        self.peers_list = QListWidget()
        self.peers_list.setStyleSheet("background-color: #21222C; border: none;")
        peers_layout.addWidget(self.peers_list)
        self.tabs.addTab(peers_tab, "Peers")
        
        right_splitter.addWidget(self.tabs)
        right_splitter.setSizes([400, 200])

        # 5. Status Bar
        self.status_lbl = QLabel(" Ready")
        self.statusBar().addWidget(self.status_lbl)
        self.statusBar().setStyleSheet("border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;")

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
                background-color: #21222C; 
                color: #F8F8F2; 
                border: 1px solid #44475A; 
                border-radius: 6px; 
                padding: 5px;
            } 
            QMenu::item {
                padding: 8px 25px;
                border-radius: 4px;
            }
            QMenu::item:selected { 
                background-color: #44475A; 
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
