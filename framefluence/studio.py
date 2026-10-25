"""
Framefluence Studio - local web UI for the autopilot pipeline.

    python -m framefluence studio     # then open http://127.0.0.1:8765

Standard library only, bound to localhost. It serves ui/index.html and a small JSON API:
upload clips to inbox/, run the autopilot or a restyle as a background job (one at a time -
renders are memory-hungry), browse drafts with seekable video, edit hooks, approve/reject.
"""

import argparse
import datetime
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from framefluence.paths import FONTS, INBOX, LOGS, ROOT, UI as UI_DIR
STATUS_DIRS = {"pending": "review", "approved": "approved", "rejected": "rejected"}
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".m4v")
EDITABLE = ("hook", "header", "hashtags", "caption_style", "question", "context")
FLAGS = ("show_hook", "show_header")  # on-video hook box / show title; off unless chosen
DRAFT_NAME = re.compile(r"^[\w.-]+$")


def pipeline_python():
    """The venv interpreter has the smart-step packages; fall back to whatever runs this server."""
    venv = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    return venv if os.path.exists(venv) else sys.executable


# ---------------------------------------------------------------- drafts

def draft_dir(status, name):
    """Resolves a draft folder, refusing anything that could escape the status folder."""
    if status not in STATUS_DIRS or not DRAFT_NAME.match(name or ""):
        return None
    path = os.path.join(ROOT, STATUS_DIRS[status], name)
    return path if os.path.isfile(os.path.join(path, "reel.mp4")) else None


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def list_drafts():
    drafts = []
    for status, folder in STATUS_DIRS.items():
        base = os.path.join(ROOT, folder)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base), reverse=True):
            path = draft_dir(status, name)
            if not path:
                continue
            meta = read_json(os.path.join(path, "meta.json"), {})
            start, end = meta.get("segment", [0, 0])
            caption = ""
            if os.path.exists(os.path.join(path, "caption.txt")):
                with open(os.path.join(path, "caption.txt"), encoding="utf-8") as f:
                    caption = f.read()
            drafts.append({
                "name": name, "status": status, "title": meta.get("title", name),
                "hook": meta.get("hook", ""), "header": meta.get("header", ""),
                "hashtags": meta.get("hashtags", ""), "caption_style": meta.get("caption_style", "bold"),
                "question": meta.get("question", ""), "context": meta.get("context", ""),
                "pick": meta.get("pick"), "duration": round(end - start, 1), "segment": [start, end],
                "framing": meta.get("framing"), "subtitles": meta.get("subtitles", False),
                "source": meta.get("source", ""), "created": meta.get("created", ""),
                "show_hook": bool(meta.get("show_hook")), "show_header": bool(meta.get("show_header")),
                "caption": caption, "restylable": os.path.exists(os.path.join(path, "source_cut.mp4")),
            })
    return drafts


def transcript(path):
    words = read_json(os.path.join(path, "words.json"), [])
    return " ".join(w["word"] for w in words)


def move_draft(status, name, new_status):
    src = draft_dir(status, name)
    if not src or new_status not in STATUS_DIRS:
        raise ValueError("unknown draft or status")
    meta_path = os.path.join(src, "meta.json")
    meta = read_json(meta_path, {})
    meta["status"] = "pending_review" if new_status == "pending" else new_status
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    dest = os.path.join(ROOT, STATUS_DIRS[new_status])
    os.makedirs(dest, exist_ok=True)
    shutil.move(src, os.path.join(dest, name))


def update_meta(status, name, fields):
    path = draft_dir(status, name)
    if not path:
        raise ValueError("unknown draft")
    meta_path = os.path.join(path, "meta.json")
    meta = read_json(meta_path, {})
    meta.update({k: str(v).strip() for k, v in fields.items() if k in EDITABLE})
    meta.update({k: bool(fields[k]) for k in FLAGS if k in fields})
    if meta.get("caption_style") not in ("bold", "clean"):
        meta["caption_style"] = "bold"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return path


def thumbnail(path):
    """First-frame-ish poster (1s in), generated once per draft and cached next to the reel."""
    thumb = os.path.join(path, "thumb.jpg")
    reel = os.path.join(path, "reel.mp4")
    if not os.path.exists(thumb) or os.path.getmtime(thumb) < os.path.getmtime(reel):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", reel, "-frames:v", "1",
                        "-vf", "scale=360:-2", thumb], check=False)
    return thumb if os.path.exists(thumb) else None


# ---------------------------------------------------------------- inbox

def safe_filename(name):
    base, ext = os.path.splitext(os.path.basename(name or "clip.mp4"))
    base = re.sub(r"[^\w-]+", "_", base).strip("_")[:60] or "clip"
    return base + (ext.lower() if ext.lower() in VIDEO_EXTS else ".mp4")


