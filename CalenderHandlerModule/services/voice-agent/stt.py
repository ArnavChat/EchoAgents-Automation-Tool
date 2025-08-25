import sounddevice as sd
import numpy as np
import whisper
import scipy.io.wavfile as wav
import os, time

# Load Whisper model (allow override via WHISPER_MODEL env, default 'base')
_model_name = os.getenv('WHISPER_MODEL', 'base')
print(f"[stt] Loading Whisper model: {_model_name}")
_load_start = time.time()
model = whisper.load_model(_model_name)
print(f"[stt] Model loaded in {time.time()-_load_start:.2f}s")


def record_audio(filename, duration=5, fs=16000):
    print(f"🎙 Recording for {duration} seconds...")
    audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype=np.int16)
    sd.wait()  # Wait until recording is finished
    wav.write(filename, fs, audio)
    print("✅ Recording saved:", filename)


if __name__ == "__main__":
    while True:
        input("Press ENTER to record...")
        record_audio("input.wav", duration=5)
        t0 = time.time()
        result = model.transcribe("input.wav")
        print(f"[stt] Transcription took {time.time()-t0:.2f}s")
        print("📝 Transcribed text:", result["text"])
