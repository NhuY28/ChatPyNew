# app/VideoCall.py
import threading
import time
import base64
import queue
import cv2
import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write, read
from PyQt5.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QApplication
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt
from PyQt5.QtCore import pyqtSignal

class VideoCall(QDialog):
    signal_local = pyqtSignal(QPixmap)
    signal_remote = pyqtSignal(QPixmap)
    """
    VideoCall: dialog hiển thị remote (lớn) và local (nhỏ góc phải).
    Gửi frame JPEG base64 + audio Base64 qua client.send_video_stream(target, b64_video, b64_audio)
    """
    def __init__(self, client, target_user, incoming=False, parent=None,
                 fps=15, width=640, height=480):
        super().__init__(parent)
        self.client = client
        self.target_user = target_user
        self.incoming = incoming
        self.fps = fps
        self.width = width
        self.height = height
        self.is_running = False
        self.call_established = False

        # queues
        self._send_queue = queue.Queue(maxsize=100)
        self._audio_queue = queue.Queue(maxsize=50)
        self._display_lock = threading.Lock()

        # UI
        self.setWindowTitle(f"📹 Video call: {self.target_user}")
        self.setFixedSize(900, 640)

        layout = QVBoxLayout(self)

        # Remote (large)
        self.remote_label = QLabel(self)
        self.remote_label.setAlignment(Qt.AlignCenter)
        self.remote_label.setStyleSheet("background: black;")
        self.remote_label.setFixedSize(880, 520)
        layout.addWidget(self.remote_label)

        # bottom controls: end button
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.btn_end = QPushButton("Kết thúc", self)
        self.btn_end.setStyleSheet("background:#f44336;color:white;font-weight:bold;")
        self.btn_end.clicked.connect(self.end)
        bottom.addWidget(self.btn_end)
        layout.addLayout(bottom)

        # local small preview (overlay)
        self.local_label = QLabel(self)
        self.local_label.setFixedSize(200, 150)
        self.local_label.setStyleSheet("border-radius:6px; background: #222;")
        self.local_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.local_label.raise_()

        self.signal_local.connect(self.local_label.setPixmap)
        self.signal_remote.connect(self.remote_label.setPixmap)


        # capture
        self._cap = None
        self._t_capture = None
        self._t_send = None
        self._t_ui = None
        self._t_audio = None

        # remote frame storage
        self._last_remote_frame = None

        # audio
        self.audio_fs = 16000
        self.audio_chunk = 1024

    # ---------- lifecycle ----------
    def start(self):
        if self.is_running:
            return

        self.is_running = True

        try:
            self._cap = cv2.VideoCapture(0)
        except:
            self.is_running = False
            return

        self.show()
        QApplication.processEvents()

        self._t_capture = threading.Thread(target=self._capture_loop, daemon=True)
        self._t_send = threading.Thread(target=self._send_loop, daemon=True)
        self._t_audio = threading.Thread(target=self._audio_capture_loop, daemon=True)
        self._t_ui = threading.Thread(target=self._ui_update_loop, daemon=True)

        self._t_capture.start()
        self._t_send.start()
        self._t_audio.start()
        self._t_ui.start()

        self.resizeEvent(None)

    def accept_and_start(self):
        self.call_established = True   # ⭐ RẤT QUAN TRỌNG
        self.start()


    def end(self):
        if not self.is_running:
            try:
                self.close()
            except:
                pass
            return
        self.is_running = False
        time.sleep(0.05)

        # release camera
        try:
            if self._cap and self._cap.isOpened():
                self._cap.release()
        except:
            pass

        # notify server
        try:
            self.client.send_video_end(self.target_user)
        except Exception:
            try:
                self.client.send(f"VIDEO_END|{self.target_user}\n")
            except:
                pass

        self.close()

    # ---------- video capture + send ----------
    def _capture_loop(self):
        interval = 1.0 / max(1, self.fps)

        while self.is_running:
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame_small = cv2.resize(frame, (480, 360))

            # ===== local preview luôn hiển thị =====
            qt_pix = self._cv2_to_qpixmap(frame_small, small=True)
            try:
                self.signal_local.emit(qt_pix)
            except:
                pass

            # ⛔ CHƯA ACCEPT → KHÔNG GỬI FRAME
            if not self.call_established:
                time.sleep(interval)
                continue

            ok, jpeg = cv2.imencode(
                '.jpg',
                frame_small,
                [int(cv2.IMWRITE_JPEG_QUALITY), 60]
            )
            if not ok:
                continue

            b64_video = base64.b64encode(jpeg.tobytes()).decode('ascii')

            try:
                self._send_queue.put_nowait(b64_video)
            except queue.Full:
                pass

            time.sleep(interval)

    def _send_loop(self):
        while self.is_running:
            try:
                b64_video = self._send_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            b64_audio = ""
            try:
                audio_data = self._audio_queue.get_nowait()
                b64_audio = base64.b64encode(audio_data).decode('ascii')
            except queue.Empty:
                pass

            try:
                try:
                    self.client.send_video_stream(self.target_user, b64_video, b64_audio)
                except Exception:
                    self.client.send(f"VIDEO_STREAM|{self.target_user}|{b64_video}|{b64_audio}\n")
            except Exception as e:
                print("[VideoCall] send error:", e)
                self.is_running = False
                break
            time.sleep(0.01)

    # ---------- audio capture ----------
    def _audio_capture_loop(self):
        def callback(indata, frames, time_info, status):
            if not self.is_running:
                raise sd.CallbackStop()
            try:
                self._audio_queue.put_nowait(indata.copy().tobytes())
            except queue.Full:
                pass

        try:
            with sd.InputStream(samplerate=self.audio_fs, channels=1, dtype='int16',
                                blocksize=self.audio_chunk, callback=callback):
                while self.is_running:
                    time.sleep(0.05)
        except Exception as e:
            print("[VideoCall] audio capture error:", e)

    # ---------- receive remote ----------
    def receive_remote_frame(self, b64_video, b64_audio=""):
        try:
            if b64_video:
                data = base64.b64decode(b64_video)
                nparr = np.frombuffer(data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame is not None:
                    frame = cv2.resize(frame, (880, 520))
                    with self._display_lock:
                        self._last_remote_frame = frame

            if b64_audio:
                audio_bytes = base64.b64decode(b64_audio)
                audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
                try:
                    sd.play(audio_np, self.audio_fs, blocking=False)
                except Exception as e:
                    print("[VideoCall] audio playback error:", e)
        except Exception as e:
            print("[VideoCall] receive_remote_frame error:", e)

    # ---------- UI update ----------
    def _ui_update_loop(self):
        interval = 1.0 / max(1, self.fps)
        while self.is_running:
            frame = None
            with self._display_lock:
                if self._last_remote_frame is not None:
                    frame = self._last_remote_frame.copy()
                    self._last_remote_frame = None

            if frame is not None:
                pix = self._cv2_to_qpixmap(frame, small=False)
                self.signal_remote.emit(pix)

            time.sleep(interval)


    def _cv2_to_qpixmap(self, frame, small=False):
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pix = QPixmap.fromImage(img)
            if small:
                pix = pix.scaled(self.local_label.width(), self.local_label.height(),
                                 Qt.KeepAspectRatio, Qt.SmoothTransformation)
            else:
                pix = pix.scaled(self.remote_label.width(), self.remote_label.height(),
                                 Qt.KeepAspectRatio, Qt.SmoothTransformation)
            return pix
        except:
            qp = QPixmap(self.local_label.size())
            qp.fill(Qt.black)
            return qp

    def resizeEvent(self, event):
        try:
            remote_geo = self.remote_label.geometry()
            x = remote_geo.right() - self.local_label.width() - 12
            y = remote_geo.top() + 12
            self.local_label.move(x, y)
        except:
            pass
        super().resizeEvent(event)
