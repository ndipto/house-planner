# voice.py
# Spoken briefs with Muse Voice Transcribe (Meta Model API).
#
# What this file does:
#   1. to_supported_wav() reshapes a browser WAV recording into what
#      the endpoint accepts (mono, 16-bit PCM, 24 kHz) with the
#      standard library only - no ffmpeg, so Streamlit Cloud works.
#   2. transcribe_audio() sends it to the one-shot file endpoint and
#      returns the plain-text transcript, which the app drops into
#      the wishes box (Bangla or English - the languageBias hint is
#      omitted, so the model detects the language itself).
#
# Official docs (read Oct 31, 2026):
# https://dev.meta.ai/docs/speech-to-text and
# https://dev.meta.ai/docs/api-reference/voice/transcribe :
# POST https://api.meta.ai/v1/asr/transcribe, multipart/form-data
# with parts "request" (JSON settings incl. model
# "muse-voice-transcribe-1.0", audioEncoding "WAV", mode
# "PUSH_TO_TALK") and "audio" (the WAV file); header
# "Authorization: Bearer <key>", "Accept: application/json".
# The JSON answer carries the full text in "transcript" in every
# mode. Caps: 32 MB body / 10 minutes of audio.
# The key is read via ai_program.get_api_key() (st.secrets, else env).

import io
import json
import struct
import urllib.error
import urllib.request
import uuid

from ai_program import BASE_URL, get_api_key

VOICE_MODEL = "muse-voice-transcribe-1.0"
TRANSCRIBE_PATH = "/asr/transcribe"
TARGET_RATE = 24000  # the model's native sample rate (docs)
MAX_AUDIO_BYTES = 32 * 1024 * 1024  # server cap; refuse bigger early


def _read_wav(raw):
    """Parse plain-PCM WAV bytes -> (channels, rate, samples).

    samples is a flat list of signed 16-bit ints (one per channel per
    frame). Raises ValueError when the bytes are not plain PCM WAV.
    Plain struct parsing only - no audio libraries needed.
    """
    if len(raw) < 44 or raw[0:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(raw):
        tag, size = raw[pos:pos + 4], struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if tag == b"fmt ":
            fmt = body
        elif tag == b"data" and data is None:
            data = body
        pos += 8 + size + (size % 2)
    if fmt is None or data is None or len(fmt) < 16:
        raise ValueError("broken WAV file")
    kind, channels, rate = struct.unpack("<HHI", fmt[0:8])
    width = struct.unpack("<H", fmt[14:16])[0] // 8  # bits -> bytes
    if kind != 1 or channels < 1 or width not in (1, 2, 3, 4):
        raise ValueError("not plain PCM WAV")
    step = width * channels
    frames = len(data) // step
    if frames < 1:
        raise ValueError("empty WAV file")
    samples = []
    for i in range(frames):
        for ch in range(channels):
            chunk = data[i * step + ch * width:(i * step + ch * width) + width]
            if width == 1:
                samples.append((chunk[0] - 128) * 256)  # unsigned 8-bit
            elif width == 2:
                samples.append(struct.unpack("<h", chunk)[0])
            elif width == 3:
                samples.append(struct.unpack("<i", chunk + b"\x00")[0] >> 8)
            else:
                samples.append(struct.unpack("<i", chunk)[0] >> 16)
    return channels, rate, samples


def _write_wav(samples, rate):
    """Pack mono signed-16-bit samples into minimal WAV bytes."""
    pcm = struct.pack("<%dh" % len(samples), *samples)
    head = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(pcm),
                       b"WAVE", b"fmt ", 16, 1, 1, rate, rate * 2, 2,
                       16, b"data", len(pcm))
    return head + pcm


