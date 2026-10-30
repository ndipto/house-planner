# test_voice.py
# Mocked Muse Voice Transcribe tests: no network calls, no API cost.
#
# Run them with: python test_voice.py
# (Same split as test_render.py: the layout suite stays pure-Python;
# this file covers the transcribe plumbing with a stubbed urlopen.
# The owner tests one real transcription live with a microphone.)

import io
import json
import struct
import urllib.error
from unittest.mock import patch

import voice


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _make_wav(rate=8000, channels=2, seconds=1):
    """Synthesize a small PCM WAV (non-target rate, stereo)."""
    pcm = b"\x00\x01" * rate * seconds * channels
    head = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(pcm),
                       b"WAVE", b"fmt ", 16, 1, channels, rate,
                       rate * channels * 2, channels * 2, 16,
                       b"data", len(pcm))
    return head + pcm


def test_wav_normalized():
    """Stereo 8 kHz in, mono 16-bit 24 kHz WAV out."""
    raw = _make_wav()
    out = voice.to_supported_wav(raw)
    assert out[0:4] == b"RIFF" and out[8:12] == b"WAVE", "WAV kept"
    channels, rate, samples = voice._read_wav(out)
    assert channels == 1, "mono"
    assert rate == 24000, "24 kHz"
    assert len(samples) == 24000, "one second kept"
    for bad in (b"", None, b"not-a-wav-file"):
        try:
            voice.to_supported_wav(bad)
        except RuntimeError:
            pass
        else:
            raise AssertionError("bad input must raise")
    print("PASS test_wav_normalized")


def test_transcribe_returns_text():
    """A JSON answer yields the transcript; request part matches docs."""
    calls = []

    def _fake(request, timeout=None):
        calls.append(request)
        payload = {"sessionId": "s1",
                   "transcript": "  home office  ",
                   "audioDurationMs": 1500, "turns": []}
        return _FakeResp(json.dumps(payload).encode("utf-8"))

    with patch("voice.urllib.request.urlopen", _fake):
        out = voice.transcribe_audio(_make_wav(), api_key="key")
    assert out == "home office", "transcript stripped"
    req = calls[0]
    assert req.full_url.endswith("/asr/transcribe"), "voice endpoint"
    assert req.headers["Authorization"] == "Bearer key", "bearer key"
    assert req.headers["Accept"] == "application/json", "json answer"
    body = req.data.decode("latin1")
    assert '"model": "muse-voice-transcribe-1.0"' in body, "model pinned"
    assert '"audioEncoding": "WAV"' in body, "WAV encoding"
    assert '"mode": "PUSH_TO_TALK"' in body, "push-to-talk mode"
    assert 'name="request"' in body and 'name="audio"' in body, \
        "both multipart parts"
    print("PASS test_transcribe_returns_text")


def test_transcribe_friendly_errors():
    """Missing key, oversize, HTTP states and failure all explain."""
    with patch("voice.get_api_key", return_value=""):
        try:
            voice.transcribe_audio(_make_wav())
        except RuntimeError as exc:
            assert "META_API_KEY" in str(exc), "key error names the key"
        else:
            raise AssertionError("missing key must raise")
    long_wav = _make_wav(seconds=1)
    with patch("voice.MAX_AUDIO_BYTES", len(long_wav) - 1):
        try:
            voice.transcribe_audio(long_wav, api_key="key")
        except RuntimeError as exc:
            assert "32 MB" in str(exc), "oversize explained"
        else:
            raise AssertionError("oversize audio must raise")

    def _http_error(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 429, "limited",
                                     {}, None)

    with patch("voice.urllib.request.urlopen", _http_error):
        try:
            voice.transcribe_audio(_make_wav(), api_key="key")
        except RuntimeError as exc:
            assert "429" in str(exc), "rate limit named"
        else:
            raise AssertionError("HTTP failure must raise")

    def _boom(request, timeout=None):
        raise Exception("connection reset")

    with patch("voice.urllib.request.urlopen", _boom):
        try:
            voice.transcribe_audio(_make_wav(), api_key="key")
        except RuntimeError as exc:
            assert "Muse Voice" in str(exc), "error names the service"
        else:
            raise AssertionError("API failure must raise")
    silent = _FakeResp(json.dumps({"transcript": "  "}).encode("utf-8"))
    with patch("voice.urllib.request.urlopen",
               return_value=silent):
        try:
            voice.transcribe_audio(_make_wav(), api_key="key")
        except RuntimeError as exc:
            assert "no transcript" in str(exc), "empty answer explained"
        else:
            raise AssertionError("empty transcript must raise")
    print("PASS test_transcribe_friendly_errors")


if __name__ == "__main__":
    test_wav_normalized()
    test_transcribe_returns_text()
    test_transcribe_friendly_errors()
    print("ALL VOICE TESTS PASSED")
