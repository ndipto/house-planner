# test_plan_render.py
# Mocked tests for the rendered-plan auto-check (no network).
#
# Run: .venv\Scripts\python.exe test_plan_render.py

import base64
import io
import json

from PIL import Image

from plan_render import (CANVAS, check_render, edit_image,
                         render_plan_checked)

ROOMS = [
    {"name": "Kitchen", "type": "kitchen", "x": 1.5, "y": 4.0,
     "w": 10.0, "d": 12.0},
    {"name": "Bedroom 1", "type": "bedroom", "x": 11.5, "y": 4.0,
     "w": 12.0, "d": 12.0},
    {"name": "Bath 1", "type": "bathroom", "x": 23.5, "y": 4.0,
     "w": 6.0, "d": 7.0},
]


def _png_bytes(color):
    img = Image.new("RGB", CANVAS, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _Item:
    def __init__(self, b64_json=None):
        self.b64_json = b64_json
        self.url = None


class _ImagesReply:
    def __init__(self, item):
        self.data = [item]


class _FakeImages:
    """Scripted images.edit: one PNG (solid color) per call."""

    def __init__(self, colors):
        self.colors = list(colors)
        self.calls = 0

    def edit(self, **kwargs):
        self.calls += 1
        color = self.colors[min(self.calls - 1,
                                len(self.colors) - 1)]
        raw = base64.b64encode(_png_bytes(color)).decode("ascii")
        return _ImagesReply(_Item(b64_json=raw))


class _TextReply:
    def __init__(self, output_text):
        self.output_text = output_text


class _FakeResponses:
    """Scripted responses.create: one reply text per call."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.last_input = None

    def create(self, **kwargs):
        self.calls += 1
        self.last_input = kwargs.get("input")
        text = self.replies[min(self.calls - 1,
                                len(self.replies) - 1)]
        if isinstance(text, Exception):
            raise text
        return _TextReply(text)


class _FakeClient:
    def __init__(self, colors=(), replies=()):
        self.images = _FakeImages(colors)
        self.responses = _FakeResponses(replies)


def _verdict(oks):
    return json.dumps({"rooms": [
        {"name": name, "ok": ok, "seen": "test furniture"}
        for name, ok in oks]})


def test_check_all_ok():
    client = _FakeClient(replies=[_verdict(
        [("Kitchen", True), ("Bedroom 1", True),
         ("Bath 1", True)])])
    check = check_render(_png_bytes("white"), ROOMS,
                         client=client)
    assert check["all_ok"], "all rooms ok"
    assert check["rooms"]["Kitchen"]["ok"], "kitchen ok"
    sent = client.responses.last_input
    assert sent[0]["content"][1]["type"] == "input_image", \
        "image sent as input_image block"
    print("PASS test_check_all_ok")


def test_check_flags_wrong_room():
    client = _FakeClient(replies=[_verdict(
        [("Kitchen", False), ("Bedroom 1", True)])])
    check = check_render(_png_bytes("white"), ROOMS,
                         client=client)
    assert not check["all_ok"], "one room fails"
    assert not check["rooms"]["Kitchen"]["ok"], "kitchen flagged"
    assert not check["rooms"]["Bath 1"]["ok"], \
        "missing verdict fails closed"
    print("PASS test_check_flags_wrong_room")


def test_check_bad_json_raises():
    client = _FakeClient(replies=["not json {"])
    try:
        check_render(_png_bytes("white"), ROOMS, client=client)
    except RuntimeError:
        print("PASS test_check_bad_json_raises")
        return
    raise AssertionError("bad JSON must raise")


def test_check_missing_key_raises():
    try:
        check_render(_png_bytes("white"), ROOMS, api_key="",
                     client=None)
    except RuntimeError:
        print("PASS test_check_missing_key_raises")
        return
    raise AssertionError("missing key must raise")


def test_edit_missing_key_raises():
    try:
        edit_image(b"xx", api_key="", client=None)
    except RuntimeError:
        print("PASS test_edit_missing_key_raises")
        return
    raise AssertionError("missing key must raise")


def test_retry_then_pass():
    bad = _verdict([("Kitchen", False), ("Bedroom 1", True),
                    ("Bath 1", True)])
    good = _verdict([("Kitchen", True), ("Bedroom 1", True),
                     ("Bath 1", True)])
    client = _FakeClient(colors=["red", "green"],
                         replies=[bad, good])
    final, check, attempts = render_plan_checked(
        ROOMS, [], [], 180.0, 40.0, 60.0, "north",
        max_retries=2, client=client)
    assert attempts == 2, "one retry, got %d" % attempts
    assert check["all_ok"], "second render passes"
    assert client.images.calls == 2, "two image calls"
    assert Image.open(io.BytesIO(final)).size == CANVAS, \
        "final keeps canvas size"
    print("PASS test_retry_then_pass")


def test_keeps_best_of_retries():
    worst = _verdict([("Kitchen", False), ("Bedroom 1", False),
                      ("Bath 1", True)])
    best = _verdict([("Kitchen", True), ("Bedroom 1", True),
                     ("Bath 1", False)])
    mid = _verdict([("Kitchen", True), ("Bedroom 1", False),
                    ("Bath 1", False)])
    client = _FakeClient(colors=["red", "green", "blue"],
                         replies=[worst, best, mid])
    final, check, attempts = render_plan_checked(
        ROOMS, [], [], 180.0, 40.0, 60.0, "north",
        max_retries=2, client=client)
    assert attempts == 3, "uses all retries, got %d" % attempts
    assert not check["all_ok"], "best still imperfect"
    pixel = Image.open(io.BytesIO(final)).getpixel((512, 100))
    assert pixel == (0, 128, 0), \
        "keeps the best render (green), got %s" % (pixel,)
    print("PASS test_keeps_best_of_retries")


def test_checker_error_keeps_first():
    client = _FakeClient(colors=["red"],
                         replies=[RuntimeError("boom")])
    final, check, attempts = render_plan_checked(
        ROOMS, [], [], 180.0, 40.0, 60.0, "north",
        max_retries=2, client=client)
    assert attempts == 1, "no retry on checker error"
    assert check is None, "check is None on checker error"
    assert client.images.calls == 1, "one image call only"
    print("PASS test_checker_error_keeps_first")


def main():
    test_check_all_ok()
    test_check_flags_wrong_room()
    test_check_bad_json_raises()
    test_check_missing_key_raises()
    test_edit_missing_key_raises()
    test_retry_then_pass()
    test_keeps_best_of_retries()
    test_checker_error_keeps_first()
    print("8/8 plan-render tests pass.")


if __name__ == "__main__":
    main()
