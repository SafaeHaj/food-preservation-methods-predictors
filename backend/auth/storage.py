"""
Avatar file storage.

Uploads are never trusted: the bytes are decoded by Pillow (which fails on
anything that isn't a real image regardless of extension or declared MIME
type), stripped of metadata by re-encoding, downscaled, and written under a
server-generated UUID filename. The client's filename is discarded entirely,
so it can't influence the path.
"""
from __future__ import annotations

import uuid
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from backend.db import AVATAR_DIR

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
AVATAR_PX = 512  # square, enough for retina at every size the UI renders


class AvatarError(ValueError):
    """Raised for user-fixable upload problems; the message is shown in the UI."""


def save_avatar(raw: bytes) -> str:
    """Validate, normalize and persist an avatar. Returns the stored filename."""
    if not raw:
        raise AvatarError("The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise AvatarError("Image must be 5 MB or smaller.")

    try:
        image = Image.open(BytesIO(raw))
        image.verify()  # cheap structural check; consumes the file object
        image = Image.open(BytesIO(raw))  # reopen -- verify() leaves it unusable
    except (UnidentifiedImageError, OSError) as exc:
        raise AvatarError("That file isn't a readable image.") from exc

    # Flatten transparency onto white so WebP output is predictable, then crop
    # to a centered square before resizing (avoids distorting non-square input).
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        flat = Image.new("RGB", image.size, (255, 255, 255))
        flat.paste(image, mask=image.split()[-1])
        image = flat
    else:
        image = image.convert("RGB")

    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize((AVATAR_PX, AVATAR_PX), Image.LANCZOS)

    filename = f"{uuid.uuid4().hex}.webp"
    image.save(AVATAR_DIR / filename, format="WEBP", quality=88, method=5)
    return filename


def delete_avatar(filename: str | None) -> None:
    """Remove a stored avatar, ignoring anything that isn't a plain filename
    inside AVATAR_DIR (defensive against a malformed stored value)."""
    if not filename:
        return
    path = (AVATAR_DIR / filename).resolve()
    if path.parent != AVATAR_DIR.resolve() or not path.is_file():
        return
    try:
        path.unlink()
    except OSError:
        pass
