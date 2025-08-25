import sounddevice as sd
import numpy as np
import whisper
import scipy.io.wavfile as wav

# Load Whisper model
model = whisper.load_model("base")  # can be "tiny", "small", "medium", "large"


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

        # Transcribe with Whisper
        result = model.transcribe("input.wav")
        print("📝 Transcribed text:", result["text"])
