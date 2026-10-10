"""Ollama vision client used by the camera-analysis tool."""

import base64
import json
import os
from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from PIL import Image


load_dotenv(".env.local", override=True)

SYSTEM_INSTRUCTIONS = """
Return points of interest as a JSON array with labels. Do not return markdown,
code fencing, masks, or any explanation outside the JSON array. Limit the
result to 25 objects. Coordinates must be integers in the 0-1000 range and
use [y, x] order, where (0, 0) is the top-left corner of the image.

If an object is present multiple times, identify each one with a unique
characteristic such as color, size, position, or another visible feature.
If the requested object is not visible, return an empty array.

Example:
[{"point": [527, 508], "label": "yellow lamp"}]
""".strip()


def _api_url() -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    if not base_url.endswith("/v1"):
        base_url += "/v1"
    return f"{base_url}/chat/completions"


def _image_data_url(image: Image.Image) -> str:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _response_text(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Ollama returned an unexpected response: {payload!r}") from exc

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        return "".join(text_parts)
    raise RuntimeError(f"Ollama returned non-text content: {content!r}")


def analyze_camera_image(prompt: str, image: Image.Image) -> str:
    """Ask the configured Ollama vision model to analyze one camera frame."""
    model = os.getenv("OLLAMA_MODEL", "qwen3-vl:4b").strip()
    if not model:
        raise ValueError("OLLAMA_MODEL must name an installed vision model.")

    request_payload = {
        "model": model,
        "stream": False,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _image_data_url(image)}},
                ],
            },
        ],
    }

    request = Request(
        _api_url(),
        data=json.dumps(request_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    timeout = float(os.getenv("OLLAMA_VISION_TIMEOUT", "120"))
    try:
        with urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama vision request failed ({exc.code}): {details}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not connect to Ollama at {_api_url()}: {exc.reason}") from exc

    return _response_text(response_payload)
