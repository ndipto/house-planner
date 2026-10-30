# render.py
# Exterior concept renders with Muse Image (Meta Model API).
#
# What this file does:
#   1. exterior_prompt() turns one finished option into a one-paragraph
#      image prompt (plot size, road side, porch, verandas, roof, style).
#   2. generate_exterior() sends it to Muse Image and returns PNG bytes.
#
# Docs (checked Oct 31, 2026): dev.meta.ai/docs/image-generation -
# model "muse-image-1.0", single-shot /v1/images/generations endpoint,
# OpenAI-compatible, so the normal OpenAI client works with our base URL.
# The key is read via ai_program.get_api_key() (st.secrets, else env).

import base64
import urllib.request

from openai import OpenAI

from ai_program import BASE_URL, get_api_key

IMAGE_MODEL = "muse-image-1.0"
IMAGE_SIZE = "1024x1024"


def _third(value, total):
    """Left/center/right (or front/back) third for a plan coordinate."""
    if value < total / 3.0:
        return 0
    if value > 2.0 * total / 3.0:
        return 2
    return 1


def exterior_prompt(plot, option):
    """One-paragraph Muse Image prompt for an option's street view.

    plot: {"width", "depth", "road"}. Coordinates are road-relative
    (low y = the road side), so front/back/left/right read straight
    off the plan whatever the real compass is.
    """
    rooms = option.get("placements", [])
    plot_w = float(plot["width"])
    plot_d = float(plot["depth"])
    road = str(plot.get("road", "south")).lower()
    beds = sum(1 for r in rooms if r["type"] == "bedroom")
    porch = next((r for r in rooms if r["type"] == "porch"), None)
    if porch is None:
        porch_txt = "a simple front door with steps"
    else:
        side = ("left", "center", "right")[
            _third(porch["x"] + porch["w"] / 2.0, plot_w)]
        porch_txt = "a front porch on the %s with steps up from the gate" \
            % side
    verandas = [r for r in rooms if r["type"] == "veranda"]
    spots = []
    for ver in verandas:
        cx, cy = ver["x"] + ver["w"] / 2.0, ver["y"] + ver["d"] / 2.0
        if cy < plot_d / 2.0:
            spots.append("front")
        elif cx < plot_w / 3.0 or cx > 2.0 * plot_w / 3.0:
            spots.append("side")
        else:
            spots.append("back")
    if not spots:
        ver_txt = "no side verandas"
    elif len(spots) == 1:
        ver_txt = "1 %s veranda" % spots[0]
    else:
        ver_txt = "%d verandas (%s)" % (len(spots), ", ".join(spots))
    jali = " with a decorative jali screen wall on the road-facing veranda" \
        if any(v.get("screened_jali") for v in verandas) else ""
    return (
        "Eye-level architectural photograph from the road of a "
        "single-storey Bangladeshi family house on a %.0f ft by %.0f ft "
        "plot, road along the %s side. Flat concrete roof with a thin "
        "sunshade over the openings, warm brick and off-white plaster "
        "walls, green tropical garden with shrubs in the setback. %s%s; "
        "%s; %d bedrooms inside. Bright daylight, monsoon-climate "
        "detailing, no people, no cars, no text."
        % (plot_w, plot_d, road, porch_txt, jali, ver_txt, beds)
    )


def generate_exterior(prompt, api_key=None):
    """Render one exterior view; return the PNG bytes.

    Raises RuntimeError with a friendly message when the key is
    missing, the call fails, or no image comes back.
    """
    key = (api_key or get_api_key() or "").strip()
    if not key:
        raise RuntimeError(
            "META_API_KEY is missing, so no render was made. On "
            "Streamlit Cloud add it under Settings > Secrets; on your "
            "laptop put META_API_KEY=your-key-here in .env.")
    try:
        client = OpenAI(api_key=key, base_url=BASE_URL)
        result = client.images.generate(model=IMAGE_MODEL, prompt=prompt,
                                        size=IMAGE_SIZE, n=1)
        item = result.data[0]
        if getattr(item, "b64_json", None):
            return base64.b64decode(item.b64_json)
        if getattr(item, "url", None):
            with urllib.request.urlopen(item.url, timeout=60) as resp:
                return resp.read()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "Muse Image could not render this view (%s). Check your "
            "connection and API key, then try again."
            % str(exc)[:160])
    raise RuntimeError("Muse Image returned no image; please try again.")
