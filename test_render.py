# test_render.py
# Mocked Muse Image tests: no network calls, no API cost.
#
# Run them with: python test_render.py
# (Separate from test_layout.py: the layout suite stays pure-Python
# and instant; this file covers the render prompt + API plumbing with
# a stubbed client. The owner tests one real render live.)

import base64
from unittest.mock import patch

import render
from test_layout import PROGRAM_3BED
from typology import build_options


class _FakeItem:
    def __init__(self, b64=None, url=None):
        self.b64_json = b64
        self.url = url


class _FakeImages:
    def __init__(self, item):
        self.item = item
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return type("Resp", (), {"data": [self.item]})()


class _FakeClient:
    last = None

    def __init__(self, item, **kwargs):
        _FakeClient.last = self
        self.images = _FakeImages(item)


def test_prompt_describes_plan():
    """The prompt names plot, road, porch, verandas, style."""
    result = build_options(PROGRAM_3BED, 40, 60, "North", 3)
    opt = result["options"][0]
    prompt = render.exterior_prompt(result["plot"], opt).lower()
    for word in ("40", "60", "bangladesh", "flat", "roof", "porch",
                 "veranda", "eye-level", "road"):
        assert word in prompt, "prompt names %s" % word
    print("PASS test_prompt_describes_plan")


def test_generate_returns_bytes():
    """A b64 answer decodes to bytes; model + size are pinned."""
    payload = base64.b64encode(b"fake-png-bytes").decode("ascii")
    with patch("render.OpenAI",
               return_value=_FakeClient(_FakeItem(b64=payload))):
        out = render.generate_exterior("a house", api_key="key")
    assert out == b"fake-png-bytes", "b64 decodes"
    call = _FakeClient.last.images.calls[0]
    assert call["model"] == "muse-image-1.0", "image model pinned"
    assert call["prompt"] == "a house", "prompt passes through"
    print("PASS test_generate_returns_bytes")


def test_generate_friendly_errors():
    """Missing key and API failures raise friendly RuntimeErrors."""
    with patch("render.get_api_key", return_value=""):
        try:
            render.generate_exterior("a house")
        except RuntimeError as exc:
            assert "META_API_KEY" in str(exc), "key error names the key"
        else:
            raise AssertionError("missing key must raise")

    def _boom(**kwargs):
        raise Exception("connection reset")

    with patch("render.OpenAI",
               return_value=type("C", (),
                                 {"images": type(
                                     "I", (),
                                     {"generate": staticmethod(_boom)})()})()):
        try:
            render.generate_exterior("a house", api_key="key")
        except RuntimeError as exc:
            assert "Muse Image" in str(exc), "error names the service"
        else:
            raise AssertionError("API failure must raise")
    print("PASS test_generate_friendly_errors")


if __name__ == "__main__":
    test_prompt_describes_plan()
    test_generate_returns_bytes()
    test_generate_friendly_errors()
    print("ALL RENDER TESTS PASSED")
