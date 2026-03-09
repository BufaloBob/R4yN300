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
import traceback
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from thefuzz import process, fuzz
import sounddevice as sd
from scipy.io import wavfile
import numpy as np

from shazamio import Shazam

AUDIO_INPUT_DEVICE = None

GROQ_API_KEY      = "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"
ACR_HOST          = "identify-eu-west-1.acrcloud.com"
ACR_ACCESS_KEY    = "decbcc1f6e68593c7f6fdbc603990533"
ACR_ACCESS_SECRET = "Jas1pzmo7Y0qFSReLTWxTxV2Hznglzq7CzTBLno4"

TARGET_LANGUAGE = "es"

SOGLIA_AFFINITA_SYNC   = 65
SOGLIA_DOPPIA_VERIFICA = 50

SYNC_SMOOTH_FACTOR     = 0.78
SYNC_DEAD_ZONE         = 0.12
SYNC_MIN_DIFF_HARD     = 3.0

LINE_VISUAL_OFFSET     = 0.00
WORD_VISUAL_OFFSET     = 0.00
EMOJI_WORD_OFFSET      = 0.08

SYNC_BOOTSTRAP_SECONDS = 10.0
SYNC_BOOTSTRAP_INTERVAL = 0.20
SYNC_BOOTSTRAP_DURATION = 2.20
SYNC_STEADY_INTERVAL    = 0.35
SYNC_STEADY_DURATION    = 4.00

FINESTRA_RICERCA_BASE  = 10
FINESTRA_RICERCA_EXTRA = 6

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
    'Rajdhani':   'https://github.com/google/fonts/raw/main/ofl/rajdhani/Rajdhani-Bold.ttf',
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

