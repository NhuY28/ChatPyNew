import sounddevice as sd
from scipy.io.wavfile import write
import os
import tempfile

def record_audio_to_file(duration=5, samplerate=44100):
    try:
        print("🔴 Bắt đầu ghi âm...")
        recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=2)
        sd.wait()  # chờ ghi xong
        print("✅ Ghi âm hoàn tất")

        tmp_path = os.path.join(tempfile.gettempdir(), "voice_message.wav")
        write(tmp_path, samplerate, recording)
        return tmp_path
    except Exception as e:
        print("❌ Lỗi ghi âm:", e)
        return None
