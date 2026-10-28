import json
import os
from pathlib import Path

MAX_LINE = 256 * 1024
LEVELS = ("TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL")


def level_of(text):
    if text.startswith("{"):
        try:
            value = json.loads(text).get("level", "")
            if isinstance(value, str):
                normalized = value.upper().replace("WARNING", "WARN").replace("CRITICAL", "FATAL")
                if normalized in LEVELS:
                    return normalized
        except (ValueError, AttributeError):
            pass
    upper = text.upper()
    for level in reversed(LEVELS):
        if level in upper or (level == "WARN" and "WARNING" in upper):
            return level
    return "—"


def lines(path):
    with open(path, "rb") as file:
        number = 0
        while True:
            chunk = file.readline(MAX_LINE + 1)
            if not chunk:
                return
            number += 1
            if len(chunk) > MAX_LINE and not chunk.endswith(b"\n"):
                while chunk and not chunk.endswith(b"\n"):
                    chunk = file.readline(MAX_LINE + 1)
                yield number, None
            else:
                yield (
                    number,
                    chunk.decode("utf-8-sig" if number == 1 else "utf-8", errors="replace").rstrip(
                        "\r\n"
                    ),
                )


def search(path, query="", level="TODOS", case_sensitive=False, limit=2000, cancel=None):
    if not 1 <= limit <= 10000:
        raise ValueError("Límite de resultados inválido.")
    needle = query if case_sensitive else query.casefold()
    result = []
    scanned, skipped = 0, 0
    for number, text in lines(path):
        if cancel and cancel.is_set():
            return {
                "rows": result,
                "scanned": scanned,
                "skipped": skipped,
                "cancelled": True,
                "limited": False,
            }
        scanned = number
        if text is None:
            skipped += 1
            continue
        severity = level_of(text)
        haystack = text if case_sensitive else text.casefold()
        if needle in haystack and (level == "TODOS" or severity == level):
            result.append((number, severity, text))
            if len(result) >= limit:
                return {
                    "rows": result,
                    "scanned": scanned,
                    "skipped": skipped,
                    "cancelled": False,
                    "limited": True,
                }
    return {
        "rows": result,
        "scanned": scanned,
        "skipped": skipped,
        "cancelled": False,
        "limited": False,
    }


class Tail:
    def __init__(self, path):
        self.path = Path(path)
        stat = self.path.stat()
        self.identity = (stat.st_dev, stat.st_ino)
        self.offset = stat.st_size
        self.pending = b""

    def read(self):
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        reset = identity != self.identity or stat.st_size < self.offset
        if reset:
            self.offset = 0
            self.pending = b""
            self.identity = identity
        with self.path.open("rb") as file:
            file.seek(self.offset)
            data = file.read(1024 * 1024)
            self.offset = file.tell()
        chunks = (self.pending + data).split(b"\n")
        self.pending = chunks.pop()
        if len(self.pending) > MAX_LINE:
            self.pending = b"[linea demasiado larga omitida]"
        return reset, [
            chunk[:MAX_LINE].decode("utf-8", errors="replace").rstrip("\r") for chunk in chunks
        ]


class Filters:
    def __init__(self, path):
        self.path = Path(path)

    def all(self):
        if not self.path.exists():
            return {}
        result = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError("El archivo de filtros no es válido.")
        return result

    def save(self, name, query, level, case):
        if not name.strip() or len(name) > 80:
            raise ValueError("Escribe un nombre de hasta 80 caracteres.")
        result = self.all()
        result[name.strip()] = {"query": query, "level": level, "case": bool(case)}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
