"""Claude bbox feasibility experiment (#96) — gates B-full from #24.

Asks the production tagging model for per-item bounding boxes on multi-item
photos, draws the boxes onto the images with Pillow, and saves annotated
copies for eyeballing. The decision artifact is a comment on #96: if the
boxes are usable, B-full (cropped per-item thumbnails) gets an issue; if
not, the negative result gets documented and B-full is deferred.

Deliberately uses services.claude.MODEL — the question is whether the model
we actually tag with can localize items, not whether some other model can.
The photo goes through ensure_under_limit first (same as the real upload
path), then is shrunk to fit the vision API's internal resize limits
(~1.15 megapixels / 1568px long edge). That second step is load-bearing:
the API silently downscales anything larger before the model sees it, so
the model reports coordinates in the resized frame — drawing those on the
original shifts every box toward the top-left by the resize factor. By
resizing ourselves first, the bytes the model sees are pixel-identical to
the bytes we annotate.

Run from repo root against ~10 real photos (accessories on a tray, clothes
laid flat, a mixed pile):

    uv --project backend run python backend/scripts/bbox_experiment.py photo1.jpg photo2.heic ...
    uv --project backend run python backend/scripts/bbox_experiment.py --out /tmp/bbox photos/*.jpg

Annotated copies land in ./bbox_annotated/ by default (gitignored output;
the script itself is checked in — a documented negative result is worth
keeping).
"""

import argparse
import base64
import io
import sys
from pathlib import Path

# Make `services` importable when run as `python backend/scripts/...`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

# Load the single repo-root .env regardless of cwd.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from PIL import Image, ImageDraw  # noqa: E402

from services.claude import MODEL, client, parse_json  # noqa: E402
from services.image import ensure_under_limit  # noqa: E402

BBOX_SYSTEM_PROMPT = """You are a clothing-tagging assistant for a personal wardrobe app.

Given a photo containing one or more clothing/accessory items, enumerate every
distinct item and return a JSON object of the shape:

{"items": [{"name": ..., "type": ..., "bbox": [x1, y1, x2, y2]}, ...]}

Fields per item:

- name: short descriptive name, 3-7 words.
- type: closest match from: jacket, coat, vest, shirt, t-shirt, sweater,
  blouse, dress, skirt, trousers, jeans, shorts, shoes, boots, sneakers,
  sandals, bag, scarf, hat, belt, accessory, other.
- bbox: the item's bounding box as [x1, y1, x2, y2] in PIXEL coordinates of
  the provided image, where (0, 0) is the top-left corner, (x1, y1) is the
  box's top-left and (x2, y2) its bottom-right. The box should tightly
  enclose the entire visible item.

Rules:
- One entry per distinct physical item; tag at most 9 (the most prominent).
- If the photo contains no clothing or accessory items, return {"items": []}.

Return ONLY the JSON object, no commentary, no markdown fences.
"""

# Cycle of visually distinct outline colors for up to 9 boxes.
COLORS = [
    "#e6194b",
    "#3cb44b",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#42d4f4",
    "#f032e6",
    "#9a6324",
    "#000075",
]

# Anthropic vision API internal resize limits: images beyond either bound are
# downscaled server-side before the model sees them, which desyncs the model's
# coordinate space from ours. Stay under both so no hidden resize happens.
VISION_MAX_EDGE = 1568
VISION_MAX_PIXELS = 1_150_000

MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
}


def fit_to_vision_limits(image_bytes: bytes, mime: str) -> tuple[bytes, str]:
    """Shrink the image below the API's resize thresholds (no-op if already under)."""
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    scale = min(
        1.0,
        VISION_MAX_EDGE / max(w, h),
        (VISION_MAX_PIXELS / (w * h)) ** 0.5,
    )
    if scale >= 1.0:
        return image_bytes, mime
    img = img.convert("RGB").resize(
        (int(w * scale), int(h * scale)), Image.Resampling.LANCZOS
    )
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue(), "image/jpeg"


def ask_for_boxes(
    image_bytes: bytes, mime_type: str, width: int, height: int
) -> list[dict]:
    resp = client().messages.create(
        model=MODEL,
        max_tokens=4096,
        system=[{"type": "text", "text": BBOX_SYSTEM_PROMPT}],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": base64.standard_b64encode(image_bytes).decode(
                                "ascii"
                            ),
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"This image is {width}x{height} pixels. "
                            "Tag every item with its bounding box."
                        ),
                    },
                ],
            }
        ],
    )
    data = parse_json(resp)
    items = data.get("items", []) if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


def annotate(image_bytes: bytes, items: list[dict]) -> Image.Image:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    stroke = max(2, img.width // 300)
    for i, item in enumerate(items):
        bbox = item.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4):
            print(f"    [{i}] {item.get('name', '?')}: unusable bbox {bbox!r}")
            continue
        color = COLORS[i % len(COLORS)]
        x1, y1, x2, y2 = bbox
        draw.rectangle([x1, y1, x2, y2], outline=color, width=stroke)
        label = f"{i} {item.get('name', '?')}"
        draw.text((x1 + stroke, y1 + stroke), label, fill=color)
    return img


def run(paths: list[Path], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        mime = MIME_BY_SUFFIX.get(path.suffix.lower())
        if mime is None:
            print(f"skipping {path.name}: unsupported extension")
            continue
        print(f"{path.name}:")
        image_bytes, mime = ensure_under_limit(path.read_bytes(), mime)
        # Don't trust the extension-derived mime: sniff the actual format from
        # the bytes we're about to send (a mismatch is a vision-API 400).
        img = Image.open(io.BytesIO(image_bytes))
        mime = Image.MIME.get(img.format, mime)
        # Pre-shrink below the API's internal resize limits so the model's
        # coordinate frame is pixel-identical to the bytes we annotate.
        image_bytes, mime = fit_to_vision_limits(image_bytes, mime)
        width, height = Image.open(io.BytesIO(image_bytes)).size
        items = ask_for_boxes(image_bytes, mime, width, height)
        if not items:
            print("    no items returned")
            continue
        for i, item in enumerate(items):
            print(
                f"    [{i}] {item.get('name', '?')} ({item.get('type', '?')}) "
                f"bbox={item.get('bbox')}"
            )
        annotated = annotate(image_bytes, items)
        out_path = out_dir / f"{path.stem}_annotated.jpg"
        annotated.save(out_path, "JPEG", quality=90)
        print(f"    -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("photos", nargs="+", type=Path, help="photo files to annotate")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("bbox_annotated"),
        help="output directory for annotated copies (default: ./bbox_annotated)",
    )
    args = parser.parse_args()
    run(args.photos, args.out)
