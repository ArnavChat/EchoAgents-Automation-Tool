from TTS.api import TTS
import simpleaudio as sa

tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC")


def speak_text(text, output_file="response.wav"):
    """Synthesize speech to a file and play it."""
    tts.tts_to_file(text=text, file_path=output_file)
    wave_obj = sa.WaveObject.from_wave_file(output_file)
    play_obj = wave_obj.play()
    play_obj.wait_done()


if __name__ == "__main__":
    # Minimal demo: synthesize a test sentence
    speak_text("Text to speech is ready.")
