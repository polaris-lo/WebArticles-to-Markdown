from __future__ import annotations
import re
import unicodedata


def slugify(text: str, max_length: int = 60) -> str:
    """Convert a title or URL fragment to a safe filename slug."""
    # Normalise unicode (keep CJK characters as-is)
    text = unicodedata.normalize("NFC", text)
    # Replace separators with hyphen
    text = re.sub(r"[\s/\\|]+", "-", text)
    # Remove characters that are unsafe in filenames
    text = re.sub(r'[<>:"\'\?\*\x00-\x1f]', "", text)
    # Collapse multiple hyphens
    text = re.sub(r"-{2,}", "-", text)
    text = text.strip("-")
    return text[:max_length] if text else "untitled"
