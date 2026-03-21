import os
import re

from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QVariant, QRectF, QSize
from PyQt6.QtGui import QColor, QPainter, QTextDocument, QFont

from .styles import (
    BG_ROW_ODD, BG_ROW_EVEN, BG_ROW_SEL, TEXT_PRIMARY, HIGHLIGHT, RED
)


class ResultsModel(QAbstractTableModel):
    HEADERS = ["Fichier", "Terme", "Contexte"]

    def __init__(self):
        super().__init__()
        self._data: list[dict] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return 3

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data):
            return QVariant()
        row = self._data[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return [os.path.basename(row["file"]), row["term"], row["context"]][col]
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == 0:
                return row["file"]
            if col == 2:
                return row["context"]
        if role == Qt.ItemDataRole.UserRole:
            return row
        if role == Qt.ItemDataRole.BackgroundRole:
            if row.get("term") == "ERREUR":
                return QColor("#3A1A1A")
            return QColor(BG_ROW_ODD if index.row() % 2 == 0 else BG_ROW_EVEN)
        if role == Qt.ItemDataRole.ForegroundRole:
            if row.get("term") == "ERREUR":
                return QColor(RED)
            return QColor(TEXT_PRIMARY)
        return QVariant()

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return QVariant()

    def add_result(self, r: dict):
        row = len(self._data)
        self.beginInsertRows(QModelIndex(), row, row)
        self._data.append(r)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def get_row(self, idx: int) -> dict:
        return self._data[idx] if idx < len(self._data) else {}

    def all_results(self):
        return list(self._data)


class ContextDelegate(QStyledItemDelegate):
    """Colonne Contexte : affiche les [termes] en gras et en couleur."""

    def _make_doc(self, text: str, font: QFont, width: int) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setTextWidth(width)
        html = re.sub(
            r'\[([^\]]+)\]',
            rf'<b><span style="color:{HIGHLIGHT};">\1</span></b>',
            re.sub(r'&', '&amp;', re.sub(r'<', '&lt;', text))
        )
        doc.setHtml(f'<span style="color:{TEXT_PRIMARY};">{html}</span>')
        return doc

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        if index.column() != 2:
            super().paint(painter, option, index)
            return
        painter.save()
        bg = index.data(Qt.ItemDataRole.BackgroundRole)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if is_selected:
            painter.fillRect(option.rect, QColor(BG_ROW_SEL))
        else:
            painter.fillRect(option.rect, bg or QColor(BG_ROW_ODD))
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        doc = self._make_doc(text, option.font, option.rect.width() - 16)
        painter.translate(option.rect.left() + 8, option.rect.top() + 4)
        clip = QRectF(0, 0, option.rect.width() - 16, option.rect.height() - 8)
        doc.drawContents(painter, clip)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        if index.column() != 2:
            return super().sizeHint(option, index)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        doc = self._make_doc(text, option.font, option.rect.width() - 16 or 500)
        return QSize(int(doc.idealWidth()) + 16, min(int(doc.size().height()) + 8, 80))
