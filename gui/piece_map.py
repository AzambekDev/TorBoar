import math
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QRect

class PieceMapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.total_pieces = 0
        self.completed_pieces = set()
        
        # Monochromatic Pro Palette
        self.color_bg = QColor("#121212")
        self.color_missing = QColor("#2A2A2A")
        self.color_have = QColor("#EAEAEA")
        self.color_border = QColor("#1A1A1A")
        
        self.setMinimumHeight(200)

    def update_map(self, total_pieces: int, completed_pieces: list):
        self.total_pieces = total_pieces
        self.completed_pieces = set(completed_pieces)
        self.update() # Trigger a repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Fill background
        painter.fillRect(self.rect(), self.color_bg)
        
        if self.total_pieces <= 0:
            return
            
        width = self.width()
        height = self.height()
        
        # Calculate best square size based on available area and total pieces
        area = width * height
        square_area = area / max(1, self.total_pieces)
        square_size = max(4, int(math.sqrt(square_area)))
        
        # Add a tiny gap
        gap = max(1, square_size // 5)
        box_size = max(1, square_size - gap)
        
        cols = max(1, width // square_size)
        
        # Pre-calculate offsets to center the grid
        grid_width = cols * square_size
        offset_x = (width - grid_width) // 2
        
        # Draw all pieces
        for i in range(self.total_pieces):
            col = i % cols
            row = i // cols
            
            x = offset_x + col * square_size + gap
            y = row * square_size + gap
            
            if i in self.completed_pieces:
                painter.fillRect(x, y, box_size, box_size, self.color_have)
            else:
                painter.fillRect(x, y, box_size, box_size, self.color_missing)
            
            painter.setPen(self.color_border)
            painter.drawRect(x, y, box_size, box_size)
