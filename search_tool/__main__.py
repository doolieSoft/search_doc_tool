import sys
from PyQt6.QtWidgets import QApplication
from search_tool.ui.styles import STYLESHEET
from search_tool.ui.app import SearchApp


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = SearchApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
