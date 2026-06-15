from PyQt6.QtCore import Qt, QAbstractListModel, QAbstractTableModel, QModelIndex, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QLinearGradient
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle
from typing import List, Dict, Any

def format_size(size_bytes: float) -> str:
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(units) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {units[i]}"

class TorrentListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._torrents: List[Dict[str, Any]] = []
        self._info_hashes: List[str] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._torrents)

    def data(self, index, role):
        if not index.isValid():
            return None
            
        row = index.row()
        t = self._torrents[row]
        
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.UserRole:
            return t
            
        return None

    def update_snapshot(self, snapshot):
        self.layoutAboutToBeChanged.emit()
        
        new_torrents = []
        new_hashes = []
        for h, t in snapshot.torrents.items():
            new_torrents.append(t)
            new_hashes.append(h)
            
        self._torrents = new_torrents
        self._info_hashes = new_hashes
        
        self.layoutChanged.emit()

class TorrentCardDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg_color = QColor("#282A36") # Dracula background
        self.bg_hover = QColor("#44475A")
        self.bg_selected = QColor("#6272A4")
        self.text_color = QColor("#F8F8F2")
        self.text_muted = QColor("#6272A4")
        
        self.prog_bg = QColor("#21222C")
        self.prog_chunk1 = QColor("#BD93F9") # Purple
        self.prog_chunk2 = QColor("#8BE9FD") # Cyan

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 100) # Fixed 100px tall cards

    def paint(self, painter, option, index):
        t = index.data(Qt.ItemDataRole.UserRole)
        if not t:
            return

        rect = option.rect
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw Background Card
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setBrush(QBrush(self.bg_selected))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setBrush(QBrush(self.bg_hover))
        else:
            painter.setBrush(QBrush(self.bg_color))
            
        painter.setPen(Qt.PenStyle.NoPen)
        card_rect = rect.adjusted(10, 10, -10, -10)
        painter.drawRoundedRect(card_rect, 10, 10)

        # Draw Text
        painter.setPen(QPen(self.text_color))
        
        # Title (Large, Bold)
        font_title = QFont("Segoe UI", 14, QFont.Weight.Bold)
        painter.setFont(font_title)
        name = t.get('name', 'Unknown')
        if t.get('sequential_mode'):
            name = "[STREAMING] " + name
            
        painter.drawText(card_rect.adjusted(15, 15, -15, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, name)

        # Status & Speed (Smaller, Muted)
        font_sub = QFont("Segoe UI", 10)
        painter.setFont(font_sub)
        painter.setPen(QPen(self.text_muted))
        
        size_str = format_size(t.get('size', 0))
        d_speed = format_size(t.get('down_speed', 0)) + "/s"
        u_speed = format_size(t.get('up_speed', 0)) + "/s"
        status = t.get('status', 'Unknown')
        progress = t.get('progress', 0)
        
        sub_text = f"{status}  |  {size_str}  |  ↓ {d_speed}  |  ↑ {u_speed}"
        painter.drawText(card_rect.adjusted(15, 40, -15, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, sub_text)

        # Draw Progress Bar
        prog_rect = QRect(card_rect.left() + 15, card_rect.bottom() - 20, card_rect.width() - 30, 8)
        painter.setBrush(QBrush(self.prog_bg))
        painter.drawRoundedRect(prog_rect, 4, 4)
        
        if progress > 0:
            chunk_width = int((progress / 100.0) * prog_rect.width())
            chunk_rect = QRect(prog_rect.left(), prog_rect.top(), chunk_width, prog_rect.height())
            
            grad = QLinearGradient(chunk_rect.topLeft(), chunk_rect.topRight())
            grad.setColorAt(0.0, self.prog_chunk1)
            grad.setColorAt(1.0, self.prog_chunk2)
            
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(chunk_rect, 4, 4)

class PeersTableModel(QAbstractTableModel):
    HEADERS = ["IP", "Port", "Client", "Flags", "Down Speed", "Up Speed"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._peers: List[Dict[str, Any]] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._peers)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def data(self, index, role):
        if not index.isValid():
            return None
            
        row = index.row()
        col = index.column()
        p = self._peers[row]
        
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0: return p.get('ip', '')
            elif col == 1: return p.get('port', '')
            elif col == 2: return p.get('client', 'Unknown')
            elif col == 3: return p.get('flags', '')
            elif col == 4: return format_size(p.get('down_speed', 0)) + "/s"
            elif col == 5: return format_size(p.get('up_speed', 0)) + "/s"
            
        return None

    def headerData(self, section, orientation, role):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def update_peers(self, peers: List[Dict[str, Any]]):
        self.beginResetModel()
        self._peers = peers
        self.endResetModel()
