import os
import sys
import threading
import time
import requests
import random
import re
import io
import asyncio
import hashlib
import hmac
import base64
import json
import traceback
import logging
import unicodedata
from datetime import datetime
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from thefuzz import process, fuzz
import sounddevice as sd
from scipy.io import wavfile
import numpy as np
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from shazamio import Shazam

AUDIO_INPUT_DEVICE = None

GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "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")
ACR_HOST          = os.getenv("ACR_HOST", "identify-eu-west-1.acrcloud.com")
ACR_ACCESS_KEY    = os.getenv("ACR_ACCESS_KEY", "decbcc1f6e68593c7f6fdbc603990533")
ACR_ACCESS_SECRET = os.getenv("ACR_ACCESS_SECRET", "Jas1pzmo7Y0qFSReLTWxTxV2Hznglzq7CzTBLno4")

TARGET_LANGUAGE = "es"

SOGLIA_AFFINITA_SYNC   = 65
SOGLIA_DOPPIA_VERIFICA = 50

SYNC_DEAD_ZONE         = 0.12
SYNC_MIN_DIFF_HARD     = 3.0
SYNC_SOFT_BLEND        = 0.60
SYNC_MAX_STEP_BASE     = 0.35
SYNC_MAX_STEP_PER_SEC  = 0.90
SYNC_MAX_STEP_CAP      = 1.40

LINE_VISUAL_OFFSET     = 0.00
WORD_VISUAL_OFFSET     = 0.00
EMOJI_WORD_OFFSET      = 0.08
LYRIC_FONT_MIN_SP      = 14
LYRIC_FONT_MAX_SP      = 80

SYNC_BOOTSTRAP_SECONDS = 10.0
SYNC_BOOTSTRAP_INTERVAL = 0.45
SYNC_BOOTSTRAP_DURATION = 2.80
SYNC_STEADY_INTERVAL    = 1.20
SYNC_STEADY_DURATION    = 3.80
SYNC_MAX_PENDING_SNAPSHOTS = 1
SYNC_APPLY_MIN_INTERVAL = 0.80
SONG_CHANGE_VERIFY_COOLDOWN = 9.0
SONG_CHANGE_VERIFY_MISS_IDLE = 4
SONG_CHANGE_VERIFY_MISS_SYNC = 6
SONG_CHANGE_VERIFY_WINDOW_SEC = 8.0
SONG_CHANGE_VERIFY_WARMUP_SEC = 6.0
SONG_CHANGE_FORCE_VERIFY_INTERVAL = 20.0
SONG_CHANGE_STRONG_MISMATCH_STREAK = 2

SONG_MATCH_FULL_OK = 78
SONG_MATCH_LOCAL_OK = 66
SONG_MISMATCH_STRONG_FULL_MAX = 58
SONG_MISMATCH_STRONG_LOCAL_MAX = 54

SYNC_TELEPORT_GUARD_SEC = 14.0
SYNC_TELEPORT_CONFIRMATIONS = 2
SYNC_STALE_SNAPSHOT_MAX_AGE = 9.0
SYNC_HARD_JUMP_COOLDOWN_SEC = 5.0
SYNC_HARD_JUMP_CAP_EARLY = 2.4
SYNC_HARD_JUMP_STARTUP_WINDOW = 10.0
SYNC_HARD_JUMP_STARTUP_CAP = 3.0
SYNC_HARD_JUMP_MAX_STEP = 2.8
SYNC_HARD_JUMP_REAPPLY_GAP = 1.20
SYNC_NO_ANCHOR_MAX_FORWARD_JUMP = 16.0

WHISPER_429_BACKOFF_SEC = 4.5

FONT_CHANGE_COOLDOWN_SEC = 45.0

DIAG_REFRESH_INTERVAL = 0.25
DIAG_RING_BUFFER_SIZE = 200

FINESTRA_RICERCA_BASE  = 10
FINESTRA_RICERCA_EXTRA = 6

LRCLIB_GOOD_SCORE = 220.0

PROGETTO_DIR = os.path.dirname(os.path.abspath(__file__))
CRASH_DIR    = os.path.join(PROGETTO_DIR, "crash")
LOGS_DIR     = os.path.join(PROGETTO_DIR, "logs")

