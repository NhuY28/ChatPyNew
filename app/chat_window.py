import base64, os
from PyQt5 import QtWidgets, QtCore, QtGui
from backend.chatclient import ChatClient
from ui.chat_window import Ui_ChatWindow
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QBrush, QPen
from PyQt5.QtWidgets import QInputDialog, QListWidget, QPushButton, QVBoxLayout, QDialog, QLabel, QHBoxLayout, QWidget
from PyQt5.QtWidgets import QFileDialog, QMessageBox
import shutil
import sounddevice as sd
from scipy.io.wavfile import write
import tempfile
import threading
import numpy as np
from PyQt5.QtWidgets import QMessageBox
from PyQt5 import QtCore
from app.VoiceCall import VoiceCall
from app.VideoCall import VideoCall
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QMessageBox, QDialog
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QStyledItemDelegate
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtCore import QRect, Qt

class BadgeDelegate(QStyledItemDelegate):
    """
    Delegate vẽ badge thông báo chưa đọc:
    - Nền đỏ (#FF4C4C)
    - Chữ trắng
    - Oval dài theo chữ
    """
    def __init__(self, unread_dict, parent=None):
        super().__init__(parent)
        self.unread = unread_dict  # dict lưu số tin nhắn chưa đọc
        self.all_users = {}  # lưu tất cả user: username -> avatar
        self.online_users = set()  # lưu username online

    def paint(self, painter, option, index):
        # vẽ item mặc định (text, icon)
        super().paint(painter, option, index)

        # lấy key để lookup unread_counts
        key = index.data(Qt.UserRole)
        if key is None:
            key = index.data(Qt.DisplayRole).split(" (")[0]

        count = self.unread.get(key, 0)
        if not count:
            return

        display_count = str(count) if count < 100 else "99+"

        # font chữ trong badge
        font = QFont("Arial", 9, QFont.Bold)
        painter.setFont(font)
        painter.setRenderHint(QPainter.Antialiasing)

        fm = painter.fontMetrics()
        text_width = fm.width(display_count)
        badge_width = max(20, text_width + 12)  # rộng theo chữ
        badge_height = 18

        r = option.rect
        x = r.right() - badge_width - 10  # 10px cách mép phải
        y = r.center().y() - badge_height // 2

        # vẽ oval đỏ
        painter.setBrush(QColor("#FF4C4C"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRect(x, y, badge_width, badge_height), badge_height / 2, badge_height / 2)

        # vẽ chữ trắng
        painter.setPen(Qt.white)
        painter.drawText(QRect(x, y, badge_width, badge_height), Qt.AlignCenter, display_count)

class ChatWindow(QtWidgets.QMainWindow):
    new_message = QtCore.pyqtSignal(str, str, str)  # target, sender, message
    update_users_signal = QtCore.pyqtSignal(list)
    update_groups_signal = QtCore.pyqtSignal(list)
    show_message_signal = QtCore.pyqtSignal(str, str, str)
    incoming_call_signal = QtCore.pyqtSignal(str)  # caller username
    incoming_video_signal = QtCore.pyqtSignal(str)  # caller username for video

    def __init__(self, username="username", client=None):
        super().__init__()
        self.ui = Ui_ChatWindow()
        self.ui.setupUi(self)

        self.username = username
        # --- TẠO CLIENT nếu chưa có ---
        if client is None:
            self.client = ChatClient(gui_parent=self)
        else:
            self.client = client
            self.client.gui_parent = self  # đảm bảo gui_parent gán đúng

        # --- GẮN CALLBACK để chạy trên GUI thread ---
        self.client.on_message = lambda msg: QtCore.QTimer.singleShot(0, lambda: self.handle_client_message(msg))

        self.ui.userLabel.setText(f"Xin chào, {self.username}")

        # Lưu tin nhắn và số tin nhắn chưa đọc
        self.conversations = {}  # key: target (user/group/public), value: list of (sender, message)
        self.unread_counts = {}  # key: target, value: số tin nhắn chưa đọc
        self.avatars = {}  # key: username, value: đường dẫn avatar

        self.setup_signals()

        self.load_users_from_db()

        # Tạo delegate
        self.user_delegate = BadgeDelegate(self.unread_counts, self.ui.userList)
        self.group_delegate = BadgeDelegate(self.unread_counts, self.ui.groupList)

        # Gán delegate
        self.ui.userList.setItemDelegate(self.user_delegate)
        self.ui.groupList.setItemDelegate(self.group_delegate)

        # Kết nối signal
        self.new_message.connect(self.store_message_signal)
        self.update_users_signal.connect(self.update_user_list)
        self.update_groups_signal.connect(self.update_group_list)
        self.show_message_signal.connect(self.show_message_box)
        self.incoming_call_signal.connect(self.show_incoming_call_popup)

        # --- FIX layout bị giãn ---
        self.chat_container = QtWidgets.QWidget()
        self.chat_container.setLayout(self.ui.chatMessages)
        self.chat_container.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.ui.scrollArea.setWidget(self.chat_container)
        self.ui.scrollArea.setWidgetResizable(True)

        # Giữ tin nhắn bám lên trên, khoảng cách đều
        self.ui.chatMessages.setAlignment(QtCore.Qt.AlignTop)
        self.ui.chatMessages.setSpacing(5)

        self.current_call = None

        self.all_users = {}  # username -> avatar
        self.online_users = set()  # danh sách username online

        self.incoming_video_signal.connect(self.show_incoming_video_popup)

    # ------------------- Signal và sự kiện nút -------------------
    def setup_signals(self):
        self.ui.btnCreateGroup.clicked.connect(self.create_group)
        self.ui.btnImage.clicked.connect(self.send_image)
        self.ui.btnFile.clicked.connect(self.send_file)
        self.ui.btnVoice.clicked.connect(self.send_voice)
        self.ui.btnCall.clicked.connect(self.start_voice_call)
        self.ui.btnVideo.clicked.connect(self.start_video_call)
        self.ui.btnLeaveGroup.clicked.connect(self.leave_group)
        self.ui.messageInput.returnPressed.connect(self.send_text_message)

        # Khi chọn user hoặc group, refresh chat
        self.ui.userList.itemClicked.connect(self.on_user_selected)
        self.ui.groupList.itemClicked.connect(self.on_group_selected)

    # ------------------- Nhận dữ liệu từ client -------------------
    def handle_client_message(self, msg):
        parts = msg.split("|")
        cmd = parts[0]

        if msg.startswith("USER_LIST|"):
            parts = msg[len("USER_LIST|"):].split("|")
            self.online_users = set()
            for p in parts:
                if ":" in p:
                    username, avatar = p.split(":", 1)
                else:
                    username, avatar = p, "avatars/default.jpg"

                if not avatar:
                    avatar = "avatars/default.jpg"

                self.all_users[username] = avatar  # vẫn lưu vào all_users
                self.online_users.add(username)

            # Gọi cập nhật giao diện
            self.update_user_list()

        elif msg.startswith("ALL_USERS|"):
            parts = msg[len("ALL_USERS|"):].split("|")
            for p in parts:
                if ":" in p:
                    username, avatar = p.split(":", 1)
                else:
                    username, avatar = p, "avatars/default.jpg"
                if not avatar:
                    avatar = "avatars/default.jpg"
                self.all_users[username] = avatar  # lưu tất cả user
            # sau khi cập nhật all_users, gọi update_user_list
            self.update_user_list()

        elif msg.startswith("GROUP_LIST|"):
            parts = msg[len("GROUP_LIST|"):].split("|")
            groups = [g for g in parts if g.strip()]
            self.update_groups_signal.emit(groups)

        elif msg.startswith("GROUP_CREATE_OK|"):
            group_name = msg[len("GROUP_CREATE_OK|"):].strip()
            self.show_message_signal.emit("info", "Thành công", f"Bạn đã tạo nhóm '{group_name}' thành công!")
            if self.client:
                self.client.request_group_list()

        elif msg.startswith("GROUP_CREATE_FAIL|"):
            error_msg = msg[len("GROUP_CREATE_FAIL|"):].strip()
            self.show_message_signal.emit("warn", "Thất bại", f"Tạo nhóm thất bại: {error_msg}")

        elif msg.startswith("MSG|"):
            parts = msg.split("|", 2)
            if len(parts) == 3:
                sender, text = parts[1], parts[2]
                self.new_message.emit("public", sender, text)

        elif msg.startswith("PRIVATE|"):
            parts = msg.split("|", 2)
            if len(parts) == 3:
                sender, text = parts[1], parts[2]

                if sender == self.username:
                    # Tin nhắn do mình gửi -> target là người nhận cuối cùng
                    target = getattr(self.client, 'last_private_target', self.get_current_target())
                else:
                    # Tin nhắn do người khác gửi -> target là sender
                    target = sender

                self.new_message.emit(target, sender, text)

        elif msg.startswith("GROUP_MSG|"):
            parts = msg.split("|", 3)
            if len(parts) == 4:
                group_name, sender, text = parts[1], parts[2], parts[3]
                # Hỗ trợ nhận ảnh/file
                self.new_message.emit(group_name, sender, text)

        elif cmd == "IMG":
            sender, filename, b64 = parts[1], parts[2], parts[3]
            save_dir = "received_files"
            os.makedirs(save_dir, exist_ok=True)
            filepath = os.path.join(save_dir, filename)

            try:
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(b64))

                # Xác định target
                if sender != self.username:
                    target = sender
                else:
                    target = self.get_current_target()

                self.new_message.emit(target, sender, f"[IMAGE]{filepath}")
            except Exception as e:
                print("[IMAGE ERROR]", e)

        elif cmd == "FILE":
            sender, filename, b64 = parts[1], parts[2], parts[3]
            save_dir = "received_files"
            os.makedirs(save_dir, exist_ok=True)
            filepath = os.path.join(save_dir, filename)

            try:
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(b64))

                if sender != self.username:
                    target = sender
                else:
                    target = self.get_current_target()

                self.new_message.emit(target, sender, f"[FILE]{filepath}")
            except Exception as e:
                print("[FILE ERROR]", e)

        elif cmd == "VOICE":
            sender, filename, b64 = parts[1], parts[2], parts[3]
            save_dir = "received_files"
            os.makedirs(save_dir, exist_ok=True)
            filepath = os.path.join(save_dir, filename)

            try:
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(b64))

                if sender != self.username:
                    target = sender
                else:
                    target = self.get_current_target()

                self.new_message.emit(target, sender, f"[VOICE]{filepath}")
            except Exception as e:
                print("[VOICE ERROR]", e)

        elif cmd == "GROUP_IMG":
            group_name, sender, filename, b64 = parts[1], parts[2], parts[3], parts[4]
            save_dir = os.path.join("received_files", group_name)
            os.makedirs(save_dir, exist_ok=True)
            filepath = os.path.join(save_dir, filename)
            try:
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(b64))
                self.new_message.emit(group_name, sender, f"[IMAGE]{filepath}")
            except Exception as e:
                print("[GROUP_IMG ERROR]", e)

        elif cmd == "GROUP_FILE":
            group_name, sender, filename, b64 = parts[1], parts[2], parts[3], parts[4]
            save_dir = os.path.join("received_files", group_name)
            os.makedirs(save_dir, exist_ok=True)
            filepath = os.path.join(save_dir, filename)
            try:
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(b64))
                self.new_message.emit(group_name, sender, f"[FILE]{filepath}")
            except Exception as e:
                print("[GROUP_FILE ERROR]", e)

        if msg.startswith("CALL_REQUEST|"):
            _, caller = msg.split("|", 1)

            # Nếu đã có cuộc gọi đang diễn ra với caller, bỏ qua
            if hasattr(self, "current_call") and self.current_call:
                if self.current_call.is_calling or (getattr(self.current_call, 'incoming', False) and self.current_call.target_user == caller):
                    return

            self.incoming_call_signal.emit(caller)
            return

        elif msg.startswith("CALL_ACCEPT|"):
            if self.current_call and not self.current_call.is_calling:
                # CHỈ BÊN GỌI mới start()
                if not self.current_call.incoming:
                    self.current_call.start()

        elif msg.startswith("CALL_STREAM|"):
            try:
                _, sender, b64 = msg.split("|", 2)
            except ValueError:
                return
            if self.current_call and self.current_call.target_user.strip() == sender.strip():
                self.current_call.receive_audio(b64)

        elif msg.startswith("CALL_END|"):
            try:
                _, who = msg.split("|", 1)
            except ValueError:
                return
            if hasattr(self, "current_call") and self.current_call:
                self.current_call.end()

        # VIDEO request
        elif msg.startswith("VIDEO_REQUEST|"):
            _, caller = msg.split("|", 1)
            # emit incoming video signal
            self.incoming_video_signal.emit(caller)
            return

        elif msg.startswith("VIDEO_ACCEPT|"):
            _, acceptor = msg.split("|", 1)
            if hasattr(self, "current_video_call") and self.current_video_call and not self.current_video_call.incoming:
                self.current_video_call.accept_and_start()
                self.current_video_call.show()

        elif msg.startswith("VIDEO_STREAM|"):
            try:
                _, sender, b64_video, b64_audio = msg.split("|", 3)
            except ValueError:
                # maybe audio empty or missing - try split 2 parts
                try:
                    _, sender, b64_video = msg.split("|", 2)
                    b64_audio = ""
                except Exception:
                    return
            # deliver to current_video_call if matches sender
            if hasattr(self, "current_video_call") and self.current_video_call and self.current_video_call.target_user.strip() == sender.strip():
                # push to videocall for display
                QtCore.QTimer.singleShot(
                    0,
                    lambda v=b64_video, a=b64_audio:
                    self.current_video_call.receive_remote_frame(v, a)
                )

        elif msg.startswith("VIDEO_END|"):
            try:
                _, who = msg.split("|", 1)
            except ValueError:
                return
            if hasattr(self, "current_video_call") and self.current_video_call:
                self.current_video_call.end()

        else:
            # Nếu không biết lệnh, in ra debug
            print("[UNKNOWN CMD]", msg)
    # ------------------- Lưu tin nhắn -------------------
    def store_message_signal(self, target, sender, message):
        if target not in self.conversations:
            self.conversations[target] = []
        self.conversations[target].append((sender, message))

        current_target = getattr(self, 'current_chat_user', None)
        if current_target == target:
            self.refresh_chat_display(target)
            self.unread_counts[target] = 0
        else:
            # tăng số tin nhắn chưa đọc
            self.unread_counts[target] = self.unread_counts.get(target, 0) + 1

            # cập nhật badge bằng cách repaint list
            self.ui.userList.viewport().update()
            self.ui.groupList.viewport().update()

    def update_chat_header(self, target, is_group=False):
        # --- Tăng cỡ chữ ---
        font = QFont("Segoe UI", 20, QFont.Bold)
        self.ui.chatTitle.setFont(font)

        # --- Trường hợp "chat chung" ---
        if target.lower() == "chat chung":
            self.ui.chatTitle.setText("Chat chung")
            self.ui.chatAvatar.setVisible(False)
            return
        else:
            self.ui.chatTitle.setText(target)
            self.ui.chatAvatar.setVisible(True)

        # --- Xác định avatar ---
        if is_group:
            avatar_path = "avatars/group_default.jpg"
        else:
            avatar_path = self.avatars.get(target, "avatars/default.jpg")

        if not os.path.exists(avatar_path):
            avatar_path = "avatars/default.jpg"

        pixmap = QPixmap(avatar_path)
        if pixmap.isNull():
            pixmap = QPixmap("avatars/default.jpg")

        # --- Resize avatar ---
        avatar_size = 60
        pixmap = pixmap.scaled(avatar_size, avatar_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

        # --- Tạo QPixmap tròn, **không cần background QLabel** ---
        rounded = QPixmap(avatar_size, avatar_size)
        rounded.fill(Qt.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QtGui.QPainterPath()
        path.addEllipse(0, 0, avatar_size, avatar_size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)

        # --- Vẽ chấm online/offline nếu là user ---
        if not is_group:
            dot_size = 10
            dot_x = avatar_size - dot_size - 2
            dot_y = avatar_size - dot_size - 2
            if target in self.online_users:
                painter.setBrush(QBrush(Qt.green))
            else:
                painter.setBrush(QBrush(Qt.gray))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(dot_x, dot_y, dot_size, dot_size)

        painter.end()
        self.ui.chatAvatar.setPixmap(rounded)

        # --- Bỏ background QLabel nếu còn ---
        self.ui.chatAvatar.setStyleSheet("background: transparent;")


    # ------------------- Hiển thị MessageBox -------------------
    def show_message_box(self, type_, title, text):
        if type_ == "info":
            QtWidgets.QMessageBox.information(self, title, text)
        elif type_ == "warn":
            QtWidgets.QMessageBox.warning(self, title, text)

    def load_users_from_db(self):
        """
        Yêu cầu server gửi danh sách user.
        Server trả về USER_LIST|username:avatar|... và handle_client_message
        sẽ cập nhật userList, avatar và online status.
        """
        if self.client:
            try:
                # Gửi yêu cầu danh sách user tới server
                self.client.request_user_list()
            except Exception as e:
                print("❌ Lỗi khi yêu cầu danh sách user từ server:", e)

    # ------------------- Cập nhật danh sách user -------------------
    def update_user_list(self):
        self.ui.userList.clear()
        self.ui.userList.setIconSize(QtCore.QSize(40, 40))
        self.ui.userList.setSpacing(5)

        for username, avatar_path in self.all_users.items():
            if username == self.username:
                continue  # bỏ qua bản thân

            item = QtWidgets.QListWidgetItem(username)
            item.setSizeHint(QtCore.QSize(200, 50))
            item.setData(Qt.UserRole, username)

            if not avatar_path or not os.path.exists(avatar_path):
                avatar_path = "avatars/default.jpg"
            self.avatars[username] = avatar_path

            pixmap = QPixmap(avatar_path).scaled(40, 40, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            size = min(pixmap.width(), pixmap.height())
            rounded = QPixmap(size, size)
            rounded.fill(Qt.transparent)

            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QBrush(pixmap))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(0, 0, size, size)

            # Vẽ chấm trạng thái
            dot_size = 10
            dot_x = size - dot_size - 2
            dot_y = size - dot_size - 2

            if username in self.online_users:
                painter.setBrush(QBrush(Qt.green))
            else:
                painter.setBrush(QBrush(Qt.gray))  # offline màu xám

            painter.setPen(Qt.NoPen)
            painter.drawEllipse(dot_x, dot_y, dot_size, dot_size)

            painter.end()
            item.setIcon(QIcon(rounded))
            self.ui.userList.addItem(item)

        # repaint để badge hiển thị đúng
        self.ui.userList.viewport().update()

    def update_group_list(self, groups):
        self.ui.groupList.clear()
        for group_name in groups:
            if group_name.strip():
                item = QtWidgets.QListWidgetItem(group_name)

                # Lưu key thực sự
                item.setData(Qt.UserRole, group_name)
                self.ui.groupList.addItem(item)

        # repaint để badge hiển thị
        self.ui.groupList.viewport().update()

    # ------------------- Cập nhật label target với số tin nhắn chưa đọc -------------------
    def update_target_labels(self):
        # User
        for i in range(self.ui.userList.count()):
            item = self.ui.userList.item(i)
            target = item.text().split(" (")[0]  # giữ nguyên text
            # badge sẽ được vẽ bằng delegate dựa trên self.unread_counts[target]

        # Group
        for i in range(self.ui.groupList.count()):
            item = self.ui.groupList.item(i)
            target = item.text().split(" (")[0]
            # badge sẽ được vẽ bằng delegate
        # repaint list để cập nhật badge
        self.ui.userList.viewport().update()
        self.ui.groupList.viewport().update()

    # ------------------- Khi chọn user -------------------
    def on_user_selected(self, item):
        print("CLICK USER:", item.text())
        self.ui.groupList.clearSelection()
        target = item.text().split(" (")[0]
        self.current_chat_user = target
        self.unread_counts[target] = 0
        self.refresh_chat_display(target)
        self.update_chat_header(target, is_group=False)
        self.ui.userList.viewport().update()
        self.ui.groupList.viewport().update()

        self.ui.btnCall.show()
        self.ui.btnVideo.show()
        self.ui.btnLeaveGroup.hide()  # ẩn nút rời nhóm
        self.ui.userList.viewport().update()
        self.ui.groupList.viewport().update()
    # ------------------- Khi chọn group -------------------
    def on_group_selected(self, item):
        print("CLICK GROUP:", item.text())
        self.ui.userList.clearSelection()
        target = item.text().split(" (")[0]
        self.current_chat_user = target
        # reset số tin nhắn chưa đọc
        self.unread_counts[target] = 0
        self.refresh_chat_display(target)
        self.update_chat_header(target, is_group=True)  # cập nhật header
        # repaint list để badge biến mất
        self.ui.userList.viewport().update()
        self.ui.groupList.viewport().update()

        # Ẩn/hiện nút
        self.ui.btnCall.hide()
        self.ui.btnVideo.hide()
        self.ui.btnLeaveGroup.show()  # chỉ hiện khi click vào nhóm
        self.ui.userList.viewport().update()
        self.ui.groupList.viewport().update()

    # ------------------- Lấy target hiện tại -------------------
    def get_current_target(self):
        group_item = self.ui.groupList.currentItem()
        user_item = self.ui.userList.currentItem()
        if group_item:
            return group_item.text().split(" (")[0]
        elif user_item:
            return user_item.text().split(" (")[0]
        else:
            return "public"

    # ------------------- Refresh hiển thị tin nhắn theo bên trái/phải có avatar, bao quanh nội dung -------------------
    def refresh_chat_display(self, target):
        layout = self.ui.chatMessages

        # Xoá các widget cũ
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        max_width = 300

        for sender, message in self.conversations.get(target, []):
            wrapper = QtWidgets.QWidget()
            h_layout = QHBoxLayout(wrapper)
            h_layout.setContentsMargins(5, 2, 5, 2)
            h_layout.setSpacing(5)

            # --- Kiểm tra kiểu tin nhắn ---
            if message.startswith("[IMAGE]"):
                img_path = message[len("[IMAGE]"):]
                label = QLabel()
                pixmap = QPixmap(img_path)
                if not pixmap.isNull():
                    pixmap = pixmap.scaledToWidth(200, Qt.SmoothTransformation)
                    label.setPixmap(pixmap)
                else:
                    label.setText("[Ảnh không tồn tại]")
                label.setMaximumWidth(220)

            elif message.startswith("[FILE]"):
                file_path = message[len("[FILE]"):]
                file_name = os.path.basename(file_path)
                label = QWidget()
                h = QHBoxLayout(label)
                h.setContentsMargins(0, 0, 0, 0)
                h.setSpacing(6)
                file_label = QLabel(f"📄 {file_name}")
                download_btn = QPushButton("Tải xuống")
                download_btn.setStyleSheet("font-size:12px; padding:3px 6px; border-radius:5px; background:#cce5ff;")
                h.addWidget(file_label)
                h.addWidget(download_btn)

                # Xử lý tải xuống
                def download_file():
                    save_path, _ = QFileDialog.getSaveFileName(self, "Lưu file", file_name)
                    if save_path:
                        try:
                            shutil.copy(file_path, save_path)
                            QMessageBox.information(self, "Thành công", f"Đã lưu file vào:\n{save_path}")
                        except Exception as e:
                            QMessageBox.warning(self, "Lỗi", f"Không thể lưu file: {e}")
                download_btn.clicked.connect(download_file)

            elif message.startswith("[VOICE]"):
                voice_path = message[len("[VOICE]"):]
                voice_name = os.path.basename(voice_path)

                label = QWidget()
                h = QHBoxLayout(label)
                h.setContentsMargins(0, 0, 0, 0)
                h.setSpacing(6)

                voice_label = QLabel(f"🎤 {voice_name}")
                play_btn = QPushButton("▶️")  # Biểu tượng play
                download_btn = QPushButton("⬇️")  # Biểu tượng tải
                for btn in [play_btn, download_btn]:
                    btn.setStyleSheet("""
                        font-size:16px;
                        padding:3px 6px;
                        border-radius:8px;
                        background:#ffe6cc;
                    """)

                h.addWidget(voice_label)
                h.addWidget(play_btn)
                h.addWidget(download_btn)

                # Biến kiểm tra trạng thái phát
                is_playing = {"state": False, "thread": None}

                # --- Hàm phát âm thanh ---
                def play_audio():
                    try:
                        from scipy.io.wavfile import read
                        rate, data = read(voice_path)
                        sd.play(data, rate)
                        sd.wait()
                    except Exception as e:
                        QMessageBox.warning(self, "Lỗi", f"Không thể phát file: {e}")
                    finally:
                        is_playing["state"] = False
                        play_btn.setText("▶️")

                # --- Khi nhấn nút Play ---
                def toggle_play():
                    if not os.path.exists(voice_path):
                        QMessageBox.warning(self, "Lỗi", "File không tồn tại")
                        return
                    if not is_playing["state"]:
                        is_playing["state"] = True
                        play_btn.setText("⏸️")
                        thread = threading.Thread(target=play_audio, daemon=True)
                        is_playing["thread"] = thread
                        thread.start()
                    else:
                        sd.stop()
                        is_playing["state"] = False
                        play_btn.setText("▶️")

                play_btn.clicked.connect(toggle_play)

                # --- Nút tải xuống ---
                def download_voice():
                    save_path, _ = QFileDialog.getSaveFileName(self, "Lưu file ghi âm", voice_name)
                    if save_path:
                        try:
                            shutil.copy(voice_path, save_path)
                            QMessageBox.information(self, "Thành công", f"Đã lưu file vào:\n{save_path}")
                        except Exception as e:
                            QMessageBox.warning(self, "Lỗi", f"Không thể lưu file: {e}")

                download_btn.clicked.connect(download_voice)

            else:
                # Tin nhắn thường
                label = QLabel(message)
                label.setWordWrap(True)
                label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                label.setMaximumWidth(max_width)

                label.setStyleSheet("""
                    background-color:#DCF8C6;
                    padding:10px 14px;
                    border-radius:10px;
                    font-size:20px;
                    line-height:1.4;
                    font-family:'Segoe UI', 'Arial';
                """)
            label.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)

            avatar_label = QLabel()
            if sender in self.avatars and os.path.exists(self.avatars[sender]):
                pixmap = QPixmap(self.avatars[sender]).scaled(30, 30, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
                size = min(pixmap.width(), pixmap.height())
                rounded = QPixmap(size, size)
                rounded.fill(QtCore.Qt.transparent)
                painter = QPainter(rounded)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setBrush(QBrush(pixmap))
                painter.setPen(QPen(QtCore.Qt.transparent))
                painter.drawEllipse(0, 0, size, size)
                painter.end()
                avatar_label.setPixmap(rounded)
                avatar_label.setFixedSize(30, 30)

            # Căn trái/phải
            if sender == self.username or sender == "Hệ thống":
                label.setStyleSheet("""
                    background-color:#DCF8C6;
                    padding:10px 14px;
                    border-radius:10px;
                    font-size:20px;
                    line-height:1.4;
                    font-family:'Segoe UI', 'Arial';
                """)
                h_layout.addStretch()
                h_layout.addWidget(label)
                h_layout.addWidget(avatar_label)
            else:
                # Đổi màu nền cho người khác
                label.setStyleSheet("""
                    background-color:#EDEDED;
                    padding:10px 14px;
                    border-radius:10px;
                    font-size:20px;
                    line-height:1.4;
                    font-family:'Segoe UI', 'Arial';
                """)

                # Tạo layout dọc cho tên sender + nội dung tin nhắn
                v_layout = QVBoxLayout()
                v_layout.setSpacing(2)
                v_layout.setContentsMargins(0,0,0,0)

                # Hiển thị tên sender
                name_label = QLabel(sender)
                name_label.setStyleSheet("font-size:12px; color:#555555;")
                name_label.setAlignment(Qt.AlignLeft)
                v_layout.addWidget(name_label)
                v_layout.addWidget(label)

                h_layout.addWidget(avatar_label)
                h_layout.addLayout(v_layout)
                h_layout.addStretch()

            layout.addWidget(wrapper, alignment=QtCore.Qt.AlignTop)

        QtCore.QTimer.singleShot(0, lambda: self.ui.scrollArea.verticalScrollBar().setValue(
            self.ui.scrollArea.verticalScrollBar().maximum()
        ))

    # ------------------- Gửi tin nhắn -------------------
    def send_text_message(self):
        text = self.ui.messageInput.text().strip()
        if not text:
            return

        # SỬ DỤNG current_chat_user thay vì get_current_target()
        target = getattr(self, 'current_chat_user', 'public')

        self.store_message_signal(target, self.username, text)

        if self.client:
            try:
                group_names = [self.ui.groupList.item(i).text().split(" (")[0] for i in range(self.ui.groupList.count())]
                user_names = [self.ui.userList.item(i).text().split(" (")[0] for i in range(self.ui.userList.count())]

                if target in group_names:
                    self.client.send_group_message(target, text)
                elif target in user_names:
                    self.client.send_private_message(target, text)
                else:
                    self.client.send_message(text)
            except Exception as e:
                print("❌ Lỗi gửi tin nhắn:", e)

        self.ui.messageInput.clear()

    # ------------------- Gửi tin nhắn hệ thống -------------------
    def send_message(self, msg):
        self.store_message_signal("public", "Hệ thống", msg)

        # ------------------- Gửi ảnh -------------------
    def send_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh gửi", "", "Ảnh (*.png *.jpg *.jpeg *.gif)")
        if not file_path:
            return
        target = self.get_current_target()

        # Hiển thị tạm thời trên chat
        self.store_message_signal(target, self.username, f"[IMAGE]{file_path}")

        if self.client:
            try:
                with open(file_path, "rb") as f:
                    data = f.read()
                b64_data = base64.b64encode(data).decode('utf-8')
                filename = os.path.basename(file_path)

                # Nếu gửi nhóm
                if target in [self.ui.groupList.item(i).text().split(" (")[0] for i in range(self.ui.groupList.count())]:
                    self.client.send_raw(f"GROUP_IMG|{target}|{filename}|{b64_data}")
                else:  # Gửi cá nhân/public
                    self.client.send_raw(f"IMG|{target}|{filename}|{b64_data}")
            except Exception as e:
                print("❌ Lỗi gửi ảnh:", e)

    # ------------------- Gửi file -------------------
    def send_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file gửi", "")
        if not file_path:
            return
        target = self.get_current_target()

        # Hiển thị tạm thời trên chat
        self.store_message_signal(target, self.username, f"[FILE]{file_path}")

        if self.client:
            try:
                with open(file_path, "rb") as f:
                    data = f.read()
                b64_data = base64.b64encode(data).decode('utf-8')
                filename = os.path.basename(file_path)

                # Nếu gửi nhóm
                if target in [self.ui.groupList.item(i).text().split(" (")[0] for i in range(self.ui.groupList.count())]:
                    self.client.send_raw(f"GROUP_FILE|{target}|{filename}|{b64_data}")
                else:  # Gửi cá nhân/public
                    self.client.send_raw(f"FILE|{target}|{filename}|{b64_data}")
            except Exception as e:
                print("❌ Lỗi gửi file:", e)

        # ------------------- Ghi âm bằng micro và gửi -------------------
    def send_voice(self):
        duration = 0
        fs = 44100  # Tần số mẫu
        is_recording = False
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name

        dialog = QDialog(self)
        dialog.setWindowTitle("🎤 Ghi âm tin nhắn thoại")
        dialog.setFixedSize(250, 150)

        layout = QVBoxLayout(dialog)
        status_label = QLabel("Nhấn 'Bắt đầu' để ghi âm...")
        status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(status_label)

        btn_start = QPushButton("Bắt đầu ghi")
        btn_stop = QPushButton("Dừng lại")
        btn_send = QPushButton("Gửi tin nhắn thoại")
        btn_stop.setEnabled(False)
        btn_send.setEnabled(False)
        layout.addWidget(btn_start)
        layout.addWidget(btn_stop)
        layout.addWidget(btn_send)

        recording_thread = None
        recording = []

        def record_audio():
            nonlocal recording
            try:
                recording = sd.rec(int(fs * 120), samplerate=fs, channels=1, dtype='int16')  # Giới hạn 120s
                sd.wait()
            except Exception as e:
                print("❌ Lỗi ghi âm:", e)

        def start_recording():
            nonlocal recording_thread, is_recording
            is_recording = True
            btn_start.setEnabled(False)
            btn_stop.setEnabled(True)
            status_label.setText("🎙️ Đang ghi âm...")
            recording_thread = threading.Thread(target=record_audio)
            recording_thread.start()

        def stop_recording():
            nonlocal is_recording
            if is_recording:
                sd.stop()
                is_recording = False
                btn_stop.setEnabled(False)
                btn_send.setEnabled(True)
                status_label.setText("✅ Ghi âm xong, sẵn sàng gửi")

                # Lưu file WAV tạm
                write(temp_file, fs, recording)
                print(f"[VOICE SAVED] {temp_file}")

        def send_voice_message():
            target = self.get_current_target()
            self.store_message_signal(target, self.username, f"[VOICE]{temp_file}")

            if self.client:
                try:
                    with open(temp_file, "rb") as f:
                        data = f.read()
                    b64_data = base64.b64encode(data).decode('utf-8')
                    filename = os.path.basename(temp_file)

                    # Nếu gửi nhóm
                    if target in [self.ui.groupList.item(i).text().split(" (")[0] for i in range(self.ui.groupList.count())]:
                        self.client.send_raw(f"GROUP_VOICE|{target}|{filename}|{b64_data}")
                    else:
                        self.client.send_raw(f"VOICE|{target}|{filename}|{b64_data}")
                except Exception as e:
                    print("❌ Lỗi gửi voice:", e)
            dialog.accept()

        btn_start.clicked.connect(start_recording)
        btn_stop.clicked.connect(stop_recording)
        btn_send.clicked.connect(send_voice_message)

        dialog.exec_()

    def start_voice_call(self):
        if not getattr(self, "client", None):
            QMessageBox.warning(self, "Gọi thoại", "Chưa kết nối tới server!")
            return
        if not getattr(self, "current_chat_user", None):
            QMessageBox.warning(self, "Gọi thoại", "Vui lòng chọn người để gọi!")
            return

        # --- Tạo VoiceCall nhưng chưa start ---
        self.current_call = VoiceCall(self.client, self.current_chat_user, parent=self)

        try:
            # Gửi yêu cầu gọi
            self.client.send(f"CALL_REQUEST|{self.current_chat_user}\n")
            print(f"📞 Gửi yêu cầu gọi tới {self.current_chat_user}")
        except Exception as e:
            print("Không gửi được CALL_REQUEST:", e)

    def show_incoming_call_popup(self, caller):
        if hasattr(self, "current_call") and self.current_call:
            if self.current_call.is_calling or getattr(self.current_call, 'incoming', False):
                return

        reply = QMessageBox.question(
            self,
            "📞 Cuộc gọi đến",
            f"{caller} đang gọi bạn. Chấp nhận?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # Gửi xác nhận cho server
            self.client.send(f"CALL_ACCEPT|{caller}\n")
            # Tạo VoiceCall incoming và start
            self.current_call = VoiceCall(self.client, caller, incoming=True, parent=self)
            # self.current_call.start()
            print(f"✅ Đã nhận cuộc gọi từ {caller}")
        else:
            self.client.send(f"CALL_END|{caller}\n")
            print(f"❌ Từ chối cuộc gọi từ {caller}")

    def start_video_call(self):
        if not getattr(self, "client", None):
            QMessageBox.warning(self, "Gọi video", "Chưa kết nối tới server!")
            return
        if not getattr(self, "current_chat_user", None):
            QMessageBox.warning(self, "Gọi video", "Vui lòng chọn người để gọi!")
            return

        target = self.current_chat_user
        # tạo VideoCall instance (nhưng chưa start)
        self.current_video_call = VideoCall(self.client, target, parent=self)
        self.client.video_call = self.current_video_call   # ⭐ RẤT QUAN TRỌNG
        self.current_video_call.show()

        try:
            # gửi yêu cầu
            self.client.send_video_request(target)
            print(f"📹 Gửi VIDEO_REQUEST tới {target}")
        except Exception as e:
            print("Không gửi được VIDEO_REQUEST:", e)

    def show_incoming_video_popup(self, caller):
        # nếu có cuộc gọi video đang tồn tại, ignore
        if hasattr(self, "current_video_call") and getattr(self, "current_video_call", None):
            if getattr(self.current_video_call, "is_running", False):
                return

        reply = QMessageBox.question(
            self,
            "📹 Video call đến",
            f"{caller} muốn gọi video. Chấp nhận?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # send accept
            try:
                self.client.send_video_accept(caller)
            except Exception:
                try:
                    self.client.send(f"VIDEO_ACCEPT|{caller}\n")
                except:
                    pass
            # create VideoCall incoming and start
            self.current_video_call = VideoCall(self.client, caller, incoming=True, parent=self)
            self.client.video_call = self.current_video_call
            self.current_video_call.accept_and_start()
        else:
            try:
                self.client.send_video_end(caller)
            except Exception:
                try:
                    self.client.send(f"VIDEO_END|{caller}\n")
                except:
                    pass

    def closeEvent(self, event):
        # when closing chat window, ensure any video call ended
        try:
            if hasattr(self, "current_video_call") and self.current_video_call:
                self.current_video_call.end()
        except:
            pass
        try:
            if hasattr(self, "current_call") and self.current_call:
                self.current_call.end()
        except:
            pass
        event.accept()

    # ------------------- Tạo nhóm -------------------
    def create_group(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Tạo nhóm mới")
        dialog.resize(300, 400)
        layout = QVBoxLayout(dialog)
        group_name, ok = QInputDialog.getText(dialog, "Tên nhóm", "Nhập tên nhóm:")
        if not ok or not group_name.strip():
            return
        member_list = QListWidget(dialog)
        member_list.setSelectionMode(QListWidget.MultiSelection)
        for i in range(self.ui.userList.count()):
            item = self.ui.userList.item(i)
            member_list.addItem(item.text().split(" (")[0])
        layout.addWidget(member_list)
        ok_btn = QPushButton("Tạo nhóm")
        layout.addWidget(ok_btn)

        def on_ok():
            members = [item.text().split(" (")[0] for item in member_list.selectedItems()]
            if self.username not in members:
                members.append(self.username)
            if members and self.client:
                self.client.send_group_create(group_name, members)
                dialog.accept()

        ok_btn.clicked.connect(on_ok)
        dialog.exec_()

    def leave_group(self):
        target = getattr(self, 'current_chat_user', None)
        if not target:
            return
        reply = QMessageBox.question(
            self,
            "Rời nhóm",
            f"Bạn có chắc muốn rời nhóm '{target}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes and self.client:
            try:
                # Gửi thông báo hệ thống đến nhóm trước khi rời
                system_msg = f"'{self.username}' đã rời nhóm."
                self.store_message_signal(target, "Hệ thống", system_msg)
                if self.client:
                    # Gửi tin nhắn hệ thống tới server để broadcast cho group
                    self.client.send_group_message(target, system_msg)

                # Gửi lệnh rời nhóm
                self.client.send_group_leave(target)

                QMessageBox.information(self, "Rời nhóm", f"Bạn đã rời nhóm '{target}'")

                # Xóa khỏi giao diện
                for i in range(self.ui.groupList.count()):
                    if self.ui.groupList.item(i).text().split(" (")[0] == target:
                        self.ui.groupList.takeItem(i)
                        break

                self.current_chat_user = None
                self.ui.btnLeaveGroup.hide()
                self.ui.chatTitle.setText("Chat chung")
                self.ui.chatAvatar.setVisible(False)
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", f"Không thể rời nhóm: {e}")
