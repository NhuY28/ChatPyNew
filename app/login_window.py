import os
from http import client

from PyQt5 import QtWidgets, QtCore, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QMessageBox

from app.chat_window import ChatWindow
from backend.chatclient import ChatClient
from PyQt5.QtCore import Qt

class LoginWindow(QtWidgets.QMainWindow):
    server_message_signal = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        from ui.ui_login import Ui_LoginWindow
        self.ui = Ui_LoginWindow()
        self.ui.setupUi(self)

        # ====== LOAD LOGO ======
        base_path = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_path, "..", "logo.png")  # lên 1 thư mục
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path)

            # Scale logo vừa với label, giữ tỉ lệ
            label_width = self.ui.logoLabel.width()
            label_height = self.ui.logoLabel.height()
            pix = pix.scaled(label_width, label_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            self.ui.logoLabel.setPixmap(pix)
            self.ui.logoLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)  # Căn giữa ngang + dọc
            self.ui.logoLabel.setMinimumSize(label_width, label_height)        # Giữ kích thước label
        else:
            print("⚠️ Không tìm thấy logo.png tại:", logo_path)

        self.client = ChatClient()
        self.server_message_signal.connect(self.handle_server_message)

        # Nút login/register
        self.ui.signInButton.clicked.connect(self.do_login)
        self.ui.signUpButton.clicked.connect(self.open_register)

    def do_login(self):
        username = self.ui.nameInput.text().strip()
        password = self.ui.passwordInput.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập đầy đủ tên và mật khẩu!")
            return

        try:
            # tạo cửa sổ chat với instance client
            chat_win = ChatWindow(username=username, client=self.client)

            # gắn callback đúng cách
            self.client.on_message = chat_win.handle_client_message

            # kết nối và login
            self.client.connect()
            self.client.login(username, password)

            # show chat window
            chat_win.show()
            self.hide()

        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể kết nối tới server: {e}")

    def handle_server_message(self, message):
        try:
            if "LOGIN_OK" in message:
                QMessageBox.information(self, "Thành công", "Đăng nhập thành công!")
                try:
                    self.open_chat_window()
                except Exception as e:
                    QMessageBox.critical(self, "Lỗi", f"Không mở được giao diện chat: {e}")
            elif "LOGIN_FAIL" in message:
                QMessageBox.warning(self, "Lỗi", "Tên hoặc mật khẩu không đúng!")
        except Exception as e:
            print(f"[HANDLE SERVER MSG ERROR] {e}")

    def open_chat_window(self):
        try:
            from app.chat_window import ChatWindow
            self.chat_window = ChatWindow(username=self.ui.nameInput.text().strip(), client=self.client)
            self.chat_window.show()
            self.hide()
        except Exception as e:
            raise e

    def open_register(self):
        try:
            from app.register_window import RegisterWindow
            self.register_window = RegisterWindow()
            self.register_window.show()
            self.hide()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không mở được giao diện đăng ký: {e}")
