import asyncio
import os
import tempfile
import uuid

import pygame
from edge_tts import Communicate

try:
    import pyttsx3
except Exception:
    pyttsx3 = None


def _run_async(coro):
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop and running_loop.is_running():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    return asyncio.run(coro)


def _edge_tts_speak(text):
    filename = os.path.join(
        tempfile.gettempdir(),
        f"sam_tts_{uuid.uuid4().hex}.mp3",
    )
    communicate = Communicate(text, voice="en-IN-NeerjaNeural")

    async def generate_and_play():
        await communicate.save(filename)
        pygame.mixer.init()
        try:
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
        finally:
            pygame.mixer.quit()
            if os.path.exists(filename):
                os.remove(filename)

    _run_async(generate_and_play())


def _pyttsx3_speak(text):
    if not pyttsx3:
        raise RuntimeError("pyttsx3 is not available for fallback TTS.")
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()

def speak(text):
    try:
        _edge_tts_speak(text)
    except Exception as e:
        print(f"TTS error: {e}")
        try:
            _pyttsx3_speak(text)
        except Exception as fallback_error:
            print(f"Fallback TTS error: {fallback_error}")