os.makedirs(PROGETTO_DIR, exist_ok=True)
os.makedirs(CRASH_DIR,    exist_ok=True)
os.makedirs(LOGS_DIR,     exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.FileHandler(
            os.path.join(LOGS_DIR, f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
            encoding='utf-8'
        ),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("RayNeo")

HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update({"User-Agent": "RayNeo/1.0"})
HTTP_RETRY = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=0.25,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET", "HEAD", "OPTIONS"]),
)
HTTP_ADAPTER = HTTPAdapter(max_retries=HTTP_RETRY, pool_connections=16, pool_maxsize=16)
HTTP_SESSION.mount("https://", HTTP_ADAPTER)
HTTP_SESSION.mount("http://", HTTP_ADAPTER)


def http_get(url, **kwargs):
    return HTTP_SESSION.get(url, **kwargs)


def http_post(url, **kwargs):
    return HTTP_SESSION.post(url, **kwargs)

def save_crash_report(exc_type, exc_value, exc_tb):
    timestamp  = datetime.now().strftime('%Y%m%d_%H%M%S')
    crash_file = os.path.join(CRASH_DIR, f"crash_{timestamp}.txt")
    tb_lines   = traceback.format_exception(exc_type, exc_value, exc_tb)
    with open(crash_file, 'w', encoding='utf-8') as f:
        f.write(f"CRASH REPORT - {datetime.now()}\n{'='*60}\n")
        f.write(f"Tipo: {exc_type.__name__}\nMessaggio: {exc_value}\n\nTRACEBACK:\n")
        f.writelines(tb_lines)
        f.write(f"\nPython: {sys.version}\n")
    print(f"💥 CRASH SALVATO: {crash_file}")
    for line in tb_lines:
        print(line, end='')

sys.excepthook = save_crash_report
threading.excepthook = lambda args: save_crash_report(args.exc_type, args.exc_value, args.exc_traceback)
os.environ['KIVY_HOME'] = os.path.join(PROGETTO_DIR, "logs")

ASSETS_DIR = os.path.join(PROGETTO_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)

COOL_FONTS = {
    'Orbitron':   'https://github.com/google/fonts/raw/main/ofl/orbitron/static/Orbitron-Bold.ttf',
    'Audiowide':  'https://github.com/google/fonts/raw/main/ofl/audiowide/Audiowide-Regular.ttf',
    'Exo2':       'https://github.com/google/fonts/raw/main/ofl/exo2/static/Exo2-Bold.ttf',
    'Saira':      'https://github.com/google/fonts/raw/main/ofl/saira/static/Saira-Bold.ttf',
    'Teko':       'https://github.com/google/fonts/raw/main/ofl/teko/static/Teko-SemiBold.ttf',
    'RussoOne':   'https://github.com/google/fonts/raw/main/ofl/russoone/RussoOne-Regular.ttf',
    'Oxanium':    'https://github.com/google/fonts/raw/main/ofl/oxanium/static/Oxanium-Bold.ttf',
    'Michroma':   'https://github.com/google/fonts/raw/main/ofl/michroma/Michroma-Regular.ttf',
}

def download_fonts():
    available = []
    for name, url in COOL_FONTS.items():
        path = os.path.join(FONTS_DIR, f"{name}.ttf")
        if os.path.exists(path):
            available.append(path)
            continue
        try:
            print(f"📥 Download font: {name}...")
            r = http_get(url, timeout=15)
            if r.status_code == 200:
                with open(path, 'wb') as f:
                    f.write(r.content)
                available.append(path)
                print(f"   ✅ {name} scaricato")
            else:
                print(f"   ⚠️ {name} HTTP {r.status_code}")
        except Exception as e:
            print(f"   ⚠️ {name} errore: {e}")
    return available

AVAILABLE_FONTS = download_fonts()

from emojis import download_flag_images
download_flag_images(ASSETS_DIR)

from emojis import extract_emojis, extract_emoji_events, get_filename_for_emoji, FLAT_EMOJI_MAP

_EMOJI_TO_KEYWORDS = {}
for _kw, _emo in FLAT_EMOJI_MAP.items():
    _EMOJI_TO_KEYWORDS.setdefault(_emo, []).append(_kw.replace("_", " "))
for _emo in _EMOJI_TO_KEYWORDS:
    _EMOJI_TO_KEYWORDS[_emo].sort(key=len, reverse=True)

from kivy.config import Config
Config.set('graphics', 'width', '1280')
Config.set('graphics', 'height', '720')
Config.set('graphics', 'resizable', '1')

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.animation import Animation
from kivy.utils import platform
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.properties import NumericProperty

class RotatedEmoji(Label):
    angle = NumericProperty(0)

class RotatedImage(Image):
    angle = NumericProperty(0)

KV = '''
<RotatedEmoji>:
    font_size: '75sp'
    canvas.before:
        PushMatrix
        Rotate:
            angle: self.angle
            origin: self.center
    canvas.after:
        PopMatrix

<RotatedImage>:
    canvas.before:
        PushMatrix
        Rotate:
            angle: self.angle
            origin: self.center
    canvas.after:
        PopMatrix

FloatLayout:
    canvas.before:
        Color:
            rgba: 0, 0, 0, 1
        Rectangle:
            pos: self.pos
            size: self.size

    Label:
        id: sync_indicator
        text: "[b]Standby ⏳[/b]"
        markup: True
        size_hint: None, None
        size: root.width * 0.23, root.height * 0.07
        pos_hint: {'x': 0.02, 'top': 0.98}
        font_size: root.height * 0.028
        color: [0.5, 0.5, 0.5, 1]
        halign: 'left'
        valign: 'top'
        text_size: self.size

    Label:
        id: diag_label
        text: ""
        size_hint: None, None
        size: root.width * 0.36, root.height * 0.24
        pos_hint: {'right': 0.985, 'top': 0.98}
        font_size: root.height * 0.014
        color: [0.3, 1, 0.4, 0.95]
        opacity: 0
        halign: 'left'
        valign: 'top'
        text_size: self.size

    BoxLayout:
        id: main_content
        orientation: 'vertical'
        size_hint: 1, 1
        opacity: 0

        BoxLayout:
            size_hint_y: 0.10
            padding: [20, 5]
            spacing: 10
            TextInput:
                id: title_input
                hint_text: "Ricerca Manuale (Opzionale)"
                multiline: False
                font_size: root.height * 0.021
                background_color: [0.1, 0.1, 0.1, 1]
                foreground_color: [1, 1, 1, 1]
            Button:
                id: manual_search_btn
                text: "CERCA"
                size_hint_x: 0.2
                bold: True
                font_size: root.height * 0.021
                text_size: self.size
                halign: 'center'
                valign: 'middle'
                background_color: [0.6, 0, 0.9, 1]
                on_press: app.start_manual_search(title_input.text)

        BoxLayout:
            size_hint_y: 0.08
            padding: [20, 0]
            spacing: 10
            Button:
                id: omni_toggle_btn
                text: "👁️ OMNI-LISTEN: OFF"
                bold: True
                font_size: root.height * 0.021
                text_size: self.size
                halign: 'center'
                valign: 'middle'
                background_color: [1, 0.4, 0, 1]
                on_press: app.toggle_omni_listen()
            Button:
                id: sync_toggle_btn
                text: "⏸️ SYNC: OFF"
                bold: True
                font_size: root.height * 0.021
                text_size: self.size
                halign: 'center'
                valign: 'middle'
                size_hint_x: 0.33
                background_color: [0.5, 0.5, 0.5, 1]
                on_press: app.toggle_sync_mode()
            Button:
                id: diag_toggle_btn
                text: "🧪 DIAG: OFF"
                bold: True
                font_size: root.height * 0.021
                text_size: self.size
                halign: 'center'
                valign: 'middle'
                size_hint_x: 0.27
                background_color: [0.35, 0.35, 0.35, 1]
                on_press: app.toggle_diagnostic_mode()

        BoxLayout:
            size_hint_y: 0.05
            padding: [20, 0]
            Label:
                id: track_label
                text: ""
                font_size: root.height * 0.019
                color: [0.8, 0, 1, 0.5]
                text_size: self.width, None
                halign: 'center'
                valign: 'middle'

        ScrollView:
            size_hint_y: 0.22
            BoxLayout:
                id: results_list
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: 2

        BoxLayout:
            orientation: 'vertical'
            padding: [40, 10]
            spacing: 15
            Label:
                id: lyric_prev
                text: ""
                font_size: root.height * 0.036
                color: [1, 1, 1, 0.45]
                opacity: 0
                markup: True
                halign: 'center'
                text_size: root.width - 80, self.height
                max_lines: 1
                shorten: True
                shorten_from: 'right'
            FloatLayout:
                size_hint_y: 1
                Label:
                    id: lyric_glow
                    text: ""
                    font_size: root.height * 0.072
                    bold: False
                    color: [0, 0, 0, 0]
                    halign: 'center'
                    valign: 'middle'
                    markup: True
                    size_hint: 1, 1
                    pos_hint: {'center_x': 0.5, 'center_y': 0.5}
                    text_size: root.width - 40, None
                    max_lines: 4
                    outline_width: 0
                    outline_color: [0, 0, 0, 0]
                Label:
                    id: lyric_curr
                    text: "ACCENDI OMNI-LISTEN PER INIZIARE"
                    font_size: root.height * 0.072
                    bold: False
                    color: [1, 1, 1, 1]
                    halign: 'center'
                    valign: 'middle'
                    opacity: 1
                    markup: True
                    size_hint: 1, 1
                    pos_hint: {'center_x': 0.5, 'center_y': 0.5}
                    text_size: root.width - 40, None
                    max_lines: 4
                    outline_width: 0
                    outline_color: [0, 0, 0, 0]
            Label:
                id: lyric_next
                text: ""
                font_size: root.height * 0.036
                color: [1, 1, 1, 0.45]
                opacity: 0
                markup: True
                halign: 'center'
                text_size: root.width - 80, self.height
                max_lines: 1
                shorten: True
                shorten_from: 'right'

        BoxLayout:
            size_hint_y: 0.08
            padding: [0, 0, 0, 15]
            Label:
                id: status_label
                text: "HUD AR Pronto - Sync Engine V5"
                font_size: root.height * 0.019
                color: [0.8, 0, 1, 0.5]
                text_size: self.width, None
                halign: 'center'

    Label:
        id: no_sync_label
        text: "⚠️ No Sync"
        size_hint: None, None
        size: root.width * 0.12, root.height * 0.056
        pos_hint: {'center_x': 0.5, 'y': 0.12}
        color: [1, 0.2, 0.2, 1]
        font_size: root.height * 0.025
        bold: True
        opacity: 0
        text_size: self.size
        halign: 'center'
        valign: 'middle'

    Label:
        id: start_splash
        text: "[b]START[/b]"
        markup: True
        size_hint: None, None
        size: root.width, root.height * 0.25
        pos_hint: {'center_x': 0.5, 'center_y': 0.55}
        color: [1, 1, 1, 1]
        font_size: root.height * 0.14
        halign: 'center'
        valign: 'middle'
        text_size: self.size
        opacity: 0

    FloatLayout:
        id: emoji_layer
        size_hint: 1, 1

    Label:
        text: "© 2026 Σ. Alle Rechte vorbehalten."
        size_hint: None, None
        size: root.width, root.height * 0.03
        pos_hint: {'center_x': 0.5, 'y': 0.005}
        font_size: root.height * 0.014
        color: [0.4, 0.4, 0.4, 0.4]
        halign: 'center'
        valign: 'bottom'
        text_size: self.size
'''

def clean_text(t: str) -> str:
    return re.sub(r"[^\w\s]", "", t.lower()).strip()

def normalize_title(t: str) -> str:
    return re.sub(r'[^a-z0-9 ]', '', t.lower().strip())

def titles_match(a: str, b: str) -> bool:
    return fuzz.token_sort_ratio(normalize_title(a), normalize_title(b)) >= 80

_FONT_CHAR_MAP = str.maketrans({
    '\u2018': "'", '\u2019': "'",
    '\u201C': '"', '\u201D': '"',
    '\u2014': '-',  '\u2013': '-',
    '\u00AB': '"',  '\u00BB': '"',
    '\u2032': "'",  '\u2033': '"',
    '\u200B': '',   '\u200C': '',   '\u200D': '',  '\uFEFF': '',
    '\u00A0': ' ',
})

def sanitize_for_font(text: str) -> str:
    text = text.translate(_FONT_CHAR_MAP)
    text = text.replace('\u2026', '...')
    # Normalize accented glyphs to base ASCII so decorative fonts don't show tofu squares.
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return text

def normalize_audio(raw):
    peak = float(np.max(np.abs(raw)))
    if peak < 0.005:
        return None, peak
    if peak >= 0.99:
        raw = raw * 0.3
        peak = float(np.max(np.abs(raw)))
    if peak > 0.01:
        raw = raw * (0.8 / peak)
    return (raw * 32767).clip(-32768, 32767).astype(np.int16), peak


class ContinuousRecorder:
    """Ring-buffer audio recorder using sd.InputStream for zero-gap capture."""

    def __init__(self, fs=16000, buffer_seconds=7):
        self.fs = fs
        self.buffer_size = int(fs * buffer_seconds)
        self.buffer = np.zeros(self.buffer_size, dtype='float32')
        self.write_pos = 0
        self.lock = threading.Lock()
        self.stream = None
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True
        self.buffer[:] = 0
        self.write_pos = 0
        self.stream = sd.InputStream(
            samplerate=self.fs,
            channels=1,
            dtype='float32',
            device=AUDIO_INPUT_DEVICE,
            callback=self._callback,
            blocksize=1024,
        )
        self.stream.start()

    def stop(self):
        self.running = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _callback(self, indata, frames, time_info, status):
        data = indata[:, 0]
        n = len(data)
        with self.lock:
            end = self.write_pos + n
            if end <= self.buffer_size:
                self.buffer[self.write_pos:end] = data
            else:
                first = self.buffer_size - self.write_pos
                self.buffer[self.write_pos:] = data[:first]
                self.buffer[:n - first] = data[first:]
            self.write_pos = (self.write_pos + n) % self.buffer_size

    def get_last_seconds(self, seconds):
        """Return the last N seconds of audio as float32 array."""
        n_samples = min(int(self.fs * seconds), self.buffer_size)
        with self.lock:
            end = self.write_pos
            start = end - n_samples
            if start >= 0:
                return self.buffer[start:end].copy()
            else:
                return np.concatenate([
                    self.buffer[start % self.buffer_size:],
                    self.buffer[:end]
                ]).copy()


@lru_cache(maxsize=4096)
def count_syllables(word: str) -> int:
    word = re.sub(r"[^\w]", "", word.lower())
    vowels = "aeiou\u00e1\u00e9\u00ed\u00f3\u00fa\u00fc"
    count, prev_vowel = 0, False
    for ch in word:
        is_v = ch in vowels
        if is_v and not prev_vowel:
            count += 1
        prev_vowel = is_v
    return max(1, count)


def find_keyword_token_index(line_tokens, keyword_tokens):
    if not line_tokens or not keyword_tokens or len(keyword_tokens) > len(line_tokens):
        return None
    k_len = len(keyword_tokens)
    for i in range(len(line_tokens) - k_len + 1):
        if line_tokens[i:i + k_len] == keyword_tokens:
            return i + (k_len // 2)
    return None

HALL_FRASES = frozenset([
    "suscribete al canal", "suscr\u00edbete al canal",
    "suscribete", "suscr\u00edbete",
    "gracias por ver", "muchas gracias",
    "no olvides suscribirte", "like y suscribete",
    "subtitulos por", "sottotitoli",
    "muy bien", "muy bien!", "\u00a1muy bien",
    "\u00a1suscr\u00edbete", "suscr\u00edbete al",
    "hasta la pr\u00f3xima", "nos vemos",
    "deja tu like", "comenta",
    "activa la campanita", "comparte",
])
HALL_PAROLE = frozenset([
    "gracias", "\u00a1gracias", "gracias!",
    "subtitulos", "amara", "iscriviti",
    "thank you", "thanks", "subscribe", "pum", "boom",
    "letras", "canciones", "urbana",
    "m\u00fasica", "musica", "music", "musical",
    "aplausos", "bravo", "ole", "ol\u00e9",
    "silencio", "instrumental", "intro",
])

def estimate_phrase_start_in_buffer(text: str, buffer_duration: float, whisper_latency: float = 0.0) -> float:
    words = text.split()
    total_syl = sum(count_syllables(w) for w in words)
    estimated_phrase_duration = total_syl * 0.14
    offset = buffer_duration - estimated_phrase_duration
    offset = max(0.05, min(offset, buffer_duration - 0.2))
    return offset

def sign_acr_request(method, uri, access_key, access_secret, data_type, signature_version, timestamp):
    string_to_sign = "\n".join([method, uri, access_key, data_type, signature_version, timestamp])
    sign = base64.b64encode(
        hmac.new(access_secret.encode('ascii'), string_to_sign.encode('ascii'), digestmod=hashlib.sha1).digest()
    ).decode('ascii')
    return sign

def recognize_with_acrcloud(audio_bytes: bytes, sample_rate: int = 44100) -> dict | None:
    if not ACR_ACCESS_KEY or not ACR_ACCESS_SECRET or not ACR_HOST:
        print("[ACRCloud] Config mancante: imposta ACR_HOST/ACR_ACCESS_KEY/ACR_ACCESS_SECRET")
        return None
    try:
        timestamp = str(int(time.time()))
        uri = "/v1/identify"
        data_type = "audio"
        signature_version = "1"

        signature = sign_acr_request(
            "POST", uri, ACR_ACCESS_KEY, ACR_ACCESS_SECRET,
            data_type, signature_version, timestamp
        )

        files = {
            'sample': ('audio.wav', audio_bytes, 'audio/wav'),
            'access_key': (None, ACR_ACCESS_KEY),
            'data_type': (None, data_type),
            'signature_version': (None, signature_version),
            'signature': (None, signature),
            'sample_rate': (None, str(sample_rate)),
            'timestamp': (None, timestamp),
        }

        url = f"https://{ACR_HOST}{uri}"
        print(f"[ACRCloud] Contatto: {url}")
        resp = http_post(url, files=files, timeout=5)

        if resp.status_code != 200:
            print(f"[ACRCloud] HTTP {resp.status_code}: {resp.text[:100]}")
            return None

        j = resp.json()
        status_code = j.get('status', {}).get('code', -1)
        print(f"[ACRCloud] Status code risposta: {status_code} "
              f"({j.get('status', {}).get('msg', '')})")

        if status_code == 0:
            music = j['metadata']['music'][0]
            title = music.get('title', '')
            artist = music.get('artists', [{}])[0].get('name', '')
            return {'title': title, 'artist': artist}
    except Exception as e:
        print(f"[ACRCloud] Errore: {e}")
    return None

class RayNeoTestApp(App):
    def build(self):
        print("\n🎧 Dispositivi audio disponibili:")
        try:
            devs = sd.query_devices()
            for i, d in enumerate(devs):
                if d['max_input_channels'] > 0:
                    marker = " ◄ DEFAULT" if i == sd.default.device[0] else ""
                    print(f"   [{i}] {d['name']}{marker}")
        except Exception as e:
            print(f"   Errore: {e}")
        print()
        self.root_ui = Builder.load_string(KV)
        # Ensure phrases are never truncated by widget shortening.
        for lbl_id in ('lyric_prev', 'lyric_curr', 'lyric_next', 'lyric_glow'):
            lbl = self.root_ui.ids[lbl_id]
            lbl.shorten = False
            lbl.max_lines = 4
        self._update_lyric_text_bounds()
        Window.bind(size=self._on_window_resize)
        self.lyrics_data = []
        self.current_index = 0
        self.start_timestamp = 0
        self.is_playing = False

        self.omni_mode = False
        self.is_ai_processing = False
        self.sync_lock = False

        self.consecutive_misses = 0
        self.sync_confidence = 1.0

        self.anchor_song_time = None
        self.anchor_real_time = None

        self.sync_enabled = False

        self.max_song_time_reached = 0.0

        self.sync_history = []

        self.remix_miss_streak = 0

        self.sync_perfect_streak = 0
        self.sync_verify_mode    = False

        self.current_song_title  = ""
        self.current_song_artist = ""
        self._needs_song_verification = False

        self.emoji_timers = []
        self.last_active_word_idx = -1
        self.last_lyric_idx = -1
        self._last_word_switch_time = 0.0

        self._sync_processing_lock = threading.Lock()
        self._last_sync_snapshot = 0
        self._continuous_recorder = None
        self._sync_locked = False
        self._sync_fast_until = 0.0
        self._last_sync_apply_time = 0.0
        self._last_song_verify_request = 0.0
        self._pending_far_jump_time = None
        self._pending_far_jump_hits = 0
        self._sync_start_time = 0.0
        self._first_lock_time = 0.0
        self._verify_miss_hall = deque(maxlen=64)
        self._verify_miss_mismatch = deque(maxlen=64)
        self._recognition_commit_token = None
        self._recognition_commit_pending = False
        self._song_mismatch_strong_streak = 0
        self._last_forced_song_verify_time = 0.0
        self._whisper_backoff_until = 0.0
        self._last_hard_jump_time = 0.0
        self._last_font_change_time = 0.0
        self._sync_apply_token = 0

        self.diagnostic_mode = False
        self._diag_stats = {
            'latency_ms': 0,
            'snapshot_age_s': 0.0,
            'partial': 0,
            'sort': 0,
            'expected_t': 0.0,
            'matched_t': 0.0,
            'applied_step': 0.0,
            'jump_blocked': 0,
            'verify_requests': 0,
            'state': 'IDLE',
        }
        self._diag_events = deque(maxlen=DIAG_RING_BUFFER_SIZE)
        self._diag_log_path = None
        self._diag_log_file = None
        self._diag_marks = {}
        self._diag_first_sync_locked = False

        self.neon_colors = {
            'green': '39FF14',
            'cyan': '00FFFF',
            'magenta': 'FF00FF',
            'yellow': 'FFD700',
            'hot_pink': 'FF1493',
            'electric_blue': '7DF9FF',
            'orange': 'FF6600',
            'lime': 'CCFF00',
        }
        self.current_neon = self.neon_colors['green']
        self.current_font = None
        self._apply_random_font(force=True)
        Clock.schedule_once(self._run_startup_animation, 0.05)
        Clock.schedule_interval(self._diag_refresh_ui, DIAG_REFRESH_INTERVAL)

        threading.Thread(target=self.master_omni_loop, daemon=True).start()
        return self.root_ui

    def _on_window_resize(self, *args):
        self._update_lyric_text_bounds()

    def _update_lyric_text_bounds(self):
        if not getattr(self, 'root_ui', None):
            return
        ids = self.root_ui.ids
        center_w = max(260, int(Window.width - 40))
        side_w = max(220, int(Window.width - 100))
        ids.lyric_curr.text_size = (center_w, None)
        ids.lyric_glow.text_size = (center_w, None)
        ids.lyric_prev.text_size = (side_w, None)
        ids.lyric_next.text_size = (side_w, None)

    def _run_startup_animation(self, dt=0):
        ids = self.root_ui.ids
        splash = ids.start_splash
        content = ids.main_content

        splash.opacity = 0
        content.opacity = 0

        splash_anim = (
            Animation(opacity=1, duration=0.50, t='out_quad') +
            Animation(opacity=1, duration=0.35) +
            Animation(opacity=0, duration=0.40, t='in_quad')
        )
        splash_anim.start(splash)

        def reveal_ui(_dt):
            Animation(opacity=1, duration=0.60, t='out_quad').start(content)
            stagger_ids = [
                'title_input',
                'manual_search_btn',
                'omni_toggle_btn',
                'sync_toggle_btn',
                'diag_toggle_btn',
                'track_label',
                'status_label',
            ]
            for i, wid_id in enumerate(stagger_ids):
                w = ids.get(wid_id)
                if not w:
                    continue
                w.opacity = 0
                Clock.schedule_once(
                    lambda _x, ww=w: Animation(opacity=1, duration=0.35, t='out_quad').start(ww),
                    0.08 * i
                )

        Clock.schedule_once(reveal_ui, 0.75)

    def _apply_random_font(self, force: bool = False):
        now = time.time()
        if not force and (now - self._last_font_change_time) < FONT_CHANGE_COOLDOWN_SEC:
            return
        if AVAILABLE_FONTS:
            candidates = [f for f in AVAILABLE_FONTS if f != self.current_font]
            if not candidates:
                candidates = AVAILABLE_FONTS
            self.current_font = random.choice(candidates)
        else:
            self.current_font = None
        self._last_font_change_time = now
        font_name = os.path.splitext(os.path.basename(self.current_font))[0] if self.current_font else 'Default'
        print(f"🔤 Font selezionato: {font_name}")
        def _set(dt):
            for lbl_id in ('lyric_prev', 'lyric_curr', 'lyric_next', 'lyric_glow'):
                try:
                    lbl = self.root_ui.ids[lbl_id]
                    if self.current_font:
                        lbl.font_name = self.current_font
                except Exception:
                    pass
        Clock.schedule_once(_set, 0)

    def _update_glow_color(self):
        def _set(dt):
            try:
                r = int(self.current_neon[0:2], 16) / 255.0
                g = int(self.current_neon[2:4], 16) / 255.0
                b = int(self.current_neon[4:6], 16) / 255.0
                glow = self.root_ui.ids.lyric_glow
                glow.color = [r, g, b, 0.25]
                glow.outline_width = 6
                glow.outline_color = [r, g, b, 0.15]
                curr = self.root_ui.ids.lyric_curr
                curr.outline_width = 2
                curr.outline_color = [r * 0.5, g * 0.5, b * 0.5, 0.3]
            except Exception:
                pass
        Clock.schedule_once(_set, 0)

    def _fit_text_sp(self, text: str, max_sp: int, min_sp: int, avail_width: float) -> int:
        if not text:
            return max(min_sp, min(max_sp, int(Window.height * 0.03)))

        plain = text.replace('[', '').replace(']', '')
        words = plain.split()
        chars = max(1, len(plain))
        longest_word = max((len(w) for w in words), default=chars)
        target_lines = 2 if chars > 24 else 1
        eff_chars = max(longest_word, int(chars / target_lines))
        avg_glyph = 0.62
        est_sp = int(avail_width / max(1.0, eff_chars * avg_glyph))
        return max(min_sp, min(max_sp, est_sp))

    def toggle_omni_listen(self):
        self.omni_mode = not self.omni_mode
        if self.omni_mode:
            self._diag_mark('song_button_click')
            self._diag_event('song_button_click', source='omni_toggle')
            self.root_ui.ids.omni_toggle_btn.text = "👁️ OMNI-LISTEN: ON (Auto)"
            self.root_ui.ids.omni_toggle_btn.background_color = [0, 0.8, 0, 1]
            if self.lyrics_data:
                self._needs_song_verification = True
                self.set_status("🔄 Verifico se è la stessa canzone...")
            else:
                self.set_status("🔄 Omni-Mode ON. Ricerca e Sync Automatico...")
        else:
            self.root_ui.ids.omni_toggle_btn.text = "👁️ OMNI-LISTEN: OFF"
            self.root_ui.ids.omni_toggle_btn.background_color = [1, 0.4, 0, 1]
            if self.sync_enabled:
                self.set_status("⏸️ Omni-Mode OFF — Sync ancora attivo.")
            else:
                self.set_status("⏸️ Omni-Mode OFF.")
                self.update_sync_ui("Standby ⏳", [0.5, 0.5, 0.5, 1])

    def toggle_sync_mode(self):
        self.sync_enabled = not self.sync_enabled

        if self.sync_enabled:
            self.anchor_song_time      = None
            self.anchor_real_time      = None
            self.sync_perfect_streak   = 0
            self.sync_verify_mode      = False
            self.sync_confidence       = 0.0
            self.consecutive_misses    = 0
            self.max_song_time_reached = 0.0
            self.sync_history          = []
            self._last_sync_snapshot   = 0
            if self.lyrics_data and self.is_playing:
                print(f"🔄 Sync riattivato — anchor e finestra resettati, cerco in tutta la canzone")
        else:
            self._stop_continuous_recorder()

        def _ui(dt):
            if self.sync_enabled:
                self.root_ui.ids.sync_toggle_btn.text = "🔄 SYNC: ON"
                self.root_ui.ids.sync_toggle_btn.background_color = [0, 0.7, 0.3, 1]
                self.set_status("🔄 Sync ATTIVO — ricalibro posizione...")
            else:
                self.root_ui.ids.sync_toggle_btn.text = "⏸️ SYNC: OFF"
                self.root_ui.ids.sync_toggle_btn.background_color = [0.5, 0.5, 0.5, 1]
                self.set_status("⏸️ Sync SPENTO — il testo scorre libero.")
        Clock.schedule_once(_ui, 0)

    def toggle_diagnostic_mode(self):
        self.diagnostic_mode = not self.diagnostic_mode
        btn = self.root_ui.ids.diag_toggle_btn
        diag_label = self.root_ui.ids.diag_label

        if self.diagnostic_mode:
            btn.text = "🧪 DIAG: ON"
            btn.background_color = [0.1, 0.6, 0.9, 1]
            diag_label.opacity = 1
            self._diag_log_path = os.path.join(LOGS_DIR, f"diag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
            try:
                self._diag_log_file = open(self._diag_log_path, 'a', encoding='utf-8')
            except Exception:
                self._diag_log_file = None
            self._diag_set(state="DIAG_ON")
            self.set_status("🧪 Diagnostic mode ON")
        else:
            btn.text = "🧪 DIAG: OFF"
            btn.background_color = [0.35, 0.35, 0.35, 1]
            diag_label.opacity = 0
            self._diag_set(state="DIAG_OFF")
            self.set_status("🧪 Diagnostic mode OFF")
            if self._diag_log_file is not None:
                try:
                    self._diag_log_file.close()
                except Exception:
                    pass
                self._diag_log_file = None

    def _diag_set(self, **kwargs):
        self._diag_stats.update(kwargs)

    def _diag_mark(self, name: str, t: float | None = None):
        self._diag_marks[name] = time.time() if t is None else float(t)

    def _diag_elapsed(self, start_name: str, end_t: float | None = None):
        t0 = self._diag_marks.get(start_name)
        if t0 is None:
            return None
        t1 = time.time() if end_t is None else float(end_t)
        return max(0.0, t1 - t0)

    def _reset_verify_miss_windows(self):
        self._verify_miss_hall.clear()
        self._verify_miss_mismatch.clear()

    def _register_verify_miss(self, miss_type: str, limit: int):
        now = time.time()
        dq = self._verify_miss_hall if miss_type == 'hall' else self._verify_miss_mismatch
        dq.append(now)
        cutoff = now - SONG_CHANGE_VERIFY_WINDOW_SEC
        while dq and dq[0] < cutoff:
            dq.popleft()

        # Warmup guard: avoid aggressive track-switch checks immediately after sync start.
        if self.sync_enabled and self._sync_start_time > 0:
            if (now - self._sync_start_time) < SONG_CHANGE_VERIFY_WARMUP_SEC:
                return False, len(dq)

        return len(dq) >= limit, len(dq)

    def _diag_event(self, event_name: str, **payload):
        ts = time.time()
        entry = {'ts': ts, 'event': event_name, **payload}
        self._diag_events.append(entry)
        if self.diagnostic_mode and self._diag_log_file is not None:
            try:
                self._diag_log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self._diag_log_file.flush()
            except Exception:
                pass

    def _diag_refresh_ui(self, dt):
        if not getattr(self, 'root_ui', None):
            return
        lbl = self.root_ui.ids.diag_label
        if not self.diagnostic_mode:
            lbl.text = ""
            return

        s = self._diag_stats
        lbl.text = (
            f"DIAG\n"
            f"state: {s.get('state', 'IDLE')}\n"
            f"latency_ms: {int(s.get('latency_ms', 0))}\n"
            f"snapshot_age_s: {s.get('snapshot_age_s', 0.0):.2f}\n"
            f"match_p/s: {int(s.get('partial', 0))}/{int(s.get('sort', 0))}\n"
            f"expected_t: {s.get('expected_t', 0.0):.1f}s\n"
            f"matched_t: {s.get('matched_t', 0.0):.1f}s\n"
            f"applied_step: {s.get('applied_step', 0.0):.2f}s\n"
            f"jump_blocked: {int(s.get('jump_blocked', 0))}\n"
            f"verify_req: {int(s.get('verify_requests', 0))}"
        )

    def show_no_sync_warning(self, txt="⚠️ No Sync"):
        def _anim(dt):
            lbl = self.root_ui.ids.no_sync_label
            lbl.text = txt
            lbl.opacity = 1
            anim = Animation(opacity=1, duration=1.0) + Animation(opacity=0, duration=0.5)
            anim.start(lbl)
        Clock.schedule_once(_anim)

    def set_status(self, msg):
        self.root_ui.ids.status_label.text = msg

    def update_sync_ui(self, text, color_rgba):
        def _update(dt):
            self.root_ui.ids.sync_indicator.text = f"[b]{text}[/b]"
            self.root_ui.ids.sync_indicator.color = color_rgba
        Clock.schedule_once(_update)

    def update_track_ui(self, title="", artist=""):
        def _update(dt):
            if title:
                self.root_ui.ids.track_label.text = f"🎵 {title} — {artist}" if artist else f"🎵 {title}"
            else:
                self.root_ui.ids.track_label.text = ""
        Clock.schedule_once(_update)

    def _score_lrclib_candidate(self, item: dict, wanted_title: str = "", wanted_artist: str = ""):
        synced = (item.get('syncedLyrics') or "").strip()
        if not synced:
            return -1e9, {'lines': 0, 'duration': 0.0, 'words': 0}

        ts_lines = re.findall(r'^\[(\d+:\d+\.\d+)\]', synced, flags=re.MULTILINE)
        times = []
        for ts in ts_lines:
            try:
                times.append(self._lrc_time_to_sec(ts))
            except Exception:
                pass

        line_count = len(times)
        duration = (max(times) - min(times)) if len(times) >= 2 else 0.0

        plain = re.sub(r'<\d+:\d+\.\d+>', ' ', synced)
        plain = re.sub(r'^\[\d+:\d+\.\d+\]', '', plain, flags=re.MULTILINE)
        plain = re.sub(r'\s+', ' ', plain).strip()
        words = len(clean_text(plain).split())
        chars = len(plain)

        title_db = item.get('trackName') or item.get('title') or ""
        artist_db = item.get('artistName') or item.get('artist') or ""

        title_bonus = 0.0
        artist_bonus = 0.0
        if wanted_title and title_db:
            title_bonus = fuzz.token_sort_ratio(normalize_title(wanted_title), normalize_title(title_db)) * 0.35
        if wanted_artist and artist_db:
            artist_bonus = fuzz.token_sort_ratio(normalize_title(wanted_artist), normalize_title(artist_db)) * 0.20

        score = (
            min(180.0, line_count * 3.0) +
            min(140.0, duration * 0.9) +
            min(120.0, words * 0.6) +
            min(80.0, chars / 18.0) +
            title_bonus + artist_bonus
        )

        # Penalize snippets / short hooks that look incomplete.
        if line_count < 10:
            score -= 80
        if duration < 75:
            score -= 70
        if words < 120:
            score -= 45

        return score, {'lines': line_count, 'duration': duration, 'words': words}

    def _pick_best_synced_candidate(self, entries, wanted_title: str = "", wanted_artist: str = ""):
        best_item = None
        best_score = -1e9
        best_meta = {'lines': 0, 'duration': 0.0, 'words': 0}

        for item in (entries or []):
            if not isinstance(item, dict) or not item.get('syncedLyrics'):
                continue
            score, meta = self._score_lrclib_candidate(item, wanted_title, wanted_artist)
            if score > best_score:
                best_score = score
                best_item = item
                best_meta = meta

        return best_item, best_score, best_meta

    def _search_lrclib_best(self, query: str, wanted_title: str = "", wanted_artist: str = ""):
        r = http_get("https://lrclib.net/api/search", params={"q": query}, timeout=5)
        results = r.json()
        best, score, meta = self._pick_best_synced_candidate(results, wanted_title, wanted_artist)
        return best, score, meta

    def _estimate_presync_hint_from_audio(self, rec_int16, fs: int, clip_end_time: float):
        """Estimate current song time from recognition clip to reduce initial sync lag."""
        if not GROQ_API_KEY or not self.lyrics_data:
            return None
        if time.time() < self._whisper_backoff_until:
            return None

        try:
            wav_buf = io.BytesIO()
            wavfile.write(wav_buf, fs, rec_int16)
            wav_buf.seek(0)

            headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
            data = {
                "model": "whisper-large-v3-turbo",
                "language": TARGET_LANGUAGE,
                "temperature": "0.0",
                "response_format": "verbose_json",
            }
            resp = http_post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                files={"file": ("presync.wav", wav_buf, "audio/wav")},
                data=data,
                timeout=8,
            )

            if resp.status_code == 429:
                self._whisper_backoff_until = time.time() + WHISPER_429_BACKOFF_SEC
                self._diag_event("presync_whisper_429", backoff_s=WHISPER_429_BACKOFF_SEC)
                return None
            if resp.status_code != 200:
                self._diag_event("presync_whisper_http", status=resp.status_code)
                return None

            j = resp.json()
            probe_text = (j.get('text') or "").strip()
            probe_clean = clean_text(probe_text)
            if len(probe_clean) < 5:
                return None

            pool = [
                {
                    'index': i,
                    'time': row['time'],
                    'clean': row.get('clean') or clean_text(row.get('text', '')),
                }
                for i, row in enumerate(self.lyrics_data)
                if len(row.get('text', '')) >= 5
            ]
            if not pool:
                return None

            pool_dict = {i: p['clean'] for i, p in enumerate(pool)}
            best = process.extractOne(probe_clean, pool_dict, scorer=fuzz.partial_ratio)
            if not best or best[1] < 68:
                self._diag_event("presync_probe_weak", score=(best[1] if best else 0))
                return None

            matched = pool[best[2]]
            phrase_offset = estimate_phrase_start_in_buffer(probe_text, 3.0, 0.0)
            tail_after_phrase = max(0.0, 3.0 - phrase_offset)
            song_time_at_clip_end = matched['time'] + tail_after_phrase
            song_time_now = song_time_at_clip_end + max(0.0, time.time() - clip_end_time)

            max_song_t = self.lyrics_data[-1]['time'] if self.lyrics_data else song_time_now
            song_time_now = max(0.0, min(song_time_now, max_song_t))

            self._diag_event(
                "presync_hint",
                matched_t=round(matched['time'], 3),
                score=best[1],
                hint_now=round(song_time_now, 3),
            )
            return song_time_now
        except Exception as e:
            self._diag_event("presync_error", error=str(e))
            return None

    def _request_song_verification(self, reason: str = ""):
        now = time.time()
        if self._needs_song_verification:
            return False
        if now - self._last_song_verify_request < SONG_CHANGE_VERIFY_COOLDOWN:
            return False

        self._last_song_verify_request = now
        self._last_forced_song_verify_time = now
        self._needs_song_verification = True
        self._reset_verify_miss_windows()
        self._song_mismatch_strong_streak = 0
        self._diag_stats['verify_requests'] = int(self._diag_stats.get('verify_requests', 0)) + 1
        self._diag_set(state="VERIFY_REQUEST")
        self._diag_event("verify_request", reason=reason)
        if reason:
            print(f"🔎 Verifica brano richiesta: {reason}")
        self.update_sync_ui("Verifica Shazam... 🔄", [1, 0.8, 0, 1])
        return True

    def _verify_or_change_song(self):
        """Verifica completa con riconoscimento parallelo (Shazam×2 + ACR)."""
        self._needs_song_verification = False
        try:
            fs = 44100
            duration_long = 3.0
            overlap = 1.0
            print("\n🔍 Verifica brano in corso (rilevamento parallelo)...")

            rec_long = sd.rec(int(duration_long * fs), samplerate=fs, channels=1,
                              dtype='float32', device=AUDIO_INPUT_DEVICE)
            sd.wait()
            clip_end_time = time.time()

            rec_A, peak_A = normalize_audio(rec_long.copy())
            rec_B, peak_B = normalize_audio(rec_long[int(overlap * fs):].copy())

            if rec_A is None:
                print("🔇 Verifica: silenzio — riprovo al prossimo ciclo")
                self._needs_song_verification = True
                return

            path_A = os.path.join(PROGETTO_DIR, "verify_A.wav")
            path_B = os.path.join(PROGETTO_DIR, "verify_B.wav")
            wavfile.write(path_A, fs, rec_A)
            if rec_B is not None:
                wavfile.write(path_B, fs, rec_B)
            else:
                path_B = path_A

            with open(path_A, 'rb') as f:
                audio_bytes_A = f.read()

            votes = []
            votes_lock = threading.Lock()
            first_found_event = threading.Event()

            def on_vote(title, artist, source):
                with votes_lock:
                    votes.append({'title': title, 'artist': artist, 'source': source})
                    current_votes = list(votes)
                print(f"   🗳️ Verifica voto [{source}]: {title} by {artist}  ({len(current_votes)}/3)")
                if len(current_votes) >= 2:
                    matches = sum(1 for v in current_votes if titles_match(v['title'], title))
                    if matches >= 2:
                        first_found_event.set()

            def try_shazam_A():
                try:
                    async def _run():
                        return await asyncio.wait_for(Shazam().recognize(path_A), timeout=5.0)
                    out = asyncio.run(_run())
                    track = (out or {}).get('track', {})
                    if track and track.get('title'):
                        on_vote(track['title'], track.get('subtitle', ''), 'Shazam-A')
                        return
                    print("[Verifica Shazam-A] Nessun risultato")
                except Exception as e:
                    print(f"[Verifica Shazam-A] Errore: {e}")

            def try_shazam_B():
                try:
                    async def _run():
                        return await asyncio.wait_for(Shazam().recognize(path_B), timeout=5.0)
                    out = asyncio.run(_run())
                    track = (out or {}).get('track', {})
                    if track and track.get('title'):
                        on_vote(track['title'], track.get('subtitle', ''), 'Shazam-B')
                        return
                    print("[Verifica Shazam-B] Nessun risultato")
                except Exception as e:
                    print(f"[Verifica Shazam-B] Errore: {e}")

            def try_acrcloud():
                try:
                    res = recognize_with_acrcloud(audio_bytes_A, fs)
                    if res:
                        on_vote(res['title'], res['artist'], 'ACRCloud')
                        return
                    print("[Verifica ACRCloud] Nessun risultato")
                except Exception as e:
                    print(f"[Verifica ACRCloud] Errore: {e}")

            t1 = threading.Thread(target=try_shazam_A, daemon=True, name="V-Shazam-A")
            t2 = threading.Thread(target=try_shazam_B, daemon=True, name="V-Shazam-B")
            t3 = threading.Thread(target=try_acrcloud,  daemon=True, name="V-ACR")
            t1.start(); t2.start(); t3.start()

            majority_reached = first_found_event.wait(timeout=4.0)

            if not majority_reached:
                with votes_lock:
                    current_votes = list(votes)
                if current_votes:
                    majority_reached = True
                else:
                    print("⚠️ Verifica: nessun riconoscimento — riprendo sync attuale")
                    def _ui_resume(dt):
                        if self.sync_enabled:
                            self.root_ui.ids.sync_toggle_btn.text = "🔄 SYNC: ON"
                            self.root_ui.ids.sync_toggle_btn.background_color = [0, 0.7, 0.3, 1]
                            self.set_status("⚠️ Brano non identificato — sync attivo")
                        else:
                            self.root_ui.ids.sync_toggle_btn.text = "⏸️ SYNC: OFF"
                            self.root_ui.ids.sync_toggle_btn.background_color = [0.5, 0.5, 0.5, 1]
                            self.set_status("⚠️ Brano non identificato — sync disattivato")
                    Clock.schedule_once(_ui_resume, 0)
                    return

            with votes_lock:
                current_votes = list(votes)

            title_counts = {}
            for v in current_votes:
                matched = False
                for key in title_counts:
                    if titles_match(key, v['title']):
                        title_counts[key]['count'] += 1
                        matched = True
                        break
                if not matched:
                    title_counts[v['title']] = {'count': 1, 'artist': v['artist']}

            best_title  = max(title_counts, key=lambda k: title_counts[k]['count'])
            best_artist = title_counts[best_title]['artist']
            print(f"🔍 Verifica risultato: {best_title} by {best_artist}")

            same = fuzz.token_sort_ratio(
                normalize_title(best_title),
                normalize_title(self.current_song_title)
            ) >= 70

            if same:
                print(f"✅ Stessa canzone: {best_title} ≈ {self.current_song_title}")
                self.anchor_song_time    = None
                self.anchor_real_time    = None
                self.sync_perfect_streak = 0
                self.sync_verify_mode    = False
                self.remix_miss_streak   = 0
                self.max_song_time_reached = 0.0
                self.sync_history        = []
                self._last_sync_snapshot = 0
                def _ui_same(dt):
                    if self.sync_enabled:
                        self.root_ui.ids.sync_toggle_btn.text = "🔄 SYNC: ON"
                        self.root_ui.ids.sync_toggle_btn.background_color = [0, 0.7, 0.3, 1]
                        self.set_status("🎵 Stessa canzone — sync attivo")
                    else:
                        self.root_ui.ids.sync_toggle_btn.text = "⏸️ SYNC: OFF"
                        self.root_ui.ids.sync_toggle_btn.background_color = [0.5, 0.5, 0.5, 1]
                        self.set_status("🎵 Stessa canzone — riproduzione libera")
                Clock.schedule_once(_ui_same, 0)
                self.update_sync_ui("Stessa canzone ✅", [0, 1, 0, 1])
            else:
                print(f"🔄 Canzone diversa: {best_title} ≠ {self.current_song_title}")
                self.update_sync_ui("Nuova canzone... 🎵", [1, 0.5, 0, 1])

                def try_lrclib_verify(title, artist):
                    queries_tried = set()
                    best_fallback = {'item': None, 'score': -1e9}
                    def _search(q):
                        q = q.strip()
                        if not q or q in queries_tried:
                            return None
                        queries_tried.add(q)
                        try:
                            best, score, meta = self._search_lrclib_best(q, title, artist)
                            if best:
                                print(f"[lrclib verify] best q='{q}' score={score:.1f} lines={meta['lines']} dur={meta['duration']:.1f}s words={meta['words']}")
                                if score > best_fallback['score']:
                                    best_fallback['item'] = best
                                    best_fallback['score'] = score
                                if score >= LRCLIB_GOOD_SCORE:
                                    return best
                        except Exception as e:
                            print(f"[Verifica lrclib] Errore per '{q}': {e}")
                        return None

                    result = _search(f"{title} {artist}")
                    if not result:
                        result = _search(title)
                    if not result:
                        core = re.sub(r'\s*[\(\[].*?[\)\]]', '', title).strip()
                        if core and core != title:
                            result = _search(core)
                            if not result:
                                result = _search(f"{core} {artist}")
                    if not result and artist:
                        for part in artist.replace(',', ' ').replace('&', ' ').split():
                            if len(part) >= 2:
                                result = _search(f"{title} {part}")
                                if result:
                                    break
                    return result or best_fallback['item']

                lrc_result = try_lrclib_verify(best_title, best_artist)

                if lrc_result:
                    print(f"✅ [Verifica] Testo trovato per: {best_title}")
                    def auto_load_new(dt, r=lrc_result, _title=best_title, _artist=best_artist):
                        self.lyrics_data = []
                        self.is_playing  = False
                        Clock.unschedule(self.update_loop)
                        self.current_song_title  = _title
                        self.current_song_artist = _artist
                        self.update_track_ui(_title, _artist)
                        self._needs_song_verification = False
                        self.current_neon = random.choice(list(self.neon_colors.values()))
                        self._apply_random_font()
                        self._update_glow_color()
                        self.parse_lrc(r['syncedLyrics'])
                        self.consecutive_misses  = 0
                        self.remix_miss_streak   = 0
                        self.sync_confidence     = 0.0
                        self.sync_perfect_streak = 0
                        self.sync_verify_mode    = False
                        self.anchor_song_time    = None
                        self.anchor_real_time    = None
                        self.max_song_time_reached = 0.0
                        self.sync_history        = []
                        self._last_sync_snapshot = 0
                        self.sync_enabled = True
                        self.root_ui.ids.sync_toggle_btn.text = "🔄 SYNC: ON"
                        self.root_ui.ids.sync_toggle_btn.background_color = [0, 0.7, 0.3, 1]
                        self.start_hybrid_engine()
                        self.root_ui.ids.results_list.clear_widgets()
                        self.set_status(f"🎵 Traccia Attiva: {_title} — {_artist}")
                    Clock.schedule_once(auto_load_new, 0)
                else:
                    print(f"⚠️ [Verifica] Nessun testo per: {best_title} — reset")
                    self.remix_miss_streak     = 0
                    self.consecutive_misses    = 0
                    self.sync_confidence       = 0.0
                    self.anchor_song_time      = None
                    self.anchor_real_time      = None
                    self.max_song_time_reached = 0.0
                    self.sync_history          = []
                    self.sync_perfect_streak   = 0
                    self.sync_verify_mode      = False
                    self.sync_enabled          = False
                    self.current_song_title    = ""
                    self.current_song_artist   = ""
                    self.update_track_ui("", "")
                    def _reset_ui(dt):
                        self.lyrics_data = []
                        self.is_playing  = False
                        Clock.unschedule(self.update_loop)
                        self.root_ui.ids.lyric_curr.text = (
                            "[color=FFA500]🎵 Nuova canzone — cerco il brano...[/color]"
                        )
                        self.root_ui.ids.lyric_prev.text = ""
                        self.root_ui.ids.lyric_next.text = ""
                        self.root_ui.ids.sync_toggle_btn.text = "⏸️ SYNC: OFF"
                        self.root_ui.ids.sync_toggle_btn.background_color = [0.5, 0.5, 0.5, 1]
                    Clock.schedule_once(_reset_ui, 0)

        except Exception as e:
            print(f"[Verifica] Errore: {e}")

    def master_omni_loop(self):
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="SyncWorker")
        pending = []
        last_snap = 0
        snap_count = 0

        while True:
            omni = self.omni_mode
            sync = self.sync_enabled
            has_lyrics = bool(self.lyrics_data)
            playing = self.is_playing

            # --- Idle: nothing active ---
            if not omni and not sync:
                self._stop_continuous_recorder()
                time.sleep(0.5)
                continue

            if not omni and sync and not has_lyrics:
                self._stop_continuous_recorder()
                time.sleep(0.5)
                continue

            # --- Song recognition / verification (uses sd.rec, needs recorder off) ---
            # Also recover from stale states: lyrics loaded but playback not running.
            if omni and (self._needs_song_verification or not has_lyrics or (has_lyrics and not playing)):
                self._stop_continuous_recorder()
                if self._recognition_commit_pending:
                    time.sleep(0.05)
                    continue
                if self.is_ai_processing or self.sync_lock:
                    time.sleep(0.1)
                    continue
                self.is_ai_processing = True
                try:
                    if self._needs_song_verification and has_lyrics:
                        self.update_sync_ui("Verifico brano... 🔄", [1, 0.8, 0, 1])
                        self._verify_or_change_song()
                    else:
                        self.update_sync_ui("Cerco Brano... 🎵", [0, 0.8, 1, 1])
                        self.perform_parallel_recognition()
                finally:
                    self.is_ai_processing = False
                continue

            # --- Playback with sync off: no sync processing, optional periodic song-change check ---
            if has_lyrics and playing and not sync:
                self._stop_continuous_recorder()
                if omni and not self._needs_song_verification:
                    now_check = time.time()
                    if (now_check - self._last_forced_song_verify_time) > SONG_CHANGE_FORCE_VERIFY_INTERVAL:
                        if self._request_song_verification("monitoraggio cambio brano (sync off)"):
                            self._last_forced_song_verify_time = now_check
                time.sleep(0.2)
                continue

            # --- Active sync: overlapping snapshots while sync is ON ---
            if has_lyrics and playing and sync:
                if self._continuous_recorder is None:
                    self._continuous_recorder = ContinuousRecorder(fs=16000, buffer_seconds=7)
                    self._continuous_recorder.start()
                    # Force first sync snapshot immediately after recorder starts.
                    last_snap = 0
                    snap_count = 0
                    print("🎙️ Registrazione continua avviata (ring buffer 7s @ 16kHz)")
                    time.sleep(0.2)
                    continue

                now = time.time()
                if now < self._sync_fast_until:
                    snap_interval = SYNC_BOOTSTRAP_INTERVAL
                    snap_duration = SYNC_BOOTSTRAP_DURATION
                else:
                    snap_interval = SYNC_STEADY_INTERVAL
                    snap_duration = SYNC_STEADY_DURATION

                if now - last_snap >= snap_interval:
                    last_snap = now
                    audio_chunk = self._continuous_recorder.get_last_seconds(snap_duration)
                    t_snap = now
                    snap_count += 1

                    # Clean up completed futures
                    pending = [f for f in pending if not f.done()]

                    if len(pending) < SYNC_MAX_PENDING_SNAPSHOTS:
                        if sync:
                            self.update_sync_ui("Ascolto... 🎧", [1, 0.5, 0, 1])
                        elif omni:
                            self.update_sync_ui("Monitoraggio 👁️", [1, 0.5, 0, 0.6])
                        print(f"📡 Sync snapshot #{snap_count} (dur={snap_duration:.1f}s pending={len(pending)})")
                        future = executor.submit(
                            self._process_sync_chunk, audio_chunk, t_snap, snap_duration
                        )
                        pending.append(future)

                time.sleep(0.05)
            else:
                self._stop_continuous_recorder()
                time.sleep(0.2)

    def _stop_continuous_recorder(self):
        if self._continuous_recorder is not None:
            self._continuous_recorder.stop()
            self._continuous_recorder = None

    def perform_parallel_recognition(self):
        try:
            commit_token = time.time_ns()
            self._recognition_commit_token = commit_token
            self._diag_mark('recognition_cycle_start')
            self._diag_event('recognition_cycle_start')
            fs = 44100
            duration_long = 3.0
            overlap = 1.0
            clip_end_time = time.time()

            rec_long = sd.rec(int(duration_long * fs), samplerate=fs, channels=1,
                              dtype='float32', device=AUDIO_INPUT_DEVICE)
            sd.wait()
            clip_end_time = time.time()

            rec_A, peak_A = normalize_audio(rec_long.copy())
            rec_B, peak_B = normalize_audio(rec_long[int(overlap * fs):].copy())

            print(f"   📊 Picco A: {peak_A:.3f}  Picco B: {peak_B:.3f}")

            if rec_A is None:
                print("   ⚠️ Audio troppo basso — microfono non sente nulla")
                self.update_sync_ui("Silenzio ⏳", [0.5, 0.5, 0.5, 1])
                return

            path_A = os.path.join(PROGETTO_DIR, "recog_A.wav")
            path_B = os.path.join(PROGETTO_DIR, "recog_B.wav")
            wavfile.write(path_A, fs, rec_A)
            if rec_B is not None:
                wavfile.write(path_B, fs, rec_B)
            else:
                path_B = path_A

            with open(path_A, 'rb') as f:
                audio_bytes_A = f.read()

            votes = []
            votes_lock = threading.Lock()
            first_found_event = threading.Event()
            lrclib_result  = {'synced': None, 'title': '', 'artist': ''}
            lrclib_done    = threading.Event()
            lrclib_started = threading.Event()

            def try_lrclib(title, artist):
                queries_tried = set()
                best_fallback = {'item': None, 'score': -1e9}
                def _search_lrclib(q):
                    q = q.strip()
                    if not q or q in queries_tried:
                        return None
                    queries_tried.add(q)
                    print(f"[lrclib] Ricerca: '{q}'")
                    try:
                        best, score, meta = self._search_lrclib_best(q, title, artist)
                        if best:
                            print(f"[lrclib] best q='{q}' score={score:.1f} lines={meta['lines']} dur={meta['duration']:.1f}s words={meta['words']}")
                            if score > best_fallback['score']:
                                best_fallback['item'] = best
                                best_fallback['score'] = score
                            if score >= LRCLIB_GOOD_SCORE:
                                return best
                    except Exception as e:
                        print(f"[lrclib] Errore per '{q}': {e}")
                    return None

                # 1) title + artist
                result = _search_lrclib(f"{title} {artist}")
                # 2) title only
                if not result:
                    result = _search_lrclib(title)
                # 3) core title (strip parenthesized parts like "(Remix)", "(feat. X)")
                if not result:
                    core = re.sub(r'\s*[\(\[].*?[\)\]]', '', title).strip()
                    if core and core != title:
                        result = _search_lrclib(core)
                        if not result:
                            result = _search_lrclib(f"{core} {artist}")
                # 4) try each artist word with title (catches "RVFV" etc)
                if not result and artist:
                    for part in artist.replace(',', ' ').replace('&', ' ').split():
                        if len(part) >= 2:
                            result = _search_lrclib(f"{title} {part}")
                            if result:
                                break

                if not result:
                    result = best_fallback['item']

                if result:
                    lrclib_result['synced']  = result
                    lrclib_result['title']   = title
                    lrclib_result['artist']  = artist
                    print(f"✅ [lrclib] Testo trovato: {result.get('trackName','?')}")
                else:
                    print(f"⚠️ [lrclib] Nessun testo per: {title} {artist}")
                lrclib_done.set()

            def on_vote(title, artist, source):
                with votes_lock:
                    votes.append({'title': title, 'artist': artist, 'source': source})
                    current_votes = list(votes)
                print(f"   🗳️ Voto [{source}]: {title} by {artist}  ({len(current_votes)}/3)")

                if len(current_votes) == 1:
                    elapsed_first_vote = self._diag_elapsed('recognition_cycle_start')
                    self._diag_event(
                        'song_recognized_first_vote',
                        source=source,
                        title=title,
                        artist=artist,
                        elapsed_ms=int(elapsed_first_vote * 1000) if elapsed_first_vote is not None else -1,
                    )

                if not lrclib_started.is_set():
                    lrclib_started.set()
                    print(f"   ⚡ lrclib avviato subito su primo voto [{source}]")
                    threading.Thread(
                        target=try_lrclib, args=(title, artist),
                        daemon=True, name="lrclib"
                    ).start()

                if len(current_votes) >= 2:
                    matches = sum(
                        1 for v in current_votes
                        if titles_match(v['title'], title)
                    )
                    if matches >= 2:
                        print(f"   ✅ MAGGIORANZA ({matches}/3) confermata: {title}")
                        first_found_event.set()

            def try_shazam_A():
                try:
                    print("[Shazam-A] Avvio...")
                    async def _run():
                        return await asyncio.wait_for(Shazam().recognize(path_A), timeout=5.0)
                    out = asyncio.run(_run())
                    track = (out or {}).get('track', {})
                    if track:
                        t = track.get('title', '')
                        a = track.get('subtitle', '')
                        if t:
                            print(f"✅ [Shazam-A] → {t} by {a}")
                            on_vote(t, a, 'Shazam-A')
                            return
                    print("[Shazam-A] Nessun risultato")
                except Exception as e:
                    print(f"[Shazam-A] Errore: {type(e).__name__}: {e}")

            def try_shazam_B():
                try:
                    print("[Shazam-B] Avvio...")
                    async def _run():
                        return await asyncio.wait_for(Shazam().recognize(path_B), timeout=5.0)
                    out = asyncio.run(_run())
                    track = (out or {}).get('track', {})
                    if track:
                        t = track.get('title', '')
                        a = track.get('subtitle', '')
                        if t:
                            print(f"✅ [Shazam-B] → {t} by {a}")
                            on_vote(t, a, 'Shazam-B')
                            return
                    print("[Shazam-B] Nessun risultato")
                except Exception as e:
                    print(f"[Shazam-B] Errore: {type(e).__name__}: {e}")

            def try_acrcloud_main():
                try:
                    print("[ACRCloud] Avvio...")
                    res = recognize_with_acrcloud(audio_bytes_A, fs)
                    if res:
                        print(f"✅ [ACRCloud] → {res['title']} by {res['artist']}")
                        on_vote(res['title'], res['artist'], 'ACRCloud')
                        return
                    print("[ACRCloud] Nessun risultato")
                except Exception as e:
                    print(f"[ACRCloud] Errore: {type(e).__name__}: {e}")

            t1 = threading.Thread(target=try_shazam_A,      daemon=True, name="Shazam-A")
            t2 = threading.Thread(target=try_shazam_B,      daemon=True, name="Shazam-B")
            t3 = threading.Thread(target=try_acrcloud_main, daemon=True, name="ACRCloud")
            t1.start()
            t2.start()
            t3.start()

            majority_reached = first_found_event.wait(timeout=4.0)

            if not majority_reached:
                with votes_lock:
                    current_votes = list(votes)
                if current_votes:
                    print(f"⚠️ Nessuna maggioranza in 4s — uso primo voto disponibile")
                    majority_reached = True
                else:
                    print("❌ Nessun riconoscimento rapido — provo fallback lungo ACRCloud")

                    # Fallback robusto: clip piu lunga per aumentare chance sul primo aggancio.
                    duration_fallback = 6.0
                    rec_fb = sd.rec(int(duration_fallback * fs), samplerate=fs, channels=1,
                                    dtype='float32', device=AUDIO_INPUT_DEVICE)
                    sd.wait()
                    rec_fb_norm, peak_fb = normalize_audio(rec_fb)
                    if rec_fb_norm is None:
                        print("⚠️ Fallback: audio troppo basso")
                        self.update_sync_ui("Silenzio ⏳", [0.5, 0.5, 0.5, 1])
                        return

                    wav_buf = io.BytesIO()
                    wavfile.write(wav_buf, fs, rec_fb_norm)
                    wav_buf.seek(0)
                    fb_res = recognize_with_acrcloud(wav_buf.read(), fs)
                    if not fb_res:
                        print("❌ Fallback ACRCloud fallito")
                        self.update_sync_ui("Nessun match 🎵", [1, 0.3, 0.3, 1])
                        return

                    best_title = fb_res.get('title', '').strip()
                    best_artist = fb_res.get('artist', '').strip()
                    if not best_title:
                        self.update_sync_ui("Nessun match 🎵", [1, 0.3, 0.3, 1])
                        return
                    print(f"✅ Fallback ACRCloud: {best_title} by {best_artist}")

                    # Reuse lrclib search strategy with fallback title/artist.
                    queries_tried = set()
                    def _search_fb(q):
                        q = q.strip()
                        if not q or q in queries_tried:
                            return None
                        queries_tried.add(q)
                        try:
                            best_item, _, _ = self._search_lrclib_best(q, best_title, best_artist)
                            if best_item:
                                return best_item
                        except Exception as e:
                            print(f"[lrclib fallback] Errore per '{q}': {e}")
                        return None

                    best = _search_fb(f"{best_title} {best_artist}") or _search_fb(best_title)
                    if not best:
                        core = re.sub(r'\s*[\(\[].*?[\)\]]', '', best_title).strip()
                        if core and core != best_title:
                            best = _search_fb(core) or _search_fb(f"{core} {best_artist}")
                    if not best and best_artist:
                        for part in best_artist.replace(',', ' ').replace('&', ' ').split():
                            if len(part) >= 2:
                                best = _search_fb(f"{best_title} {part}")
                                if best:
                                    break

                    if not best:
                        print(f"⚠️ Fallback: brano trovato ma senza testo sync ({best_title})")
                        self.update_sync_ui("Brano trovato, no lyrics ⚠️", [1, 0.5, 0, 1])
                        return

                    def auto_load_fb(dt, r=best, _title=best_title, _artist=best_artist):
                        self._recognition_commit_pending = False
                        if self._recognition_commit_token != commit_token:
                            self._diag_event('recognition_commit_skipped', reason='stale_fallback_commit')
                            return
                        self._recognition_commit_token = None
                        self.current_song_title = _title
                        self.current_song_artist = _artist
                        self.update_track_ui(_title, _artist)
                        self._needs_song_verification = False
                        self.current_neon = random.choice(list(self.neon_colors.values()))
                        self._apply_random_font()
                        self._update_glow_color()
                        self.parse_lrc(r['syncedLyrics'])
                        self.consecutive_misses = 0
                        self.remix_miss_streak = 0
                        self.sync_confidence = 0.0
                        self.sync_perfect_streak = 0
                        self.sync_verify_mode = False
                        self.anchor_song_time = None
                        self.anchor_real_time = None
                        self.max_song_time_reached = 0.0
                        self.sync_history = []
                        self._last_sync_snapshot = 0
                        self.sync_enabled = True
                        self.root_ui.ids.sync_toggle_btn.text = "🔄 SYNC: ON"
                        self.root_ui.ids.sync_toggle_btn.background_color = [0, 0.7, 0.3, 1]
                        hint_t = self._estimate_presync_hint_from_audio(rec_A, fs, clip_end_time)
                        self.start_hybrid_engine(hint_t)
                        elapsed_fb_sync_start = self._diag_elapsed('recognition_cycle_start')
                        self._diag_event(
                            'recognition_sync_started_fallback',
                            title=_title,
                            artist=_artist,
                            elapsed_ms=int(elapsed_fb_sync_start * 1000) if elapsed_fb_sync_start is not None else -1,
                        )
                        self.root_ui.ids.results_list.clear_widgets()
                        self.set_status(f"🎵 Traccia Attiva: {_title} — {_artist}")
                    Clock.schedule_once(auto_load_fb, 0)
                    self._recognition_commit_pending = True
                    return

            with votes_lock:
                current_votes = list(votes)

            title_counts = {}
            for v in current_votes:
                matched = False
                for key in title_counts:
                    if titles_match(key, v['title']):
                        title_counts[key]['count'] += 1
                        matched = True
                        break
                if not matched:
                    title_counts[v['title']] = {'count': 1, 'artist': v['artist']}

            best_title  = max(title_counts, key=lambda k: title_counts[k]['count'])
            best_artist = title_counts[best_title]['artist']
            best_count  = title_counts[best_title]['count']
            print(f"\n🏆 Canzone vincente ({best_count}/3 voti): {best_title} by {best_artist}")

            lrclib_done.wait(timeout=4)

            # If lrclib failed with first vote's title, retry with all unique vote titles
            if not lrclib_result['synced']:
                with votes_lock:
                    all_votes = list(votes)
                tried_titles = set()
                for v in all_votes:
                    vt = normalize_title(v['title'])
                    if vt not in tried_titles:
                        tried_titles.add(vt)
                        print(f"🔄 [lrclib] Retry con voto: {v['title']} — {v['artist']}")
                        lrclib_done.clear()
                        try_lrclib(v['title'], v['artist'])
                        if lrclib_result['synced']:
                            break

            if not lrclib_result['synced']:
                print(f"⚠️ [lrclib] Nessun testo per: {best_title}")
                self._recognition_commit_pending = False
                elapsed_no_lyrics = self._diag_elapsed('recognition_cycle_start')
                self._diag_event(
                    'recognition_no_synced_lyrics',
                    title=best_title,
                    elapsed_ms=int(elapsed_no_lyrics * 1000) if elapsed_no_lyrics is not None else -1,
                )
                Clock.schedule_once(lambda dt: self.set_status(
                    f"🎵 {best_title} — nessun testo sincronizzato"
                ))
                return

            best   = lrclib_result['synced']
            title  = lrclib_result['title']
            artist = lrclib_result['artist']

            def auto_load(dt, r=best, t=f"{title} — {artist}", _title=title, _artist=artist):
                self._recognition_commit_pending = False
                if self._recognition_commit_token != commit_token:
                    self._diag_event('recognition_commit_skipped', reason='stale_main_commit')
                    return
                self._recognition_commit_token = None
                self.current_song_title  = _title
                self.current_song_artist = _artist
                self.update_track_ui(_title, _artist)
                self._needs_song_verification = False
                self.current_neon = random.choice(list(self.neon_colors.values()))
                self._apply_random_font()
                self._update_glow_color()
                self.parse_lrc(r['syncedLyrics'])
                self.consecutive_misses  = 0
                self.remix_miss_streak   = 0
                self.sync_confidence     = 0.0
                self.sync_perfect_streak = 0
                self.sync_verify_mode    = False
                self.anchor_song_time    = None
                self.anchor_real_time    = None
                self.max_song_time_reached = 0.0
                self.sync_history        = []
                self._last_sync_snapshot = 0
                self.sync_enabled = True
                self.root_ui.ids.sync_toggle_btn.text = "🔄 SYNC: ON"
                self.root_ui.ids.sync_toggle_btn.background_color = [0, 0.7, 0.3, 1]
                hint_t = self._estimate_presync_hint_from_audio(rec_A, fs, clip_end_time)
                self.start_hybrid_engine(hint_t)
                elapsed_sync_start = self._diag_elapsed('recognition_cycle_start')
                self._diag_event(
                    'recognition_sync_started',
                    title=_title,
                    artist=_artist,
                    elapsed_ms=int(elapsed_sync_start * 1000) if elapsed_sync_start is not None else -1,
                )
                self.root_ui.ids.results_list.clear_widgets()
                self.set_status(f"🎵 Traccia Attiva: {t}")
            Clock.schedule_once(auto_load, 0)
            self._recognition_commit_pending = True
            print(f"✅ [TESTO] Inizio Sincronizzazione...")

        except Exception as e:
            self._recognition_commit_pending = False
            print(f"[Riconoscimento] Errore: {e}")

    def _process_sync_chunk(self, audio_float32, t_snapshot, chunk_duration):
        """Process a 5s audio chunk from the ring buffer: normalize, Whisper, adjust sync."""
        try:
            if not self.lyrics_data or not self.is_playing:
                return

            snapshot_age = max(0.0, time.time() - t_snapshot)
            phase_state = "BOOTSTRAP" if time.time() < self._sync_fast_until else "STEADY"
            self._diag_set(snapshot_age_s=snapshot_age, state=phase_state)

            # Drop stale snapshots when network/API latency is too high to avoid late jumps.
            if snapshot_age > SYNC_STALE_SNAPSHOT_MAX_AGE:
                self._diag_set(state="STALE_DROP")
                self._diag_event("stale_snapshot_drop", snapshot_age_s=round(snapshot_age, 3))
                return

            if not GROQ_API_KEY:
                print("[Whisper] GROQ_API_KEY mancante")
                self._diag_set(state="MISSING_GROQ_KEY")
                return

            if time.time() < self._whisper_backoff_until:
                return

            fs = 16000
            peak_f = float(np.max(np.abs(audio_float32)))
            if peak_f < 0.015:
                return

            if peak_f >= 0.99:
                audio_float32 = audio_float32 * 0.3
                peak_f = float(np.max(np.abs(audio_float32)))
            if peak_f > 0.01:
                audio_float32 = audio_float32 * (0.8 / peak_f)
            rec = (audio_float32 * 32767).clip(-32768, 32767).astype(np.int16)

            wav_buf = io.BytesIO()
            wavfile.write(wav_buf, fs, rec)
            wav_buf.seek(0)

            headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
            data = {
                "model": "whisper-large-v3-turbo",
                "language": TARGET_LANGUAGE,
                "temperature": "0.0",
                "response_format": "verbose_json",
            }

            t_send = time.time()
            resp = http_post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                files={"file": ("sync.wav", wav_buf, "audio/wav")},
                data=data,
                timeout=20,
            )
            t_whisper_end = time.time()
            whisper_latency = t_whisper_end - t_send
            self._diag_set(latency_ms=int(whisper_latency * 1000), state="TRANSCRIBE")
            self._diag_event("whisper_result", latency_ms=int(whisper_latency * 1000))

            if resp.status_code != 200:
                print(f"[Whisper] HTTP {resp.status_code}")
                self._diag_set(state="WHISPER_HTTP_ERROR")
                self._diag_event("whisper_http_error", status=resp.status_code)
                if resp.status_code == 429:
                    self._whisper_backoff_until = time.time() + WHISPER_429_BACKOFF_SEC
                return

            result = resp.json()
            text = result.get('text', "").strip()
            sync_text = text

            # Use segment timestamps from verbose_json for precise timing
            segments = result.get('segments', [])
            if segments:
                seg_start, seg_text = self._select_sync_segment(segments)
                if seg_text:
                    sync_text = seg_text
                t_phrase_start = (t_snapshot - chunk_duration) + seg_start
            else:
                phrase_offset = estimate_phrase_start_in_buffer(text, chunk_duration, whisper_latency)
                t_phrase_start = (t_snapshot - chunk_duration) + phrase_offset

            print(f"🎙️ Whisper: '{text}' | sync:'{sync_text}' (latency={whisper_latency:.2f}s chunk={chunk_duration:.1f}s)")

            lower_text = clean_text(sync_text)
            if not any(c.isalpha() for c in lower_text):
                return

            lower_text_full = sync_text.lower()
            is_hallucination = False
            if any(f in lower_text_full for f in HALL_FRASES):
                is_hallucination = True
            elif any(h in lower_text for h in HALL_PAROLE) and len(lower_text.split()) < 3:
                is_hallucination = True
            elif len(sync_text) < 5 or len(lower_text.split()) < 2:
                is_hallucination = True

            with self._sync_processing_lock:
                # Skip if a newer snapshot was already processed
                if t_snapshot < self._last_sync_snapshot:
                    return

                if is_hallucination:
                    self._diag_set(state="HALLUCINATION")
                    if self.omni_mode and self.lyrics_data:
                        verify_miss_limit = SONG_CHANGE_VERIFY_MISS_SYNC if self.sync_enabled else SONG_CHANGE_VERIFY_MISS_IDLE
                        self.remix_miss_streak += 1
                        trigger_verify, window_count = self._register_verify_miss('hall', verify_miss_limit)
                        self._diag_event(
                            "hallucination_miss",
                            miss_streak=self.remix_miss_streak,
                            window_count=window_count,
                            limit=verify_miss_limit,
                        )
                        print(f"   🔍 Hallucination miss: {self.remix_miss_streak}/{verify_miss_limit} | window={window_count}")
                        if trigger_verify:
                            self._request_song_verification("troppi chunk rumorosi/allucinazioni")
                            self.remix_miss_streak = 0
                            self._reset_verify_miss_windows()
                    return

                if self.omni_mode:
                    text_matches_song, score_full, score_local, strong_mismatch = self._quick_text_match(sync_text)
                    self._diag_event(
                        "song_match_check",
                        full=score_full,
                        local=score_local,
                        strong=strong_mismatch,
                    )
                    soglia_cambio = SONG_CHANGE_VERIFY_MISS_SYNC if self.sync_enabled else SONG_CHANGE_VERIFY_MISS_IDLE

                    now_song = time.time()
                    if (self.sync_enabled and self.is_playing and self.sync_confidence < 0.35 and self.remix_miss_streak >= 2 and
                        (now_song - self._sync_start_time) > SONG_CHANGE_VERIFY_WARMUP_SEC and
                        (now_song - self._last_forced_song_verify_time) > SONG_CHANGE_FORCE_VERIFY_INTERVAL):
                        if self._request_song_verification("controllo periodico: bassa confidenza sync"):
                            self._last_forced_song_verify_time = now_song

                    if text_matches_song:
                        self.remix_miss_streak = 0
                        self._song_mismatch_strong_streak = 0
                        if self.sync_enabled:
                            self.sync_confidence = min(1.0, self.sync_confidence + 0.1)
                    else:
                        self.remix_miss_streak += 1
                        if strong_mismatch:
                            self._song_mismatch_strong_streak += 1
                        else:
                            self._song_mismatch_strong_streak = 0

                        if self._song_mismatch_strong_streak >= SONG_CHANGE_STRONG_MISMATCH_STREAK:
                            if self._request_song_verification("forte mismatch testo (possibile cambio brano)"):
                                self._last_forced_song_verify_time = now_song
                            self.remix_miss_streak = 0
                            self._song_mismatch_strong_streak = 0
                            self._reset_verify_miss_windows()
                            return

                        trigger_verify, window_count = self._register_verify_miss('mismatch', soglia_cambio)
                        print(f"   🔍 Remix check: miss {self.remix_miss_streak}/{soglia_cambio} | window={window_count}")
                        self._diag_event(
                            "remix_miss",
                            miss_streak=self.remix_miss_streak,
                            window_count=window_count,
                            limit=soglia_cambio,
                        )
                        if trigger_verify:
                            if self._request_song_verification("testo non coerente con il brano corrente"):
                                self._last_forced_song_verify_time = now_song
                            self.remix_miss_streak = 0
                            self._song_mismatch_strong_streak = 0
                            self._reset_verify_miss_windows()
                            return

                if not self.sync_enabled:
                    return

                match_found = self.adjust_sync(sync_text, t_phrase_start)

                if match_found:
                    self._last_sync_snapshot = t_snapshot
                    self.consecutive_misses = 0
                    self.sync_confidence = min(1.0, self.sync_confidence + 0.2)
                    self._diag_set(state="LOCKED")
                    if not self._diag_first_sync_locked:
                        self._diag_first_sync_locked = True
                        elapsed_lock = self._diag_elapsed('sync_engine_started')
                        self._diag_event(
                            'first_sync_lock',
                            elapsed_ms=int(elapsed_lock * 1000) if elapsed_lock is not None else -1,
                        )
                        self._first_lock_time = time.time()
                        elapsed_total = self._diag_elapsed('recognition_cycle_start')
                        if elapsed_total is not None:
                            self._diag_event(
                                'total_time_click_to_lock',
                                elapsed_ms=int(elapsed_total * 1000),
                            )
                else:
                    self.consecutive_misses += 1
                    self.sync_confidence = max(0.0, self.sync_confidence - 0.2)
                    self._diag_set(state="SEARCH")
                    self._diag_event("sync_miss", misses=self.consecutive_misses)
                    if self.consecutive_misses >= 5 and self.anchor_song_time is not None:
                        print(f"⚠️ {self.consecutive_misses} miss consecutivi — resetto anchor")
                        self.anchor_song_time = None
                        self.anchor_real_time = None
                        self.sync_perfect_streak = 0
                        self.sync_verify_mode = False

        except Exception as e:
            print(f"[Sync Chunk] Eccezione: {e}")

    def _select_sync_segment(self, segments):
        """Pick the most recent meaningful segment to reduce temporal lag/jitter."""
        chosen_start = 0.0
        chosen_text = ""
        for seg in segments:
            seg_text = (seg.get('text') or "").strip()
            seg_clean = clean_text(seg_text)
            if not seg_clean:
                continue
            words = seg_clean.split()
            if len(words) >= 2:
                chosen_start = float(seg.get('start', 0.0) or 0.0)
                chosen_text = seg_text
        if chosen_text:
            return chosen_start, chosen_text

        # Fallback: use last non-empty segment, else first segment start.
        for seg in reversed(segments):
            seg_text = (seg.get('text') or "").strip()
            if clean_text(seg_text):
                return float(seg.get('start', 0.0) or 0.0), seg_text
        return float(segments[0].get('start', 0.0) or 0.0), ""

    def _quick_text_match(self, text: str):
        if not self.lyrics_data or not text:
            return True, 100, 100, False

        text_clean = clean_text(text)
        if len(text_clean) < 5:
            return True, 100, 100, False

        pool_full = getattr(self, '_lyrics_clean_pool', None)
        if pool_full is None:
            pool_full = [r['clean'] for r in self.lyrics_data if len(r['text']) >= 4]
            self._lyrics_clean_pool = pool_full
        if not pool_full:
            return True, 100, 100, False

        best_full = process.extractOne(text_clean, pool_full, scorer=fuzz.partial_ratio)
        score_full = best_full[1] if best_full else 0

        # Local context around current line catches track changes that still share generic words.
        local_pool = []
        if self.lyrics_data:
            start_idx = max(0, self.current_index - 8)
            end_idx = min(len(self.lyrics_data), self.current_index + 9)
            local_pool = [
                self.lyrics_data[i].get('clean') or clean_text(self.lyrics_data[i].get('text', ''))
                for i in range(start_idx, end_idx)
                if len(self.lyrics_data[i].get('text', '')) >= 4
            ]
        best_local = process.extractOne(text_clean, local_pool, scorer=fuzz.partial_ratio) if local_pool else None
        score_local = best_local[1] if best_local else 0

        # Require stronger agreement with current track to avoid sticking on old song after track change.
        matches = (
            (score_full >= SONG_MATCH_FULL_OK and score_local >= SONG_MATCH_LOCAL_OK) or
            (score_local >= SONG_MATCH_LOCAL_OK + 14)
        )
        strong_mismatch = (score_full <= SONG_MISMATCH_STRONG_FULL_MAX and score_local <= SONG_MISMATCH_STRONG_LOCAL_MAX)

        if matches:
            return True, score_full, score_local, False

        print(f"   🔍 Canzone check: full={score_full}% local={score_local}% → canzone diversa")
        return False, score_full, score_local, strong_mismatch

    def _limit_sync_step(self, target_start: float, now_apply: float, current_start: float = None) -> float:
        """Limit sync correction per update to avoid sudden speed/lag oscillations."""
        if current_start is None:
            current_start = float(self.start_timestamp)
        else:
            current_start = float(current_start)
        dt_apply = now_apply - self._last_sync_apply_time if self._last_sync_apply_time else 1.0
        dt_apply = max(0.12, min(dt_apply, 2.0))

        max_step = SYNC_MAX_STEP_BASE + (dt_apply * SYNC_MAX_STEP_PER_SEC)
        if now_apply < self._sync_fast_until:
            max_step *= 1.5
        max_step = min(SYNC_MAX_STEP_CAP, max_step)

        delta = target_start - current_start
        if abs(delta) <= max_step:
            return target_start
        return current_start + (max_step if delta > 0 else -max_step)

    def _confirm_far_jump(self, candidate_song_time: float) -> bool:
        """Require repeated evidence before accepting very large timeline jumps."""
        if (self._pending_far_jump_time is None or
                abs(candidate_song_time - self._pending_far_jump_time) > 4.0):
            self._pending_far_jump_time = candidate_song_time
            self._pending_far_jump_hits = 1
        else:
            self._pending_far_jump_hits += 1

        print(f"   🛡️ Far-jump guard: {self._pending_far_jump_hits}/{SYNC_TELEPORT_CONFIRMATIONS} "
              f"(target t={candidate_song_time:.1f}s)")
        if self._pending_far_jump_hits >= SYNC_TELEPORT_CONFIRMATIONS:
            self._pending_far_jump_time = None
            self._pending_far_jump_hits = 0
            return True
        self._diag_stats['jump_blocked'] = int(self._diag_stats.get('jump_blocked', 0)) + 1
        self._diag_set(state="JUMP_GUARD")
        self._diag_event("far_jump_blocked", target_song_t=round(candidate_song_time, 3))
        return False

    def adjust_sync(self, sentito: str, t_phrase_start: float) -> bool:
        if not sentito or not self.lyrics_data:
            return False

        print(f"\n{'='*50}")
        print(f"🎙️ AUTO: '{sentito}'")

        sentito_clean = clean_text(sentito)
        extra = 0 if self.sync_confidence > 0.6 else FINESTRA_RICERCA_EXTRA

        RETRO_TOLLERANZA = 3.0
        min_search_time = max(0.0, self.max_song_time_reached - RETRO_TOLLERANZA)

        if self.sync_verify_mode and self.anchor_song_time is not None:
            elapsed  = t_phrase_start - self.anchor_real_time
            expected = self.anchor_song_time + elapsed
            pool_v = [
                {'text': self.lyrics_data[i]['text'],
                 'time': self.lyrics_data[i]['time'],
                 'clean': self.lyrics_data[i].get('clean', ''),
                 'index': i}
                for i in range(len(self.lyrics_data))
                if abs(self.lyrics_data[i]['time'] - expected) <= 6.0
                and len(self.lyrics_data[i]['text']) >= 5
            ]
            if pool_v:
                pool_c = {i: (x['clean'] or clean_text(x['text'])) for i, x in enumerate(pool_v)}
                best_v = process.extractOne(sentito_clean, pool_c, scorer=fuzz.partial_ratio)
                score_v = best_v[1] if best_v else 0
                if score_v >= SOGLIA_AFFINITA_SYNC:
                    idx_v = best_v[2]
                    diff    = abs(self.start_timestamp - (t_phrase_start - pool_v[idx_v]['time']))
                    if diff < SYNC_DEAD_ZONE:
                        self.sync_perfect_streak += 1
                        print(f"✅ VERIFICA OK (score={score_v}%, Δ={diff:.2f}s) streak={self.sync_perfect_streak}")
                        self._update_anchor(pool_v[idx_v]['time'], t_phrase_start)
                        if self._sync_locked:
                            self._sync_locked = False
                            nuovo_start_v = t_phrase_start - pool_v[idx_v]['time']
                            def _unlock_v(dt, ns=nuovo_start_v, idx=pool_v[idx_v]['index']):
                                self.start_timestamp = ns
                                self.current_index = idx
                                self.update_display(idx)
                            Clock.schedule_once(_unlock_v, 0)
                        return True
                    else:
                        print(f"⚠️ VERIFICA: drift rilevato Δ={diff:.2f}s — ricalibro")
                        self.sync_verify_mode    = False
                        self.sync_perfect_streak = 0
                else:
                    print(f"⚠️ VERIFICA: match debole score={score_v}% — ricalibro")
                    self.sync_verify_mode    = False
                    self.sync_perfect_streak = 0

        soglia    = SOGLIA_AFFINITA_SYNC
        no_anchor = self.anchor_song_time is None

        # Estimate expected song time from sync_history even without anchor
        estimated_song_time = None
        if self.sync_history:
            last_st, last_rt = self.sync_history[-1]
            estimated_song_time = last_st + (t_phrase_start - last_rt)
            if estimated_song_time < 0:
                estimated_song_time = None
        expected_song_time_diag = estimated_song_time

        if no_anchor:
            pool = getattr(self, '_lyrics_pool_min5', None)
            if pool is None:
                pool = [
                    {'text': self.lyrics_data[i]['text'],
                     'time': self.lyrics_data[i]['time'],
                     'clean': self.lyrics_data[i].get('clean', ''),
                     'index': i}
                    for i in range(len(self.lyrics_data))
                    if len(self.lyrics_data[i]['text']) >= 5
                ]
                self._lyrics_pool_min5 = pool
            if pool:
                print(f"   🔓 No anchor → ricerca in tutta la canzone: {len(pool)} righe")
        else:
            start_idx = max(0, self.current_index - (FINESTRA_RICERCA_BASE + extra))
            end_idx   = min(len(self.lyrics_data), self.current_index + (FINESTRA_RICERCA_BASE + extra))

            pool = [
                {'text': self.lyrics_data[i]['text'],
                 'time': self.lyrics_data[i]['time'],
                 'clean': self.lyrics_data[i].get('clean', ''),
                 'index': i}
                for i in range(start_idx, end_idx)
                if len(self.lyrics_data[i]['text']) >= 5
                and self.lyrics_data[i]['time'] >= min_search_time
            ]

        if pool:
            print(f"   Ricerca da t≥{min_search_time:.1f}s "
                  f"(max raggiunto: {self.max_song_time_reached:.1f}s) "
                  f"— pool: {len(pool)} righe")
        if not pool:
            return False

        pool_dict = {i: (x.get('clean') or clean_text(x['text'])) for i, x in enumerate(pool)}

        soglia_eff = 75 if no_anchor else soglia
        hits = process.extract(sentito_clean, pool_dict, scorer=fuzz.partial_ratio, limit=10)

        candidati = []
        for testo_c, score_p, idx in hits:
            if score_p < soglia_eff:
                continue
            score_s = fuzz.token_sort_ratio(sentito_clean, testo_c)
            verifica_ok = (score_s >= SOGLIA_DOPPIA_VERIFICA or score_p >= 85) if no_anchor else (score_s >= SOGLIA_DOPPIA_VERIFICA or score_p >= 80)
            if verifica_ok:
                candidati.append({
                    'pool_item': pool[idx],
                    'score_p':   score_p,
                    'score_s':   score_s,
                })

        if not candidati:
            best = process.extractOne(sentito_clean, pool_dict, scorer=fuzz.partial_ratio)
            print(f"❌ SCARTATO (max partial={best[1] if best else 0}%)")
            return False

        print(f"   Candidati trovati: {len(candidati)}")

        if self.anchor_song_time is not None and self.anchor_real_time is not None:
            elapsed_since_anchor = t_phrase_start - self.anchor_real_time
            expected_song_time   = self.anchor_song_time + elapsed_since_anchor
            expected_song_time_diag = expected_song_time

            print(f"   Anchor: song_t={self.anchor_song_time:.1f}s + {elapsed_since_anchor:.1f}s "
                  f"→ expected_song_t={expected_song_time:.1f}s")

            TOLLERANZA_ANCHOR = 12.0
            plausibili = [
                c for c in candidati
                if abs(c['pool_item']['time'] - expected_song_time) <= TOLLERANZA_ANCHOR
            ]

            if plausibili:
                for c in plausibili:
                    time_dist = abs(c['pool_item']['time'] - expected_song_time)
                    c['time_score'] = max(0, 100 - time_dist * 5)
                    # Penalize candidates behind what was already sung
                    if c['pool_item']['time'] < self.max_song_time_reached - 2.0:
                        c['time_score'] -= 40
                riga_vincente_info = max(plausibili,
                    key=lambda c: c['score_p'] + c['score_s'] + c['time_score'])
                print(f"   (Anchor attivo: {len(plausibili)}/{len(candidati)} candidati plausibili)")
            else:
                best_c = max(candidati, key=lambda c: c['score_p'] + c['score_s'])
                if best_c['score_p'] >= 80 and best_c['score_s'] >= 60:
                    far_jump = abs(best_c['pool_item']['time'] - expected_song_time)
                    if far_jump >= SYNC_TELEPORT_GUARD_SEC:
                        if not self._confirm_far_jump(best_c['pool_item']['time']):
                            print(f"⚠️ Far jump bloccato ({far_jump:.1f}s) in attesa conferma")
                            return False
                    print(f"⚠️ Candidati fuori anchor ma match forte "
                          f"(p={best_c['score_p']}% s={best_c['score_s']}%) — resetto anchor")
                    self.anchor_song_time    = None
                    self.anchor_real_time    = None
                    self.sync_perfect_streak = 0
                    self.sync_verify_mode    = False
                    self.max_song_time_reached = 0.0
                    riga_vincente_info = best_c
                else:
                    print(f"⚠️ TUTTI I CANDIDATI FUORI ANCHOR (±{TOLLERANZA_ANCHOR}s) "
                          f"e match debole. Salto.")
                    return False
        else:
            riga_vincente_info = max(candidati, key=lambda c: c['score_p'] + c['score_s'])
            print("   (Nessun anchor: prendo il miglior match assoluto)")

            if estimated_song_time is not None:
                forward_jump = riga_vincente_info['pool_item']['time'] - estimated_song_time
                if forward_jump > SYNC_NO_ANCHOR_MAX_FORWARD_JUMP:
                    if not self._confirm_far_jump(riga_vincente_info['pool_item']['time']):
                        print(f"⚠️ No-anchor jump avanti bloccato ({forward_jump:.1f}s) in attesa conferma")
                        self._diag_event("no_anchor_forward_block", jump_s=round(forward_jump, 3))
                        return False

            # Chorus disambiguation: if multiple candidates score similarly,
            # prefer the one closest to estimated_song_time (forward progression)
            if estimated_song_time is not None and len(candidati) > 1:
                top_score = riga_vincente_info['score_p'] + riga_vincente_info['score_s']
                close_candidates = [
                    c for c in candidati
                    if (c['score_p'] + c['score_s']) >= top_score - 15
                ]
                if len(close_candidates) > 1:
                    # Among similarly-scored candidates, prefer forward from last matched time
                    for c in close_candidates:
                        song_t = c['pool_item']['time']
                        diff_t = song_t - estimated_song_time
                        # Strongly penalize going backwards past already-sung lines
                        if song_t < self.max_song_time_reached - 2.0:
                            c['temporal_dist'] = abs(diff_t) * 3.0
                        elif diff_t >= -3.0:
                            c['temporal_dist'] = abs(diff_t)
                        else:
                            c['temporal_dist'] = abs(diff_t) * 2.0
                    riga_vincente_info = min(close_candidates, key=lambda c: c['temporal_dist'])
                    print(f"   🔄 Chorus disambiguazione: scelto t={riga_vincente_info['pool_item']['time']:.1f}s "
                          f"(atteso ~{estimated_song_time:.1f}s, {len(close_candidates)} candidati simili)")

        riga_vincente = riga_vincente_info['pool_item']
        score_p = riga_vincente_info['score_p']
        score_s = riga_vincente_info['score_s']

        print(f"🎯 Match: '{riga_vincente['text']}' "
              f"(idx={riga_vincente['index']}, t={riga_vincente['time']:.2f}s, "
              f"partial={score_p}%, sort={score_s}%)")

        self._diag_set(
            partial=score_p,
            sort=score_s,
            expected_t=(expected_song_time_diag if expected_song_time_diag is not None else 0.0),
            matched_t=riga_vincente['time'],
        )

        nuovo_start = t_phrase_start - riga_vincente['time']
        base_start = float(self.start_timestamp)
        diff_abs = abs(base_start - nuovo_start)
        now_apply = time.time()

        if diff_abs < 1.2 and (now_apply - self._last_sync_apply_time) < SYNC_APPLY_MIN_INTERVAL:
            print(f"⏳ SYNC debounce: salto micro-correzione Δ={diff_abs:.2f}s")
            self._diag_set(applied_step=0.0, state="DEBOUNCE")
            self._diag_event("sync_debounce", diff_s=round(diff_abs, 3))
            self._update_anchor(riga_vincente['time'], t_phrase_start)
            self.update_sync_ui("Stabile ✅", [0.4, 1, 0.4, 1])
            return True

        if diff_abs < SYNC_DEAD_ZONE:
            self.sync_perfect_streak += 1
            if self.sync_perfect_streak >= 2:
                self.sync_verify_mode = True
                print(f"✅ GIÀ PERFETTO (Δ={diff_abs:.2f}s) streak={self.sync_perfect_streak} → modalità VERIFICA")
            else:
                print(f"✅ GIÀ PERFETTO (Δ={diff_abs:.2f}s < zona morta {SYNC_DEAD_ZONE}s)")
            self._diag_set(applied_step=0.0, state="PERFECT")
            self.update_sync_ui("Sincronizzato ✅", [0, 1, 0, 1])
            self._update_anchor(riga_vincente['time'], t_phrase_start)
            if self._sync_locked:
                self._sync_locked = False
                def _unlock_perfect(dt, ns=nuovo_start, idx=riga_vincente['index']):
                    self.start_timestamp = ns
                    self.current_index = idx
                    self._last_sync_apply_time = time.time()
                    self.update_display(idx)
                Clock.schedule_once(_unlock_perfect, 0)
            return True

        self.sync_perfect_streak = 0
        self.sync_verify_mode    = False

        if diff_abs < SYNC_MIN_DIFF_HARD:
            start_target = (
                base_start * (1.0 - SYNC_SOFT_BLEND) +
                nuovo_start * SYNC_SOFT_BLEND
            )
            start_applicato = self._limit_sync_step(start_target, now_apply, base_start)
            print(f"✅ SYNC SMOOTH: Δ={diff_abs:.2f}s → step={abs(base_start - start_applicato):.2f}s")
        else:
            # Large drift: jump directly to recover lock quickly, but damp in early post-lock phase.
            if self._first_lock_time > 0 and (now_apply - self._first_lock_time) < SYNC_HARD_JUMP_COOLDOWN_SEC:
                raw_delta = nuovo_start - base_start
                capped_delta = max(-SYNC_HARD_JUMP_CAP_EARLY, min(SYNC_HARD_JUMP_CAP_EARLY, raw_delta))
                start_applicato = base_start + capped_delta
                print(f"✅ SYNC HARD DAMPED: Δ={diff_abs:.2f}s → cap={abs(capped_delta):.2f}s")
                self._diag_event("hard_jump_damped", diff_s=round(diff_abs, 3), cap_s=SYNC_HARD_JUMP_CAP_EARLY)
            elif self._first_lock_time <= 0 and (now_apply - self._sync_start_time) < SYNC_HARD_JUMP_STARTUP_WINDOW:
                raw_delta = nuovo_start - base_start
                capped_delta = max(-SYNC_HARD_JUMP_STARTUP_CAP, min(SYNC_HARD_JUMP_STARTUP_CAP, raw_delta))
                start_applicato = base_start + capped_delta
                print(f"✅ SYNC STARTUP DAMPED: Δ={diff_abs:.2f}s → cap={abs(capped_delta):.2f}s")
                self._diag_event("hard_jump_startup_damped", diff_s=round(diff_abs, 3), cap_s=SYNC_HARD_JUMP_STARTUP_CAP)
            else:
                raw_delta = nuovo_start - base_start
                if (now_apply - self._last_hard_jump_time) < SYNC_HARD_JUMP_REAPPLY_GAP:
                    # Prevent back-to-back jumps that cause visible flashing/overshoot.
                    start_applicato = self._limit_sync_step(nuovo_start, now_apply, base_start)
                    print(f"✅ SYNC HARD COOLDOWN: Δ={diff_abs:.2f}s → smooth step")
                    self._diag_event("hard_jump_cooldown", diff_s=round(diff_abs, 3))
                else:
                    capped_delta = max(-SYNC_HARD_JUMP_MAX_STEP, min(SYNC_HARD_JUMP_MAX_STEP, raw_delta))
                    start_applicato = base_start + capped_delta
                    self._last_hard_jump_time = now_apply
                    print(f"✅ SYNC HARD CAPPED: Δ={diff_abs:.2f}s → cap={abs(capped_delta):.2f}s")
                    self._diag_event("hard_jump_capped", diff_s=round(diff_abs, 3), cap_s=SYNC_HARD_JUMP_MAX_STEP)

        applied_step = abs(base_start - start_applicato)
        self._diag_set(applied_step=applied_step, state="APPLY")
        self._diag_event(
            "sync_apply",
            diff_s=round(diff_abs, 3),
            step_s=round(applied_step, 3),
            matched_t=round(riga_vincente['time'], 3),
        )

        self.update_sync_ui("Sincronizzato ✅", [0, 1, 0, 1])
        self._update_anchor(riga_vincente['time'], t_phrase_start)

        if riga_vincente['time'] > self.max_song_time_reached:
            self.max_song_time_reached = riga_vincente['time']

        self._sync_apply_token += 1
        apply_token = self._sync_apply_token

        def applica_ui(dt, ns=start_applicato, idx=riga_vincente['index'], token=apply_token):
            if token != self._sync_apply_token:
                return
            self.start_timestamp = ns
            self.current_index = idx
            self._last_sync_apply_time = time.time()
            if self._sync_locked:
                self._sync_locked = False
            self.update_display(idx)

        Clock.schedule_once(applica_ui, 0)
        return True

    def _update_anchor(self, song_time: float, real_time: float):
        self.anchor_song_time = song_time
        self.anchor_real_time = real_time
        self._pending_far_jump_time = None
        self._pending_far_jump_hits = 0
        self.sync_history.append((song_time, real_time))
        # Keep only last 8 entries
        if len(self.sync_history) > 8:
            self.sync_history = self.sync_history[-8:]
        print(f"   📍 Anchor aggiornato: song={song_time:.1f}s @ real={real_time:.1f}")

    def start_manual_search(self, query):
        self.root_ui.ids.results_list.clear_widgets()
        self.set_status(f"🔍 Ricerca: {query}")
        self._diag_mark('manual_search_click')
        self._diag_event('manual_search_click', query=query.strip())
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        try:
            r = http_get("https://lrclib.net/api/search", params={"q": query}, timeout=10)
            results = r.json()
            elapsed = self._diag_elapsed('manual_search_click')
            self._diag_event(
                'manual_search_results',
                elapsed_ms=int(elapsed * 1000) if elapsed is not None else -1,
                results_count=len(results) if isinstance(results, list) else 0,
            )
            Clock.schedule_once(lambda dt: self._show_results(results))
        except Exception as e:
            print(f"[Ricerca] Errore: {e}")
            elapsed = self._diag_elapsed('manual_search_click')
            self._diag_event(
                'manual_search_error',
                elapsed_ms=int(elapsed * 1000) if elapsed is not None else -1,
                error=str(e),
            )
            Clock.schedule_once(lambda dt: self.set_status(f"❌ Errore di rete nella ricerca"))

    def _show_results(self, results):
        self.root_ui.ids.results_list.clear_widgets()
        if results and isinstance(results, list):
            for res in results[:6]:
                t_name = res.get('trackName') or res.get('title') or "Sconosciuto"
                a_name = res.get('artistName') or res.get('artist') or "Sconosciuto"
                b = Button(
                    text=f"⭐ {t_name} | {a_name}",
                    size_hint_y=None, height=max(40, int(Window.height * 0.076)),
                    font_size=f'{int(Window.height * 0.021)}sp',
                    background_color=[0.15, 0.15, 0.2, 1],
                    shorten=True,
                    shorten_from='right',
                    text_size=(Window.width * 0.9, None)
                )
                def on_click(instance, r=res, _t=t_name, _a=a_name):
                    self.root_ui.ids.results_list.clear_widgets()
                    self._diag_mark('song_select_click')
                    self._diag_mark('recognition_cycle_start')
                    self._diag_event('song_select_click', title=_t, artist=_a)
                    if r.get('syncedLyrics'):
                        self.current_song_title  = _t
                        self.current_song_artist = _a
                        self.update_track_ui(_t, _a)
                        self._needs_song_verification = False
                        self.current_neon = random.choice(list(self.neon_colors.values()))
                        self._apply_random_font()
                        self._update_glow_color()
                        self.parse_lrc(r['syncedLyrics'])
                        self.omni_mode = True
                        self.root_ui.ids.omni_toggle_btn.text = "👁️ OMNI-LISTEN: ON (Auto)"
                        self.root_ui.ids.omni_toggle_btn.background_color = [0, 0.8, 0, 1]
                        self.sync_enabled = True
                        self.root_ui.ids.sync_toggle_btn.text = "🔄 SYNC: ON"
                        self.root_ui.ids.sync_toggle_btn.background_color = [0, 0.7, 0.3, 1]
                        self.consecutive_misses  = 0
                        self.remix_miss_streak   = 0
                        self.sync_confidence     = 0.0
                        self.sync_perfect_streak = 0
                        self.sync_verify_mode    = False
                        self.anchor_song_time    = None
                        self.anchor_real_time    = None
                        self.max_song_time_reached = 0.0
                        self.sync_history        = []
                        self._last_sync_snapshot = 0
                        self.start_hybrid_engine()
                        elapsed_select_to_sync = self._diag_elapsed('song_select_click')
                        self._diag_event(
                            'manual_song_sync_started',
                            title=_t,
                            artist=_a,
                            elapsed_ms=int(elapsed_select_to_sync * 1000) if elapsed_select_to_sync is not None else -1,
                        )
                        self.set_status(f"🎵 Traccia Attiva: {_t} — {_a}")
                    else:
                        self.set_status("⚠️ SENZA TESTO SINCRONIZZATO!")
                        self._diag_event('manual_song_no_synced_lyrics', title=_t, artist=_a)
                b.bind(on_press=on_click)
                self.root_ui.ids.results_list.add_widget(b)
        else:
            self.set_status("❌ Nessun risultato.")

    def _lrc_time_to_sec(self, t_str: str) -> float:
        m, s = t_str.strip().split(':')
        return int(m) * 60 + float(s)

    def parse_lrc(self, lrc_text: str):
        self.lyrics_data = []
        RE_LINE = re.compile(r'^\[(\d+:\d+\.\d+)\](.*)$')
        RE_WORD = re.compile(r'<(\d+:\d+\.\d+)>')

        for line in lrc_text.splitlines():
            line = line.strip()
            lm = RE_LINE.match(line)
            if not lm:
                continue
            try:
                line_sec = self._lrc_time_to_sec(lm.group(1))
                rest = lm.group(2)
                word_tags = RE_WORD.findall(rest)

                if word_tags:
                    parts = RE_WORD.split(rest)
                    seg_texts = [parts[i] for i in range(0, len(parts), 2)]
                    seg_times = [self._lrc_time_to_sec(parts[i]) for i in range(1, len(parts), 2)]

                    words_timed = []
                    for i, (t_start, raw_word) in enumerate(zip(seg_times, seg_texts[1:])):
                        word_clean = sanitize_for_font(raw_word.strip().replace('[', '').replace(']', ''))
                        if not word_clean:
                            continue
                        t_end = seg_times[i + 1] if i + 1 < len(seg_times) else t_start + 5.0
                        words_timed.append({'word': word_clean, 'start': t_start, 'end': t_end})

                    full_text = ' '.join(w['word'] for w in words_timed)
                    if full_text:
                        self.lyrics_data.append({'time': line_sec, 'text': full_text, 'words': words_timed, 'clean': clean_text(full_text)})
                else:
                    text_clean = sanitize_for_font(RE_WORD.sub('', rest).strip())
                    if text_clean:
                        self.lyrics_data.append({'time': line_sec, 'text': text_clean, 'words': [], 'clean': clean_text(text_clean)})
            except Exception:
                continue

        self.lyrics_data.sort(key=lambda x: x['time'])
        self._lyrics_clean_pool = [r['clean'] for r in self.lyrics_data if len(r['text']) >= 4]
        self._lyrics_pool_min5 = [
            {
                'text': r['text'],
                'time': r['time'],
                'clean': r.get('clean', ''),
                'index': i,
            }
            for i, r in enumerate(self.lyrics_data)
            if len(r['text']) >= 5
        ]
        n_word = sum(1 for r in self.lyrics_data if r['words'])
        print(f"📝 LRC: {len(self.lyrics_data)} righe | {n_word} con word-timing nativo | {len(self.lyrics_data)-n_word} fallback sillabico")

    def start_hybrid_engine(self, start_song_time_hint: float | None = None):
        now = time.time()
        self.current_index = 0
        self.start_timestamp = now
        self.is_playing = True
        self._diag_mark('sync_engine_started')
        self._diag_first_sync_locked = False
        self._sync_start_time = now
        self._first_lock_time = 0.0
        self._reset_verify_miss_windows()
        self._song_mismatch_strong_streak = 0
        self._last_forced_song_verify_time = 0.0
        self._diag_event('sync_engine_started')
        self._diag_set(state="BOOTSTRAP", applied_step=0.0)
        self._pending_far_jump_time = None
        self._pending_far_jump_hits = 0
        self._sync_locked = self.sync_enabled
        self._sync_fast_until = time.time() + SYNC_BOOTSTRAP_SECONDS
        Clock.unschedule(self.update_loop)
        Clock.schedule_interval(self.update_loop, 0.016)
        self.root_ui.ids.lyric_prev.text = ""
        self.root_ui.ids.lyric_next.text = ""
        if self.lyrics_data:
            if start_song_time_hint is not None:
                hint = max(0.0, float(start_song_time_hint))
                idx_hint = 0
                while idx_hint < len(self.lyrics_data) - 1 and self.lyrics_data[idx_hint + 1]['time'] <= hint:
                    idx_hint += 1
                self.current_index = idx_hint
                self.start_timestamp = now - hint
                # Prime sync state with hint so first chunks stay near expected timeline.
                self.anchor_song_time = hint
                self.anchor_real_time = now
                self.sync_history = [(hint, now)]
                self.max_song_time_reached = max(self.max_song_time_reached, hint)
                self._diag_event("start_with_presync_hint", hint_t=round(hint, 3), idx=idx_hint)

            self.update_display(self.current_index)
            self.highlight_current_word(max(0.0, time.time() - self.start_timestamp))
        else:
            self.root_ui.ids.lyric_curr.text = ""
            self.root_ui.ids.lyric_curr.opacity = 1

    def on_stop(self):
        if self._diag_log_file is not None:
            try:
                self._diag_log_file.close()
            except Exception:
                pass
            self._diag_log_file = None

    def update_loop(self, dt):
        if not self.is_playing:
            return
        elapsed = time.time() - self.start_timestamp
        elapsed_line = elapsed + LINE_VISUAL_OFFSET
        new_idx = self.current_index
        while new_idx < len(self.lyrics_data) - 1 and elapsed_line >= self.lyrics_data[new_idx + 1]['time']:
            new_idx += 1
        if new_idx != self.current_index:
            self.current_index = new_idx
            self.update_display(self.current_index)
        current_song_time = self.lyrics_data[self.current_index]['time'] if self.lyrics_data else 0
        if current_song_time > self.max_song_time_reached:
            self.max_song_time_reached = current_song_time
        self.highlight_current_word(elapsed)

    def highlight_current_word(self, elapsed):
        if self.current_index >= len(self.lyrics_data):
            return

        elapsed_w = elapsed + WORD_VISUAL_OFFSET

        row = self.lyrics_data[self.current_index]
        words_timed = row.get('words', [])

        if words_timed:
            # Duration-based highlight: keep word active until its end.
            min_vis = 0.18
            active_word_idx = 0
            for i, w in enumerate(words_timed):
                w_start = float(w.get('start', 0.0))
                w_end = float(w.get('end', w_start + 0.25))
                if w_end <= w_start:
                    w_end = w_start + 0.25
                w_end = max(w_end, w_start + min_vis)

                # Avoid hyper-fast jumps when source word timings are too tight.
                if i + 1 < len(words_timed):
                    next_start = float(words_timed[i + 1].get('start', w_end))
                    w_end = max(w_start + min_vis, min(w_end, next_start + 0.03))

                if elapsed_w < w_start:
                    break

                active_word_idx = i
                if elapsed_w < w_end:
                    break
            words = [w['word'] for w in words_timed]

        else:
            c = row['text'].replace('[', '').replace(']', '')
            words = c.split()
            if not words:
                return

            lyric_time = row['time']
            if self.current_index < len(self.lyrics_data) - 1:
                line_duration = self.lyrics_data[self.current_index + 1]['time'] - lyric_time
            else:
                line_duration = 3.0

            syl = [count_syllables(w) for w in words]
            total_syl = sum(syl)
            # Slight reserve to avoid rushing into next line when timings are coarse.
            singing_time = line_duration * 0.98

            word_starts = []
            word_ends = []
            t = 0.0
            for sc in syl:
                dur = singing_time * (sc / total_syl)
                # Minimum duration per word to avoid too-fast flashing on short words.
                dur = max(0.18, dur)
                w_start = lyric_time + t
                w_end = w_start + dur
                word_starts.append(w_start)
                word_ends.append(w_end)
                t += dur

            # If minimum durations expanded total time too much, rescale smoothly.
            final_end = word_ends[-1] if word_ends else lyric_time
            max_end = lyric_time + line_duration * 0.98
            if final_end > max_end and final_end > lyric_time:
                scale = (max_end - lyric_time) / (final_end - lyric_time)
                for i in range(len(word_starts)):
                    word_starts[i] = lyric_time + (word_starts[i] - lyric_time) * scale
                    word_ends[i] = lyric_time + (word_ends[i] - lyric_time) * scale

            # Duration-based highlight for fallback timings.
            active_word_idx = 0
            for i in range(len(words)):
                if elapsed_w < word_starts[i]:
                    break
                active_word_idx = i
                if elapsed_w < word_ends[i]:
                    break

        # Keep highlighted word visible for a minimum time to reduce flicker/speed spikes.
        now = time.time()
        if (active_word_idx != self.last_active_word_idx and
                self.last_lyric_idx == self.current_index and
            (now - self._last_word_switch_time) < 0.16):
            active_word_idx = self.last_active_word_idx

        if self.last_active_word_idx != active_word_idx or self.last_lyric_idx != self.current_index:
            self.last_active_word_idx = active_word_idx
            self.last_lyric_idx = self.current_index
            self._last_word_switch_time = now

            # compute font size once per line (cache to avoid jitter)
            if self.last_lyric_idx != getattr(self, '_cached_line_idx', -1):
                base = self._fit_text_sp(
                    " ".join(words),
                    max_sp=min(LYRIC_FONT_MAX_SP, int(Window.height * 0.062)),
                    min_sp=max(LYRIC_FONT_MIN_SP, int(Window.height * 0.016)),
                    avail_width=Window.width - 44,
                )
                self._cached_line_sp = base
                self._cached_line_idx = self.last_lyric_idx
            sp = self._cached_line_sp
            neon = self.current_neon

            parts = []
            for j, w in enumerate(words):
                if j == active_word_idx:
                    parts.append(f"[b][color=FFFFFF]{w}[/color][/b]")
                else:
                    parts.append(f"[color={neon}]{w}[/color]")
            markup = f"[size={sp}sp]" + " ".join(parts) + "[/size]"
            self.root_ui.ids.lyric_curr.text = markup

    def update_display(self, index):
        for t in self.emoji_timers:
            t.cancel()
        self.emoji_timers = []
        self.root_ui.ids.emoji_layer.clear_widgets()

        p = self.lyrics_data[index - 1]['text'] if index > 0 else ""
        c = self.lyrics_data[index]['text'] if index < len(self.lyrics_data) else ""
        n = self.lyrics_data[index + 1]['text'] if index < len(self.lyrics_data) - 1 else ""

        for lbl_id, txt in [('lyric_prev', p), ('lyric_next', n)]:
            neon = self.current_neon
            clean_txt = txt.replace('[', '').replace(']', '')
            lbl = self.root_ui.ids[lbl_id]
            lbl.text_size = (Window.width - 80, None)
            lbl.font_size = f"{self._fit_text_sp(clean_txt, int(Window.height * 0.033), int(Window.height * 0.018), Window.width - 80)}sp"
            if lbl_id == 'lyric_prev' and clean_txt:
                lbl.text = f"[color={neon}]{clean_txt}[/color]"
            else:
                lbl.text = clean_txt

        self.root_ui.ids.lyric_curr.opacity = 0
        self.root_ui.ids.lyric_prev.opacity = 0
        self.root_ui.ids.lyric_next.opacity = 0
        self.root_ui.ids.lyric_glow.opacity = 0

        anim = Animation(opacity=1, duration=0.15)
        anim.start(self.root_ui.ids.lyric_curr)
        anim.start(self.root_ui.ids.lyric_prev)
        anim.start(self.root_ui.ids.lyric_next)

        glow = self.root_ui.ids.lyric_glow
        glow.text = ""
        glow.opacity = 0

        c_clean = c.replace('[', '').replace(']', '')
        row = self.lyrics_data[index] if index < len(self.lyrics_data) else None
        line_duration = 3.0
        if index < len(self.lyrics_data) - 1:
            line_duration = self.lyrics_data[index + 1]['time'] - self.lyrics_data[index]['time']

        words_raw = []
        word_starts_rel = []
        if row:
            words_timed = row.get('words', [])
            if words_timed:
                words_raw = [w['word'] for w in words_timed]
                base_t = row['time']
                word_starts_rel = [max(0.0, w['start'] - base_t) for w in words_timed]
            else:
                words_raw = c_clean.split()
                if words_raw:
                    syl = [count_syllables(w) for w in words_raw]
                    total_syl = max(1, sum(syl))
                    singing_time = max(0.6, line_duration * 0.96)
                    t_acc = 0.0
                    for sc in syl:
                        word_starts_rel.append(t_acc)
                        t_acc += singing_time * (sc / total_syl)

        line_tokens = clean_text(c_clean).split()

        def process_emojis(dt):
            try:
                emoji_events = extract_emoji_events(c_clean)
                if not emoji_events:
                    return
                slot_duration = min(2.0, max(0.35, line_duration / max(1, len(emoji_events))))
                show_duration = min(1.2, slot_duration * 0.65)

                for i, ev in enumerate(emoji_events):
                    emoji = ev.get('emoji')
                    if not emoji:
                        continue
                    target_word_idx = ev.get('token_index')
                    negated = bool(ev.get('negated', False))

                    if target_word_idx is None:
                        for kw in _EMOJI_TO_KEYWORDS.get(emoji, []):
                            kw_tokens = clean_text(kw).split()
                            idx_kw = find_keyword_token_index(line_tokens, kw_tokens)
                            if idx_kw is not None:
                                target_word_idx = idx_kw
                                break

                    if target_word_idx is not None and word_starts_rel:
                        rel_idx = min(target_word_idx, len(word_starts_rel) - 1)
                        trigger_delay = max(0.0, word_starts_rel[rel_idx] - EMOJI_WORD_OFFSET + (i * 0.03))
                    else:
                        trigger_delay = i * slot_duration

                    def trigger_emoji(dt, e=emoji, sd=show_duration, twi=target_word_idx, neg=negated):
                        is_left = True
                        if twi is not None and words_raw:
                            is_left = twi < (len(words_raw) / 2.0)
                        filename = get_filename_for_emoji(e)
                        img_path = os.path.join(ASSETS_DIR, filename)

                        emoji_sz = int(min(Window.width / 10.7, Window.height / 6))
                        if os.path.exists(img_path):
                            widget = RotatedImage(source=img_path)
                            widget.size_hint = (None, None)
                            widget.size = (emoji_sz, emoji_sz)
                        else:
                            widget = RotatedEmoji()
                            widget.text = e
                            widget.font_size = f'{int(emoji_sz * 0.625)}sp'
                            if platform == 'win':
                                try:
                                    widget.font_name = 'C:/Windows/Fonts/seguiemj.ttf'
                                except Exception:
                                    pass

                        # Keep emojis inside screen and away from central lyric lanes.
                        w = float(Window.width)
                        h = float(Window.height)
                        margin_x = (emoji_sz / (2.0 * w)) + 0.01
                        margin_y = (emoji_sz / (2.0 * h)) + 0.01

                        # Vertical zones outside lyrics: top HUD area and lower footer area.
                        y_ranges = [
                            (max(0.78, margin_y), min(0.90, 1.0 - margin_y)),
                            (max(0.08, margin_y), min(0.18, 1.0 - margin_y)),
                        ]
                        y_min, y_max = random.choice(y_ranges)

                        if is_left:
                            x_min = max(0.03, margin_x)
                            x_max = min(0.16, 1.0 - margin_x)
                        else:
                            x_min = max(0.84, margin_x)
                            x_max = min(0.97, 1.0 - margin_x)

                        if x_max <= x_min:
                            x_min, x_max = margin_x, 1.0 - margin_x
                        if y_max <= y_min:
                            y_min, y_max = margin_y, 1.0 - margin_y

                        pos_x = random.uniform(x_min, x_max)
                        pos_y = random.uniform(y_min, y_max)

                        widget.pos_hint = {'center_x': pos_x, 'center_y': pos_y}
                        widget.angle = random.randint(-25, 25)
                        widget.opacity = 0
                        self.root_ui.ids.emoji_layer.add_widget(widget)

                        neg_widget = None
                        if neg:
                            neg_widget = RotatedEmoji()
                            neg_widget.text = "❌"
                            neg_widget.font_size = f'{int(emoji_sz * 0.44)}sp'
                            neg_widget.angle = 0
                            neg_y = min(0.98 - margin_y, pos_y + ((emoji_sz * 0.34) / max(1.0, h)))
                            neg_widget.pos_hint = {'center_x': pos_x, 'center_y': neg_y}
                            neg_widget.opacity = 0
                            self.root_ui.ids.emoji_layer.add_widget(neg_widget)

                        seq = (Animation(opacity=1, duration=0.3) +
                               Animation(opacity=1, duration=sd) +
                               Animation(opacity=0, duration=0.4))

                        def remove_w(a, w, nw=neg_widget):
                            if w in self.root_ui.ids.emoji_layer.children:
                                self.root_ui.ids.emoji_layer.remove_widget(w)
                            if nw is not None and nw in self.root_ui.ids.emoji_layer.children:
                                self.root_ui.ids.emoji_layer.remove_widget(nw)
                        seq.bind(on_complete=remove_w)
                        seq.start(widget)
                        if neg_widget is not None:
                            seq_no = (Animation(opacity=1, duration=0.3) +
                                      Animation(opacity=1, duration=sd) +
                                      Animation(opacity=0, duration=0.4))
                            seq_no.start(neg_widget)

                    t = Clock.schedule_once(trigger_emoji, trigger_delay)
                    self.emoji_timers.append(t)
            except Exception:
                pass

        Clock.schedule_once(process_emojis, 0.1)

if __name__ == '__main__':
    RayNeoTestApp().run()
