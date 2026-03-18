from __future__ import annotations
import logging
import os
import re

from converter.utils.slug import slugify

logger = logging.getLogger(__name__)


def assemble(frontmatter_block: str, body_md: str) -> str:
    """Combine YAML frontmatter and Markdown body into a single string."""
    return frontmatter_block + "\n" + body_md.strip() + "\n"


def _title_from_content(content: str) -> str:
    """Extract the first H1 heading from the markdown body (skips YAML frontmatter)."""
    in_frontmatter = False
    for line in content.splitlines():
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        m = re.match(r"^#\s+(.+)", line)
        if m:
            return m.group(1).strip()
    return ""


def write(content: str, output_dir: str, extracted: dict) -> str:
    """Write the final Markdown to a file. Returns the file path."""
    os.makedirs(output_dir, exist_ok=True)

    title = extracted.get("title") or ""
    if not title or title.lower() == "untitled":
        title = _title_from_content(content) or "untitled"
    slug = slugify(title)
    filename = f"{slug}.md"
    filepath = os.path.join(output_dir, filename)

    # Avoid overwriting: append a counter if the file exists
    if os.path.exists(filepath):
        base, ext = os.path.splitext(filepath)
        counter = 1
        while os.path.exists(f"{base}-{counter}{ext}"):
            counter += 1
        filepath = f"{base}-{counter}{ext}"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Saved: %s", filepath)
    return filepath
