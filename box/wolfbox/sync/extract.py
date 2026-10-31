import re
from html.parser import HTMLParser
from pathlib import PurePosixPath

from pypdf import PdfReader


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def extract_text(path, data):
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".pdf":
        import io

        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages).strip()
    text = data.decode("utf-8", errors="replace")
    if suffix in (".html", ".htm"):
        parser = _Text()
        parser.feed(text)
        text = " ".join(parser.parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
