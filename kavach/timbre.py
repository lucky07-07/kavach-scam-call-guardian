# Gnani Timbre text-to-speech, shared by the Guardian (spoken warnings) and make_test_audio (test calls).
# Every clip is cached by (model, voice, language, speed, rate, text), so the same sentence is never paid for twice.
# Timbre streams its WAV, so the header's length fields are placeholders; pcm_of() takes the data chunk to the end.
import hashlib, io, time, wave
from pathlib import Path

import requests

from kavach.gnani_key import load_key

TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"
CACHE = Path(__file__).parent.parent / "data" / "tts_cache"


class TimbreError(RuntimeError):
    pass


def pcm_of(wav_bytes, rate):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, rate):
            raise TimbreError(f"unexpected Timbre format {w.getnchannels()} ch, {w.getsampwidth() * 8} bit, {w.getframerate()} Hz")
    pcm = wav_bytes[wav_bytes.find(b"data") + 8:]
    return pcm[:len(pcm) // 2 * 2]


def wav_of(pcm, rate, channels=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return buf.getvalue()


class Timbre:
    def __init__(self, api_key=None, session=None, cache=CACHE):
        self.key = api_key or load_key()
        self.http = session or requests.Session()
        self.cache = Path(cache)

    def speak(self, text, voice, model, language, rate=16000, speed=1.0):
        # returns 16-bit mono PCM at `rate`
        name = hashlib.sha256(f"{model}|{voice}|{language}|{speed}|{rate}|{text}".encode()).hexdigest()[:24]
        clip = self.cache / f"{name}.pcm"
        if clip.exists():
            return clip.read_bytes()
        if not self.key:
            raise TimbreError("No Gnani key: set GNANI_API_KEY or put it in Project/gnani.env")
        body = {"text": text, "voice": voice, "model": model, "language": language, "speed": speed,
                "audio_config": {"sample_rate": rate, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm", "container": "wav"}}
        for attempt in range(5):
            try:
                r = self.http.post(TTS_URL, headers={"X-API-Key-ID": self.key, "Content-Type": "application/json"},
                                   timeout=120, json=body)
            except requests.ConnectionError:   # resets on the TLS handshake; the request never reached Timbre
                if attempt == 4:
                    raise
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code != 429 or attempt == 4:
                break
            time.sleep(min(int(r.headers.get("Retry-After") or 0) or 15 * (attempt + 1), 120))
        if r.status_code >= 400:
            raise TimbreError(f"Timbre {r.status_code}: {r.text[:300]}")
        pcm = pcm_of(r.content, rate)
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(pcm)
        return pcm
