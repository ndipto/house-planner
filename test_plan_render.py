# test_plan_render.py
# Mocked tests for the rendered-plan auto-check (no network).
#
# Run: .venv\Scripts\python.exe test_plan_render.py

import base64
import io
import json

from PIL import Image

from plan_render import (CANVAS, SIMPLE_PROMPT, check_render,
                         edit_image, edit_image_simple,
                         render_plan_checked, render_plan_simple,
                         simple_input_png, simple_prompt,
                         simple_shape)

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
        self.last_kwargs = None

    def edit(self, **kwargs):
        self.calls += 1
        self.last_kwargs = dict(kwargs)
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


def test_simple_shapes():
    assert simple_shape(40, 60, "North") == "portrait", "T1 tall"
    assert simple_shape(70, 40, "East") == "portrait", \
        "T7 draws upright (road-East rotation)"
    assert simple_shape(60, 40, "South") == "landscape", "drawn wide"
    assert simple_shape(40, 40, "South") == "square", "square"
    assert simple_shape(44, 40, "South") == "square", "near-square"
    print("PASS test_simple_shapes")


def test_simple_prompt_exact():
    assert simple_prompt() == SIMPLE_PROMPT
    assert simple_prompt("") == SIMPLE_PROMPT
    assert simple_prompt("marble tiles in living") == \
        SIMPLE_PROMPT + " marble tiles in living"
    assert "exactly the same" in SIMPLE_PROMPT
    assert SIMPLE_PROMPT.endswith("No extra text.")
    print("PASS test_simple_prompt_exact")


def test_simple_input_matches_plan():
    from test_layout import (PROGRAM_2BED, PROGRAM_3BED, WISHES_T7,
                             _program_t7)
    from typology import build_options

    cases = [(PROGRAM_3BED, 40, 60, "North", 3, "", None,
              (1024, 1536)),
             (_program_t7(), 70, 40, "East", 3, WISHES_T7, 90,
              (1024, 1536)),
             (PROGRAM_2BED, 60, 40, "South", 2, "", None,
              (1536, 1024))]
    for prog, fw, fd, road, nt, wishes, angle, size in cases:
        result = build_options(prog, fw, fd, road, nt, wishes,
                               angle)
        opt = result["options"][0]
        plot = result["plot"]
        img, _shape, target = simple_input_png(
            opt["placements"], opt.get("open_plan", []),
            opt.get("glass_partitions", []),
            float(plot.get("north_angle", 0)), plot["width"],
            plot["depth"], str(plot["road"]).lower())
        assert target == size, "%dx%d %s: target %s" % (fw, fd, road,
                                                       target)
        assert img.size == size, "input padded to output size"
        black = img.convert("L").histogram()[0]
        assert black > 1000, "walls drawn (black pixels)"
    print("PASS test_simple_input_matches_plan (3 shapes, walls drawn)")


def test_simple_single_call():
    client = _FakeClient(colors=["green"])
    final = render_plan_simple(
        ROOMS, [], [], 180.0, 40.0, 60.0, "north",
        extra="marble tiles in living", client=client)
    assert client.images.calls == 1, "exactly one image call"
    sent = client.images.last_kwargs
    assert sent["size"] == "1024x1536", "portrait size sent"
    assert sent["prompt"].startswith(SIMPLE_PROMPT), \
        "simple prompt sent"
    assert "marble tiles in living" in sent["prompt"], \
        "extra instructions appended"
    assert Image.open(io.BytesIO(final)).size == (1024, 1536)
    print("PASS test_simple_single_call")


def test_simple_missing_key_raises():
    try:
        edit_image_simple(b"xx", (1024, 1024), SIMPLE_PROMPT,
                          api_key="", client=None)
    except RuntimeError:
        print("PASS test_simple_missing_key_raises")
        return
    raise AssertionError("missing key must raise")


def main():
    test_check_all_ok()
    test_check_flags_wrong_room()
    test_check_bad_json_raises()
    test_check_missing_key_raises()
    test_edit_missing_key_raises()
    test_retry_then_pass()
    test_keeps_best_of_retries()
    test_checker_error_keeps_first()
    test_simple_shapes()
    test_simple_prompt_exact()
    test_simple_input_matches_plan()
    test_simple_single_call()
    test_simple_missing_key_raises()
    print("13/13 plan-render tests pass.")


if __name__ == "__main__":
    main()
