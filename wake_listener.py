import sounddevice as sd
import queue
import vosk
import json
import os

q = queue.Queue()

# Set the model path
model_path = "vosk-model-en-in-0.5"

if not os.path.exists(model_path):
    raise Exception("Please download and unzip the Vosk Indian model into: vosk-model-en-in-0.5")

model = vosk.Model(model_path)

def callback(indata, frames, time, status):
    if status:
        print("Audio Status:", status)
    q.put(bytes(indata))

def detect_wake_word(callback_fn):
    print("RAJ is listening for wake word...")

    # Only allow *exact* phrases, remove [unk] entirely
    wake_phrases = ["hey raj", "he raj", "hai raj", "hello raj", "ok raj","raj"]
    recognizer = vosk.KaldiRecognizer(model, 16000)
    grammar = "[" + ", ".join(['"%s"' % phrase for phrase in wake_phrases]) + "]"
    recognizer.SetGrammar(grammar)

    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype="int16",
                           channels=1, callback=callback):
        while True:
            data = q.get()
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").lower().strip()
                print("Heard:", text)

                if text in wake_phrases:
                    print("Wake word detected!")
                    callback_fn()
