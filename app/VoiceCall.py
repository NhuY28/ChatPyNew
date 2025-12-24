import threading
import sounddevice as sd
import numpy as np
import base64
import queue
import time
from PyQt5.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QMessageBox

class VoiceCall(QDialog):
    def __init__(self, client, target_user, incoming=False, parent=None,
                 samplerate=16000, blocksize=1024):
        super().__init__(parent)
        self.client = client
        self.target_user = target_user
        self.samplerate = samplerate
        self.channels = 1
        self.blocksize = blocksize
        self.is_calling = False
        self.incoming = incoming

        # Queues
        self._play_queue = queue.Queue(maxsize=200)
        self._outgoing_queue = queue.Queue(maxsize=500)

        self.setWindowTitle(f"📞 Gọi: {self.target_user}")
        self.setFixedSize(300, 160)

        layout = QVBoxLayout(self)
        self.lbl = QLabel("", self)
        layout.addWidget(self.lbl)

        if self.incoming:
            self.btn_accept = QPushButton("Nhận", self)
            self.btn_accept.setStyleSheet("background:#4CAF50; color:white; font-weight:bold;")
            self.btn_accept.clicked.connect(self.accept_call)
            layout.addWidget(self.btn_accept)
            self.lbl.setText(f"📞 {self.target_user} đang gọi bạn...")
        else:
            self.lbl.setText(f"📞 Đang gọi {self.target_user}...")

        self.btn_end = QPushButton("Kết thúc", self)
        self.btn_end.setStyleSheet("background:#f44336; color:white; font-weight:bold;")
        self.btn_end.clicked.connect(self.end)
        layout.addWidget(self.btn_end)

        self._t_record = None
        self._t_play = None
        self._t_send = None
        self.show()

    def start(self):
        """Bắt đầu ghi âm và phát audio"""
        if not self.target_user or self.is_calling:
            return
        self.is_calling = True
        self.lbl.setText(f"📞 Cuộc gọi với {self.target_user}...")
        if hasattr(self, "btn_accept"):
            self.btn_accept.hide()

        # Thread ghi âm (callback only enqueues)
        self._t_record = threading.Thread(target=self._record_loop, daemon=True)
        self._t_record.start()

        # Thread gửi network (lấy từ outgoing queue)
        self._t_send = threading.Thread(target=self._send_loop, daemon=True)
        self._t_send.start()

        # Thread phát audio (từ incoming queue)
        self._t_play = threading.Thread(target=self._play_loop, daemon=True)
        self._t_play.start()

    def accept_call(self):
        """Nhấn nhận khi có cuộc gọi đến"""
        try:
            self.client.send_call_accept(self.target_user)
        except Exception:
            try:
                self.client.send(f"CALL_ACCEPT|{self.target_user}\n")
            except:
                pass

        if not self.is_calling:
            self.start()

    def _record_loop(self):
        """Ghi âm: callback chỉ đẩy vào queue, không gửi mạng"""
        def callback(indata, frames, time_info, status):
            if not self.is_calling:
                raise sd.CallbackStop()
            try:
                # mono signal: indata shape (frames, channels)
                audio_int16 = (indata[:, 0] * 32767).astype(np.int16)
                # Gộp chunk_size (ví dụ 2048) — phần này tạo 1 blob để gửi
                chunk_size = 2048
                for i in range(0, len(audio_int16), chunk_size):
                    chunk = audio_int16[i:i+chunk_size]
                    if len(chunk) == 0:
                        continue
                    b64 = base64.b64encode(chunk.tobytes()).decode('ascii')
                    try:
                        # non-blocking enqueue (bỏ chunk nếu queue đầy)
                        self._outgoing_queue.put_nowait(b64)
                    except queue.Full:
                        # nếu quá đầy, drop this chunk
                        pass
            except Exception as e:
                print("[VoiceCall] send audio enqueue error:", e)

        try:
            with sd.InputStream(samplerate=self.samplerate,
                                channels=self.channels,
                                dtype="float32",
                                blocksize=self.blocksize,
                                callback=callback):
                while self.is_calling:
                    sd.sleep(50)
        except Exception as e:
            print("[VoiceCall] record loop error:", e)
            self.is_calling = False

    def _send_loop(self):
        """Lấy chunk từ outgoing_queue và gửi qua socket (throttle nếu cần)"""
        while self.is_calling:
            try:
                b64 = self._outgoing_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            # Throttle: giữ tốc độ phù hợp (ví dụ 20-30 gói/s)
            try:
                # kiểm tra socket alive
                if not getattr(self.client, "sock", None) or not self.client.running:
                    # stop sending if socket dead
                    self.is_calling = False
                    break
                # gửi: CALL_STREAM|target|b64
                # use client helper which ensures newline
                try:
                    self.client.send_call_stream(self.target_user, b64)
                except Exception:
                    # fallback raw
                    self.client.send(f"CALL_STREAM|{self.target_user}|{b64}\n")
            except Exception as e:
                print("[VoiceCall] network send error:", e)
                # nếu lỗi nghiêm trọng, dừng cuộc gọi
                self.is_calling = False
                break
            # small sleep to limit rate (tune if needed)
            time.sleep(0.03)

    def receive_audio(self, b64_data):
        """Nhận audio từ server và đẩy vào play queue"""
        try:
            audio_bytes = base64.b64decode(b64_data)
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            if audio_array.ndim == 1:
                audio_array = audio_array.reshape(-1, 1)
            try:
                self._play_queue.put_nowait(audio_array)
            except queue.Full:
                # drop chunk if too many pending
                pass
        except Exception as e:
            print("[VoiceCall] receive audio error:", e)

    def _play_loop(self):
        """Phát audio ra loa"""
        try:
            with sd.OutputStream(samplerate=self.samplerate,
                                 channels=self.channels,
                                 dtype='float32') as out_stream:
                while self.is_calling:
                    try:
                        audio_array = self._play_queue.get(timeout=0.05)
                        out_stream.write(audio_array)
                    except queue.Empty:
                        continue
        except Exception as e:
            print("[VoiceCall] play loop error:", e)

    def end(self):
        """Kết thúc cuộc gọi"""
        if not self.is_calling:
            return   # <--- CHỐNG GỌI NHIỀU LẦN

        self.is_calling = False
        try: sd.stop()
        except: pass

        # gửi cho server
        try:
            self.client.send(f"CALL_END|{self.target_user}\n")
        except:
            pass

        self.close()