def inbox_items():
    if not os.path.isdir(INBOX):
        return []
    items = []
    for f in sorted(os.listdir(INBOX)):
        if f.lower().endswith(VIDEO_EXTS):
            sidecar = read_json(os.path.join(INBOX, os.path.splitext(f)[0] + ".json"), {})
            items.append({"file": f, "size_mb": round(os.path.getsize(os.path.join(INBOX, f)) / 1e6, 1),
                          "title": sidecar.get("title", ""), "hook": sidecar.get("hook", "")})
    return items


def write_sidecar(filename, fields):
    """clip.json next to the upload; only keys the autopilot understands, empty values dropped."""
    allowed = ("title", "header", "hook", "context", "question", "hashtags", "caption_style")
    sidecar = {k: str(v).strip() for k, v in fields.items() if k in allowed and str(v).strip()}
    for key in ("start", "end"):
        try:
            if str(fields.get(key, "")).strip():
                sidecar[key] = float(fields[key])
        except ValueError:
            pass
    if sidecar:
        with open(os.path.join(INBOX, os.path.splitext(filename)[0] + ".json"), "w", encoding="utf-8") as f:
            json.dump(sidecar, f, indent=2)


# ---------------------------------------------------------------- jobs

class JobRunner:
    """Runs one pipeline subprocess at a time and keeps its output for the UI's progress panel."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.job = {"state": "idle"}
        self.log_path = os.path.join(LOGS, "studio_job.log")

    def start(self, kind, args, label):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                raise RuntimeError("A job is already running. Wait for it to finish.")
            os.makedirs(LOGS, exist_ok=True)
            log = open(self.log_path, "w", encoding="utf-8")
            env = {**os.environ, "HF_HUB_DISABLE_SYMLINKS_WARNING": "1", "PYTHONIOENCODING": "utf-8"}
            self.proc = subprocess.Popen([pipeline_python(), "-m", "framefluence.autopilot", *args], cwd=ROOT,
                                         stdout=log, stderr=subprocess.STDOUT, env=env)
            self.job = {"state": "running", "kind": kind, "label": label,
                        "started": datetime.datetime.now().isoformat(timespec="seconds")}
            threading.Thread(target=self._wait, args=(self.proc, log), daemon=True).start()
            return self.job

    def _wait(self, proc, log):
        code = proc.wait()
        log.close()
        with self.lock:
            self.job.update(state="done" if code == 0 else "failed", exit_code=code,
                            finished=datetime.datetime.now().isoformat(timespec="seconds"))

    def status(self):
        lines = []
        if os.path.exists(self.log_path):
            with open(self.log_path, encoding="utf-8", errors="replace") as f:
                # Keep the pipeline's own progress lines; drop ffmpeg/HTTP noise
                lines = [l.rstrip() for l in f if " INFO " in l or " WARNING " in l or " ERROR " in l
                         or "Traceback" in l or "Error" in l]
        steps = [re.sub(r"^\S+ \S+ (INFO|WARNING|ERROR) ", "", l).strip() for l in lines[-12:]]
        with self.lock:
            return {**self.job, "steps": steps}


JOBS = JobRunner()


def briefing_text():
    from framefluence.trend_agent import get_breaking_trailers, get_peer_trends, get_upcoming_milestones
    ideas = []
    for m in get_upcoming_milestones(days_threshold=21)[:3]:
        ideas.append({"kind": "Birthday", "title": f"{m['actor_name']} turns {m['age_turning']}",
                      "detail": f"in {m['days_left']} days" if m["days_left"] else "today",
                      "hook": m.get("hook", "")})
    for t in get_breaking_trailers(max_items=2):
        ideas.append({"kind": "Trailer", "title": t["title"], "detail": t.get("suggested_format", ""),
                      "hook": t.get("hype_angle", "")})
    for p in get_peer_trends()[:1]:
        ideas.append({"kind": "Trend", "title": p["theme"], "detail": p.get("example_scenes", ""),
                      "hook": p.get("hook", "")})
    return ideas


# ---------------------------------------------------------------- HTTP

def parse_range(header, size):
    """'bytes=START-END' -> (start, end) inclusive, clamped; None when absent or unsatisfiable."""
    m = re.match(r"bytes=(\d*)-(\d*)$", header or "")
    if not m or (not m.group(1) and not m.group(2)):
        return None
    if m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
    else:  # suffix range: last N bytes
        start, end = max(0, size - int(m.group(2))), size - 1
    end = min(end, size - 1)
    return (start, end) if start <= end else None


class Handler(BaseHTTPRequestHandler):
    server_version = "FramefluenceStudio/1.0"

    def log_message(self, fmt, *args):  # quiet console
        pass

    # -- helpers
    def send_json(self, data, code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, code, message):
        self.send_json({"error": message}, code)

    def read_body_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def send_file(self, path, content_type=None):
        size = os.path.getsize(path)
        ctype = content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"
        rng = parse_range(self.headers.get("Range"), size)
        start, end = rng or (0, size - 1)
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-cache")
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            try:
                while remaining > 0:
                    chunk = f.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                pass  # the browser cancels range requests while seeking; that's normal

    # -- routes
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in url.path.strip("/").split("/") if p]
        if not parts:
            return self.send_file(os.path.join(UI_DIR, "index.html"), "text/html; charset=utf-8")
        if parts[0] == "fonts" and len(parts) == 2 and DRAFT_NAME.match(parts[1]):
            font = os.path.join(FONTS, parts[1])
            return self.send_file(font, "font/ttf") if os.path.isfile(font) else self.send_error_json(404, "no font")
        if parts[:2] == ["api", "drafts"] and len(parts) == 2:
            return self.send_json({"drafts": list_drafts()})
        if parts[:2] == ["api", "drafts"] and len(parts) == 5 and parts[4] == "transcript":
            path = draft_dir(parts[2], parts[3])
            return self.send_json({"text": transcript(path)}) if path else self.send_error_json(404, "no draft")
        if parts[:2] == ["api", "inbox"]:
            return self.send_json({"items": inbox_items()})
        if parts[:2] == ["api", "job"]:
            return self.send_json(JOBS.status())
        if parts[:2] == ["api", "ideas"]:
            try:
                return self.send_json({"ideas": briefing_text()})
            except Exception as e:
                return self.send_json({"ideas": [], "error": str(e)})
        if parts[0] == "media" and len(parts) == 4:
            path = draft_dir(parts[1], parts[2])
            if path and parts[3] == "reel.mp4":
                return self.send_file(os.path.join(path, "reel.mp4"), "video/mp4")
            if path and parts[3] == "thumb.jpg":
                thumb = thumbnail(path)
                return self.send_file(thumb, "image/jpeg") if thumb else self.send_error_json(404, "no thumbnail")
            if path and parts[3] == "caption.txt" and os.path.exists(os.path.join(path, "caption.txt")):
                return self.send_file(os.path.join(path, "caption.txt"), "text/plain; charset=utf-8")
        self.send_error_json(404, "not found")

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in url.path.strip("/").split("/") if p]
        try:
            if parts == ["api", "upload"]:
                return self.upload(urllib.parse.parse_qs(url.query))
            if parts == ["api", "run"]:
                body = self.read_body_json()
                args = ["--no-briefing", "--drafts", str(int(body.get("drafts", 3))),
                        "--max-len", str(float(body.get("max_len", 118)))]
                if not inbox_items():
                    return self.send_error_json(400, "The inbox is empty. Add a video first.")
                return self.send_json(JOBS.start("process", args, "Making drafts from the inbox"))
            if len(parts) == 5 and parts[:2] == ["api", "drafts"]:
                status, name, action = parts[2], parts[3], parts[4]
                if action in ("approve", "reject", "restore"):
                    target = {"approve": "approved", "reject": "rejected", "restore": "pending"}[action]
                    move_draft(status, name, target)
                    return self.send_json({"ok": True, "status": target})
                if action == "edit":
                    body = self.read_body_json()
                    path = update_meta(status, name, body)
                    if body.get("render", True):
                        if not os.path.exists(os.path.join(path, "source_cut.mp4")):
                            return self.send_error_json(400, "This draft has no source clip, so it can't be re-rendered.")
                        rel = os.path.relpath(path, ROOT)
                        return self.send_json(JOBS.start("restyle", ["--restyle", rel], f"Re-rendering {name}"))
                    return self.send_json({"ok": True})
            self.send_error_json(404, "not found")
        except RuntimeError as e:
            self.send_error_json(409, str(e))
        except (ValueError, KeyError) as e:
            self.send_error_json(400, str(e))

    def upload(self, query):
        """Raw-body upload (no multipart parsing needed): filename and options arrive in the query."""
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return self.send_error_json(400, "The upload was empty.")
        os.makedirs(INBOX, exist_ok=True)
        filename = safe_filename(query.get("name", ["clip.mp4"])[0])
        dest = os.path.join(INBOX, filename)
        stem, ext = os.path.splitext(filename)
        n = 2
        while os.path.exists(dest):
            filename = f"{stem}_{n}{ext}"
            dest = os.path.join(INBOX, filename)
            n += 1
        remaining = length
        with open(dest + ".part", "wb") as f:
            while remaining > 0:
                chunk = self.rfile.read(min(1 << 20, remaining))
                if not chunk:
                    break
                f.write(chunk)
                remaining -= len(chunk)
        if remaining:
            os.remove(dest + ".part")
            return self.send_error_json(400, "The upload was cut off. Try again.")
        os.replace(dest + ".part", dest)  # only complete files ever appear in the inbox
        write_sidecar(filename, {k: v[0] for k, v in query.items()})
        self.send_json({"ok": True, "file": filename})


def main():
    parser = argparse.ArgumentParser(description="Framefluence Studio (local web UI)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    os.chdir(ROOT)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Framefluence Studio running at http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
