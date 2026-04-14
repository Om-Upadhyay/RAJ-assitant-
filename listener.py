import speech_recognition as sr

def listen():
    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("Adjusting for background noise...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            print("Listening for command...")
            audio = recognizer.listen(source, timeout=7, phrase_time_limit=7)
            print("Recognizing...")
            query = recognizer.recognize_google(audio)
            print("Heard:", query)
            return query.lower()
    except sr.WaitTimeoutError:
        print("Timeout – no speech.")
    except sr.UnknownValueError:
        print("Could not understand.")
    except sr.RequestError:
        print("Speech service error.")
    except Exception as e:
        print("Error:", str(e))
    return ""