def to_supported_wav(raw):
    """Reshape a WAV recording to mono 16-bit PCM at 24 kHz.

    Returns fresh WAV bytes. Raises RuntimeError (friendly) when the
    input is not a WAV file at all - the endpoint only takes WAV, and
    non-WAV containers need ffmpeg, which the app does not ship.
    """
    if not raw:
        raise RuntimeError("No audio was recorded; please try again.")
    try:
        channels, rate, samples = _read_wav(raw)
    except (ValueError, struct.error, IndexError):
        raise RuntimeError(
            "That recording is not a WAV file, and only WAV can be "
            "sent for transcription. Please record again - or just "
            "type the brief into the wishes box.")
    frames = len(samples) // channels
    if channels > 1:  # stereo -> mono (average both ears)
        mono = [sum(samples[i * channels:(i + 1) * channels]) // channels
                for i in range(frames)]
    else:
        mono = samples
    if rate != TARGET_RATE:  # linear resample to the model's rate
        count = max(1, int(round(frames * TARGET_RATE / rate)))
        mono = [mono[min(frames - 1, int(i * frames / count))]
                for i in range(count)]
    return _write_wav(mono, TARGET_RATE)


def _multipart_body(parts):
    """Encode small multipart/form-data by hand (stdlib only).

    parts: [(field name, filename or None, content type, bytes)].
    Returns (body, content_type).
    """
    boundary = uuid.uuid4().hex
    chunks = []
    for name, filename, content_type, payload in parts:
        head = '--%s\r\nContent-Disposition: form-data; name="%s"' \
            % (boundary, name)
        if filename is not None:
            head += '; filename="%s"' % filename
        head += "\r\nContent-Type: %s\r\n\r\n" % content_type
        chunks.append(head.encode("utf-8") + payload + b"\r\n")
    chunks.append(("--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(chunks), \
        "multipart/form-data; boundary=%s" % boundary


def transcribe_audio(audio_bytes, api_key=None, session_id=None):
    """Transcribe one recording; return the plain-text transcript.

    audio_bytes: the recorded file (browser WAV from the mic widget).
    Raises RuntimeError with a friendly message when the key is
    missing, the file is too big or not WAV, or the call fails.
    """
    key = (api_key or get_api_key() or "").strip()
    if not key:
        raise RuntimeError(
            "META_API_KEY is missing, so nothing was transcribed. On "
            "Streamlit Cloud add it under Settings > Secrets; on your "
            "laptop put META_API_KEY=your-key-here in .env.")
    wav = to_supported_wav(audio_bytes)
    if len(wav) > MAX_AUDIO_BYTES:
        raise RuntimeError(
            "That recording is over the 32 MB limit; please record a "
            "shorter brief (under 10 minutes).")
    settings = {"model": VOICE_MODEL, "audioEncoding": "WAV",
                "mode": "PUSH_TO_TALK"}
    body, content_type = _multipart_body([
        ("request", None, "application/json",
         json.dumps(settings).encode("utf-8")),
        ("audio", "brief.wav", "audio/wav", wav),
    ])
    url = BASE_URL + TRANSCRIBE_PATH
    if session_id:
        url += "?sessionId=" + str(session_id)
    request = urllib.request.Request(
        url, data=body,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": content_type,
                 "Accept": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_http_hint(exc.code))
    except Exception as exc:
        raise RuntimeError(
            "Muse Voice could not transcribe this (%s). Check your "
            "connection and API key, then try again."
            % str(exc)[:160])
    text = data.get("transcript", "") if isinstance(data, dict) else ""
    if not str(text).strip():
        raise RuntimeError(
            "Muse Voice returned no transcript; please try again.")
    return str(text).strip()


def _http_hint(code):
    """One friendly line per documented failure status."""
    if code == 400:
        return ("Muse Voice refused the audio (HTTP 400): it must be a "
                "WAV recording under 10 minutes. Please record again.")
    if code == 413:
        return ("That recording is over the 32 MB limit (HTTP 413); "
                "please record a shorter brief.")
    if code == 429:
        return ("Muse Voice is rate-limited right now (HTTP 429); "
                "please wait a minute and try again.")
    if code == 500:
        return ("Muse Voice failed to process this (HTTP 500); please "
                "try once more.")
    return ("Muse Voice could not transcribe this (HTTP %s). Check "
            "your API key and connection, then try again." % code)