from emojis import extract_emojis, get_filename_for_emoji, FLAT_EMOJI_MAP

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

    BoxLayout:
        orientation: 'vertical'
        size_hint: 1, 1

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
                size_hint_x: 0.4
                background_color: [0.5, 0.5, 0.5, 1]
                on_press: app.toggle_sync_mode()

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
                    text_size: root.width - 20, self.height
                    max_lines: 1
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
                    text_size: root.width - 20, self.height
                    max_lines: 1
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
    return text.replace('\u2026', '...')

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

        self._sync_processing_lock = threading.Lock()
        self._last_sync_snapshot = 0
        self._continuous_recorder = None
        self._sync_locked = False
        self._sync_fast_until = 0.0

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
        self._apply_random_font()

        threading.Thread(target=self.master_omni_loop, daemon=True).start()
        return self.root_ui

    def _apply_random_font(self):
        if AVAILABLE_FONTS:
            candidates = [f for f in AVAILABLE_FONTS if f != self.current_font]
            if not candidates:
                candidates = AVAILABLE_FONTS
            self.current_font = random.choice(candidates)
        else:
            self.current_font = None
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

    def toggle_omni_listen(self):
        self.omni_mode = not self.omni_mode
        if self.omni_mode:
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
                    def _search(q):
                        q = q.strip()
                        if not q or q in queries_tried:
                            return None
                        queries_tried.add(q)
                        try:
                            r = http_get("https://lrclib.net/api/search",
                                         params={"q": q}, timeout=5)
                            synced = [x for x in r.json() if x.get('syncedLyrics')]
                            if synced:
                                return synced[0]
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
                    return result

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

            # --- Active sync: overlapping 5s recordings every 0.5s ---
            if has_lyrics and playing:
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

                    if len(pending) < 2:
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
            fs = 44100
            duration_long = 3.0
            overlap = 1.0

            rec_long = sd.rec(int(duration_long * fs), samplerate=fs, channels=1,
                              dtype='float32', device=AUDIO_INPUT_DEVICE)
            sd.wait()

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
                def _search_lrclib(q):
                    q = q.strip()
                    if not q or q in queries_tried:
                        return None
                    queries_tried.add(q)
                    print(f"[lrclib] Ricerca: '{q}'")
                    try:
                        r = http_get("https://lrclib.net/api/search",
                                     params={"q": q}, timeout=5)
                        synced = [x for x in r.json() if x.get('syncedLyrics')]
                        if synced:
                            return synced[0]
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
                            r = http_get("https://lrclib.net/api/search", params={"q": q}, timeout=5)
                            synced = [x for x in r.json() if x.get('syncedLyrics')]
                            if synced:
                                return synced[0]
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
                        self.start_hybrid_engine()
                        self.root_ui.ids.results_list.clear_widgets()
                        self.set_status(f"🎵 Traccia Attiva: {_title} — {_artist}")
                    Clock.schedule_once(auto_load_fb, 0)
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
                Clock.schedule_once(lambda dt: self.set_status(
                    f"🎵 {best_title} — nessun testo sincronizzato"
                ))
                return

            best   = lrclib_result['synced']
            title  = lrclib_result['title']
            artist = lrclib_result['artist']

            def auto_load(dt, r=best, t=f"{title} — {artist}", _title=title, _artist=artist):
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
                self.set_status(f"🎵 Traccia Attiva: {t}")
            Clock.schedule_once(auto_load, 0)
            print(f"✅ [TESTO] Inizio Sincronizzazione...")

        except Exception as e:
            print(f"[Riconoscimento] Errore: {e}")

    def _process_sync_chunk(self, audio_float32, t_snapshot, chunk_duration):
        """Process a 5s audio chunk from the ring buffer: normalize, Whisper, adjust sync."""
        try:
            if not self.lyrics_data or not self.is_playing:
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

            if resp.status_code != 200:
                print(f"[Whisper] HTTP {resp.status_code}")
                return

            result = resp.json()
            text = result.get('text', "").strip()

            # Use segment timestamps from verbose_json for precise timing
            segments = result.get('segments', [])
            if segments:
                seg_start = segments[0].get('start', 0.0)
                t_phrase_start = (t_snapshot - chunk_duration) + seg_start
            else:
                phrase_offset = estimate_phrase_start_in_buffer(text, chunk_duration, whisper_latency)
                t_phrase_start = (t_snapshot - chunk_duration) + phrase_offset

            print(f"🎙️ Whisper: '{text}' (latency={whisper_latency:.2f}s chunk={chunk_duration:.1f}s)")

            lower_text = clean_text(text)
            if not any(c.isalpha() for c in lower_text):
                return

            lower_text_full = text.lower()
            is_hallucination = False
            if any(f in lower_text_full for f in HALL_FRASES):
                is_hallucination = True
            elif any(h in lower_text for h in HALL_PAROLE) and len(lower_text.split()) < 4:
                is_hallucination = True
            elif len(text) < 5 or len(lower_text.split()) < 3:
                is_hallucination = True

            with self._sync_processing_lock:
                # Skip if a newer snapshot was already processed
                if t_snapshot < self._last_sync_snapshot:
                    return

                if is_hallucination:
                    if self.omni_mode and self.lyrics_data:
                        self.remix_miss_streak += 1
                        soglia_cambio = 4 if not self.sync_enabled else 6
                        print(f"   🔍 Hallucination miss: {self.remix_miss_streak}/{soglia_cambio}")
                        if self.remix_miss_streak >= soglia_cambio:
                            print("🚨 CANZONE CAMBIATA (troppe allucinazioni) — avvio verifica")
                            self._needs_song_verification = True
                            self.remix_miss_streak = 0
                    return

                if self.omni_mode:
                    text_matches_song = self._quick_text_match(text)
                    soglia_cambio = 4 if not self.sync_enabled else 6
                    if text_matches_song:
                        self.remix_miss_streak = 0
                        if self.sync_enabled:
                            self.sync_confidence = min(1.0, self.sync_confidence + 0.1)
                    else:
                        self.remix_miss_streak += 1
                        print(f"   🔍 Remix check: miss {self.remix_miss_streak}/{soglia_cambio}")
                        if self.remix_miss_streak >= soglia_cambio:
                            print("🚨 CANZONE CAMBIATA — avvio verifica parallela")
                            self._needs_song_verification = True
                            self.remix_miss_streak = 0
                            return

                if not self.sync_enabled:
                    return

                match_found = self.adjust_sync(text, t_phrase_start)

                if match_found:
                    self._last_sync_snapshot = t_snapshot
                    self.consecutive_misses = 0
                    self.sync_confidence = min(1.0, self.sync_confidence + 0.2)
                else:
                    self.consecutive_misses += 1
                    self.sync_confidence = max(0.0, self.sync_confidence - 0.2)
                    if self.consecutive_misses >= 5 and self.anchor_song_time is not None:
                        print(f"⚠️ {self.consecutive_misses} miss consecutivi — resetto anchor")
                        self.anchor_song_time = None
                        self.anchor_real_time = None
                        self.sync_perfect_streak = 0
                        self.sync_verify_mode = False

        except Exception as e:
            print(f"[Sync Chunk] Eccezione: {e}")

    def _quick_text_match(self, text: str) -> bool:
        if not self.lyrics_data or not text:
            return True

        text_clean = clean_text(text)
        if len(text_clean) < 5:
            return True

        pool_full = getattr(self, '_lyrics_clean_pool', None)
        if pool_full is None:
            pool_full = [r['clean'] for r in self.lyrics_data if len(r['text']) >= 4]
            self._lyrics_clean_pool = pool_full
        if not pool_full:
            return True

        best_full = process.extractOne(text_clean, pool_full, scorer=fuzz.partial_ratio)
        score_full = best_full[1] if best_full else 0

        if score_full >= 65:
            return True

        print(f"   🔍 Canzone check: score={score_full}% < 65% → canzone diversa")
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

        nuovo_start = t_phrase_start - riga_vincente['time']
        diff_abs = abs(self.start_timestamp - nuovo_start)

        if diff_abs < SYNC_DEAD_ZONE:
            self.sync_perfect_streak += 1
            if self.sync_perfect_streak >= 2:
                self.sync_verify_mode = True
                print(f"✅ GIÀ PERFETTO (Δ={diff_abs:.2f}s) streak={self.sync_perfect_streak} → modalità VERIFICA")
            else:
                print(f"✅ GIÀ PERFETTO (Δ={diff_abs:.2f}s < zona morta {SYNC_DEAD_ZONE}s)")
            self.update_sync_ui("Sincronizzato ✅", [0, 1, 0, 1])
            self._update_anchor(riga_vincente['time'], t_phrase_start)
            if self._sync_locked:
                self._sync_locked = False
                def _unlock_perfect(dt, ns=nuovo_start, idx=riga_vincente['index']):
                    self.start_timestamp = ns
                    self.current_index = idx
                    self.update_display(idx)
                Clock.schedule_once(_unlock_perfect, 0)
            return True

        self.sync_perfect_streak = 0
        self.sync_verify_mode    = False

        if diff_abs < SYNC_MIN_DIFF_HARD:
            start_applicato = (
                self.start_timestamp * (1.0 - SYNC_SMOOTH_FACTOR) +
                nuovo_start * SYNC_SMOOTH_FACTOR
            )
            print(f"✅ SYNC SMOOTH: Δ={diff_abs:.2f}s → sposto di {abs(self.start_timestamp - start_applicato):.2f}s")
        else:
            start_applicato = nuovo_start
            print(f"✅ SYNC HARD JUMP: Δ={diff_abs:.2f}s")

        self.update_sync_ui("Sincronizzato ✅", [0, 1, 0, 1])
        self._update_anchor(riga_vincente['time'], t_phrase_start)

        if riga_vincente['time'] > self.max_song_time_reached:
            self.max_song_time_reached = riga_vincente['time']

        def applica_ui(dt, ns=start_applicato, idx=riga_vincente['index']):
            self.start_timestamp = ns
            self.current_index = idx
            if self._sync_locked:
                self._sync_locked = False
            self.update_display(idx)

        Clock.schedule_once(applica_ui, 0)
        return True

    def _update_anchor(self, song_time: float, real_time: float):
        self.anchor_song_time = song_time
        self.anchor_real_time = real_time
        self.sync_history.append((song_time, real_time))
        # Keep only last 8 entries
        if len(self.sync_history) > 8:
            self.sync_history = self.sync_history[-8:]
        print(f"   📍 Anchor aggiornato: song={song_time:.1f}s @ real={real_time:.1f}")

    def start_manual_search(self, query):
        self.root_ui.ids.results_list.clear_widgets()
        self.set_status(f"🔍 Ricerca: {query}")
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        try:
            r = http_get("https://lrclib.net/api/search", params={"q": query}, timeout=10)
            results = r.json()
            Clock.schedule_once(lambda dt: self._show_results(results))
        except Exception as e:
            print(f"[Ricerca] Errore: {e}")
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
                        self.set_status(f"🎵 Traccia Attiva: {_t} — {_a}")
                    else:
                        self.set_status("⚠️ SENZA TESTO SINCRONIZZATO!")
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

    def start_hybrid_engine(self):
        self.current_index = 0
        self.start_timestamp = time.time()
        self.is_playing = True
        self._sync_locked = self.sync_enabled
        self._sync_fast_until = time.time() + SYNC_BOOTSTRAP_SECONDS
        Clock.unschedule(self.update_loop)
        Clock.schedule_interval(self.update_loop, 0.016)
        self.root_ui.ids.lyric_prev.text = ""
        self.root_ui.ids.lyric_next.text = ""
        if self.lyrics_data:
            self.update_display(0)
            self.highlight_current_word(0.0)
        else:
            self.root_ui.ids.lyric_curr.text = ""
            self.root_ui.ids.lyric_curr.opacity = 1

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
            # Use start-based: highlight last word whose start <= elapsed_w
            active_word_idx = 0
            for i, w in enumerate(words_timed):
                if elapsed_w >= w['start']:
                    active_word_idx = i
                else:
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
            singing_time = line_duration * 0.96

            word_starts = []
            t = 0.0
            for sc in syl:
                word_starts.append(lyric_time + t)
                t += singing_time * (sc / total_syl)

            # Use start-based: highlight last word whose start <= elapsed_w
            active_word_idx = 0
            for i in range(len(words)):
                if elapsed_w >= word_starts[i]:
                    active_word_idx = i
                else:
                    break

        if self.last_active_word_idx != active_word_idx or self.last_lyric_idx != self.current_index:
            self.last_active_word_idx = active_word_idx
            self.last_lyric_idx = self.current_index

            # compute font size once per line (cache to avoid jitter)
            if self.last_lyric_idx != getattr(self, '_cached_line_idx', -1):
                base = int(Window.height * 0.072)
                total_chars = sum(len(w) for w in words) + len(words) - 1
                est_w = total_chars * base * 0.65
                avail = Window.width - 80
                if est_w > avail and est_w > 0:
                    base = max(int(Window.height * 0.020), int(base * avail / est_w))
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
            if lbl_id == 'lyric_prev' and clean_txt:
                self.root_ui.ids[lbl_id].text = f"[color={neon}]{clean_txt}[/color]"
            else:
                self.root_ui.ids[lbl_id].text = clean_txt

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
                emojis_to_show = extract_emojis(c_clean)
                if not emojis_to_show:
                    return
                slot_duration = min(2.0, max(0.35, line_duration / max(1, len(emojis_to_show))))
                show_duration = min(1.2, slot_duration * 0.65)

                for i, emoji in enumerate(emojis_to_show):
                    target_word_idx = None
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

                    def trigger_emoji(dt, e=emoji, sd=show_duration, twi=target_word_idx):
                        is_left = True
                        if twi is not None and words_raw:
                            is_left = twi < (len(words_raw) / 2.0)

                        if is_left:
                            zone = random.choice(['tl', 'bl'])
                            positions = {
                                'tl': (random.uniform(0.06, 0.20), random.uniform(0.57, 0.74)),
                                'bl': (random.uniform(0.06, 0.20), random.uniform(0.20, 0.36)),
                            }
                        else:
                            zone = random.choice(['tr', 'br'])
                            positions = {
                                'tr': (random.uniform(0.80, 0.94), random.uniform(0.57, 0.74)),
                                'br': (random.uniform(0.80, 0.94), random.uniform(0.20, 0.36)),
                            }

                        pos_x, pos_y = positions[zone]
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

                        widget.pos_hint = {'center_x': pos_x, 'center_y': pos_y}
                        widget.angle = random.randint(-25, 25)
                        widget.opacity = 0
                        self.root_ui.ids.emoji_layer.add_widget(widget)

                        seq = (Animation(opacity=1, duration=0.3) +
                               Animation(opacity=1, duration=sd) +
                               Animation(opacity=0, duration=0.4))

                        def remove_w(a, w):
                            if w in self.root_ui.ids.emoji_layer.children:
                                self.root_ui.ids.emoji_layer.remove_widget(w)
                        seq.bind(on_complete=remove_w)
                        seq.start(widget)

                    t = Clock.schedule_once(trigger_emoji, trigger_delay)
                    self.emoji_timers.append(t)
            except Exception:
                pass

        Clock.schedule_once(process_emojis, 0.1)

if __name__ == '__main__':
    RayNeoTestApp().run()