"""Read explicitly timed scene clips from an edu-video HyperFrames root."""
from html.parser import HTMLParser
from math import isfinite
from pathlib import Path


class SceneClips(HTMLParser):
    def __init__(self):
        super().__init__()
        self.clips = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        src = a.get("data-composition-src") or ""
        sid = a.get("data-composition-id")
        if not sid or src != f"compositions/{sid}.html":
            return
        try:
            start, duration = float(a["data-start"]), float(a["data-duration"])
        except (KeyError, TypeError, ValueError):
            return
        if isfinite(start) and isfinite(duration) and start >= 0 and duration > 0:
            self.clips.append({"id": sid, "start": start, "duration": duration})


def scene_timeline(project: Path) -> list[dict]:
    root = project / "index.html"
    if not root.is_file():
        return []
    parser = SceneClips()
    parser.feed(root.read_text(encoding="utf-8"))
    return sorted(parser.clips, key=lambda row: row["start"])
