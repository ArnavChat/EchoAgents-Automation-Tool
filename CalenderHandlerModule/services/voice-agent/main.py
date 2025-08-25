from .stt import record_audio, transcribe
from .tts import speak_text

if __name__ == "__main__":
    while True:
        input("Press ENTER to talk...")
        audio_file = record_audio(duration=5)
        text = transcribe(audio_file)
        print("📝 You said:", text)

        # For MVP: echo back
        speak_text("You said: " + text)
