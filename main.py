# main.py
from PyQt5 import QtWidgets
from app.login_window import LoginWindow
import sys

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = LoginWindow()  # Bắt đầu từ giao diện đăng nhập
    window.show()
    sys.exit(app.exec_())
