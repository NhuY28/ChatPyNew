import socket
import threading
import base64, os, hashlib

import pyaudio
from PyQt5.QtCore import QTimer
from pygame import time


class ChatClient:
    def __init__(self, host="192.168.1.5", port=2025, gui_parent=None):
        self.host = host
        self.port = port
        self.sock = None
        self.running = False
        self.on_message = None  # callback: msg từ server
        self.gui_parent = gui_parent

        self.all_users = {}       # username -> avatar_path
        self.online_users = set() # username đang online

        # -------------------------------
        self.group_unread_count = {}  # {group_name: số tin nhắn chưa đọc}
        self.open_groups = set()      # nhóm đang mở
        self.received_msg_ids = set() # tránh tăng count trùng

        self.call_active = False
        self.call_target = None
        self.current_call = None

        self.video_call = None

    # ====================== CONNECT ======================
    def connect(self):
        if self.sock:
            return
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.running = True
        threading.Thread(target=self.receive_loop, daemon=True).start()

    # ====================== ACCOUNT ======================
    def register(self, username, password, avatar_path="avatars/default.jpg"):
        if os.path.exists(avatar_path):
            with open(avatar_path, "rb") as f:
                b64_avatar = base64.b64encode(f.read()).decode("utf-8")
        else:
            b64_avatar = ""
        self.send(f"REGISTER|{username}|{password}|{b64_avatar}\n")

    def login(self, username, password):
        # đảm bảo on_message đã gắn trước khi login
        self.send(f"LOGIN|{username}|{password}\n")

    # ====================== MESSAGE ======================
    def send_message(self, text):
        self.send(f"MSG|{text}\n")

    def send_private_message(self, target, text):
        self.send(f"PRIVATE|{target}|{text}\n")

    # ====================== FILE / IMAGE / VOICE ======================
    def send_file(self, target, filepath):
        self._send_file_generic("FILE", target, filepath)

    def send_image(self, target, filepath):
        self._send_file_generic("IMG", target, filepath)

    def send_voice(self, target, filepath):
        self._send_file_generic("VOICE", target, filepath)

    def _send_file_generic(self, cmd, target, filepath):
        try:
            with open(filepath, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")
            filename = os.path.basename(filepath)
            self.send(f"{cmd}|{target}|{filename}|{b64_data}\n")
        except Exception as e:
            print(f"[{cmd} ERROR]", e)

    # ====================== GROUP CHAT ======================
    def send_group_create(self, group_name, members):
        msg = f"GROUP_CREATE|{group_name}|{','.join(members)}\n"
        self.send(msg)

    def send_group_message(self, group_name, text):
        self.send(f"GROUP_MSG|{group_name}|{text}\n")

    def send_group_image(self, group_name, filepath):
        self._send_file_generic("GROUP_IMG", group_name, filepath)

    def send_group_file(self, group_name, filepath):
        self._send_file_generic("GROUP_FILE", group_name, filepath)

    def send_group_voice(self, group_name, filepath):
        self._send_file_generic("GROUP_VOICE", group_name, filepath)

    def send_group_leave(self, group_name):
        self.send(f"GROUP_LEAVE|{group_name}\n")

    # ====================== CALL ======================
    def send_call_request(self, target):
        self.send(f"CALL_REQUEST|{target}\n")

    def send_call_accept(self, target):
        self.send(f"CALL_ACCEPT|{target}\n")

    def send_call_stream(self, target, b64_chunk):
        try:
            self.send(f"CALL_STREAM|{target}|{b64_chunk}\n")
        except Exception as e:
            print("[ChatClient] send_call_stream error:", e)

    def send_call_end(self, target):
        self.send(f"CALL_END|{target}\n")

    # inside ChatClient class

    def send_video_request(self, target):
        """Send VIDEO_REQUEST to target"""
        try:
            self.send(f"VIDEO_REQUEST|{target}\n")
        except Exception as e:
            # fallback raw send if needed
            try:
                self.send_raw(f"VIDEO_REQUEST|{target}\n")
            except:
                raise

    def send_video_accept(self, target):
        try:
            self.send(f"VIDEO_ACCEPT|{target}\n")
        except Exception:
            try:
                self.send_raw(f"VIDEO_ACCEPT|{target}\n")
            except:
                pass

    def send_video_stream(self, target, b64_video, b64_audio=""):
        """
        Send VIDEO_STREAM|target|b64_video|b64_audio\n
        Prefer a helper method that ensures newline is added.
        """
        try:
            # ensure no stray newlines inside b64 by replacing them
            b64_video = b64_video.replace("\n", "")
            b64_audio = (b64_audio or "").replace("\n", "")
            self.send(f"VIDEO_STREAM|{target}|{b64_video}|{b64_audio}\n")
        except Exception as e:
            # fallback to raw socket if needed
            try:
                self.send_raw(f"VIDEO_STREAM|{target}|{b64_video}|{b64_audio}\n")
            except:
                raise

    def send_video_end(self, target):
        try:
            self.send(f"VIDEO_END|{target}\n")
        except Exception:
            try:
                self.send_raw(f"VIDEO_END|{target}\n")
            except:
                pass

    # ====================== GROUP OPEN / UNREAD ======================
    def open_group(self, group_name):
        """Mở nhóm, reset unread count"""
        self.open_groups.add(group_name)
        self.group_unread_count[group_name] = 0

    def close_group(self, group_name):
        """Đóng nhóm"""
        if group_name in self.open_groups:
            self.open_groups.remove(group_name)

    def get_unread_count(self, group_name):
        return self.group_unread_count.get(group_name, 0)

    def _play_audio_chunk(self, data):
        """Phát 1 đoạn âm thanh"""
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, output=True)
        stream.write(data)
        stream.stop_stream()
        stream.close()
        p.terminate()

    # ====================== RAW SEND ======================
    def send_raw(self, msg: str):
        """
        Gửi chuỗi thẳng lên server.
        Dùng khi bạn muốn gửi lệnh/format tuỳ chỉnh.
        msg: str, ví dụ 'IMG|target|filename|base64data'
        """
        if self.sock and self.running:
            try:
                # đảm bảo kết thúc bằng \n để server nhận đúng 1 message
                if not msg.endswith("\n"):
                    msg += "\n"
                self.sock.sendall(msg.encode("utf-8"))
            except Exception as e:
                print("❌ Lỗi send_raw:", e)
                self.close()

    # ====================== CORE SOCKET ======================
    def send(self, message):
        if self.sock and self.running:
            try:
                self.sock.sendall(message.encode("utf-8"))
            except:
                self.close()

    def request_user_list(self):
        try:
            self.send_raw("REQUEST_USER_LIST|")
        except Exception as e:
            print("❌ Không thể yêu cầu danh sách user:", e)

    def receive_loop(self):
        """Luồng nhận dữ liệu từ server"""
        buffer = ""
        while self.running:
            try:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break

                try:
                    text = chunk.decode("utf-8")
                except UnicodeDecodeError:
                    continue

                buffer += text
                while "\n" in buffer:
                    msg, buffer = buffer.split("\n", 1)
                    msg = msg.strip()
                    if msg:
                        self.handle_incoming(msg)
            except Exception as e:
                print("[RECV ERROR]", e)
                break
        self.running = False

    # ====================== HANDLE INCOMING ======================
    def handle_incoming(self, msg):
        """
        Xử lý message từ server trước khi gửi GUI.
        Tăng group_unread_count chỉ khi message mới, nhóm đóng.
        """
        parts = msg.split("|")
        cmd = parts[0]

        # Các message nhóm
        group_cmds = ("GROUP_MSG", "GROUP_IMG", "GROUP_FILE", "GROUP_VOICE")
        if cmd in group_cmds:
            group_name = parts[1]
            # Tạo id đơn giản để tránh trùng lặp (hash msg)
            msg_id = hashlib.md5(msg.encode("utf-8")).hexdigest()
            if msg_id not in self.received_msg_ids:
                self.received_msg_ids.add(msg_id)
                if group_name not in self.open_groups:
                    self.group_unread_count[group_name] = self.group_unread_count.get(group_name, 0) + 1

        # gửi tới GUI / callback
        if self.on_message:
            try:
                self.on_message(msg)
            except Exception as e:
                print("[ON_MESSAGE ERROR]", e)

        # --- VOICE (private) ---
        if cmd == "VOICE":
            sender = parts[1]
            filename = parts[2]
            b64 = parts[3]
            os.makedirs("received_files", exist_ok=True)
            filepath = os.path.join("received_files", filename)
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(b64))
            if self.on_message:
                self.on_message(f"PRIVATE|{sender}|[VOICE]{filepath}")

        elif cmd == "GROUP_VOICE":
            group_name = parts[1]
            sender = parts[2]
            filename = parts[3]
            b64 = parts[4]
            os.makedirs(os.path.join("received_files", group_name), exist_ok=True)
            filepath = os.path.join("received_files", group_name, filename)
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(b64))
            if self.on_message:
                self.on_message(f"GROUP_MSG|{group_name}|{sender}|[VOICE]{filepath}")

        elif cmd == "CALL_STREAM":
            sender = parts[1]
            b64_data = parts[2]
            if self.current_call:  # chỉ check self.current_call != None
                self.current_call.receive_audio(b64_data)

        elif cmd == "CALL_ACCEPT":
            sender = parts[1]
            print(f"✅ {sender} đã chấp nhận cuộc gọi!")
            # Xem như chỉ gửi thông báo về GUI
            if self.on_message:
                self.on_message(f"CALL_ACCEPT|{sender}")

        elif cmd == "CALL_REQUEST":
            sender = parts[1]
            # Không gọi self.on_message ở đây nữa
            # GUI sẽ nhận thông qua handle_client_message

        elif cmd == "CALL_END":
            sender = parts[1]
            print(f"📴 {sender} đã kết thúc cuộc gọi.")
            self.call_active = False

        elif cmd == "ALL_USERS":
            # Xóa danh sách cũ
            self.all_users.clear()
            self.online_users.clear()

            for part in parts[1:]:
                if ":" in part:
                    username, avatar = part.split(":", 1)
                    self.all_users[username] = avatar
                    self.online_users.add(username)  # trạng thái online

            # Gọi callback GUI nếu có
            if self.on_message:
                self.on_message(msg)

        elif cmd == "VIDEO_STREAM":
            sender = parts[1]
            b64_video = parts[2] if len(parts) > 2 else ""
            b64_audio = parts[3] if len(parts) > 3 else ""

            if self.video_call:
                self.video_call.receive_remote_frame(b64_video, b64_audio)

    def close(self):
        self.running = False
        if self.sock:
            try: self.sock.close()
            except: pass
            self.sock = None