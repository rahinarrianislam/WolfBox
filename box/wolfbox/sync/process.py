import hashlib
import os
import shutil
import time
from contextvars import ContextVar
from pathlib import PurePosixPath

from wolfbox import gemma
from wolfbox.store import now_iso

from .extract import extract_text


# Job-wide Gemma budget: a slow model must not keep a sync "running" for minutes.
_llm_deadline = ContextVar("sync_llm_deadline", default=None)


def start_llm_budget():
    _llm_deadline.set(time.monotonic() + float(os.environ.get("SYNC_LLM_BUDGET", "45")))


def _llm(fn, *args):
    deadline = _llm_deadline.get()
    if deadline is not None and time.monotonic() > deadline:
        return None
    try:
        return fn(*args)
    except Exception:
        return None


def process_item(store, course, item, fetcher):
    doc_id = f"{course}/{item['id']}"
    rel = f"courses/{course}/docs/{item['id']}"
    old = store.read_json(f"{rel}/meta.json")
    files, texts = [], []
    for entry in item["files"]:
        content = fetcher(entry["resolved_url"])
        if isinstance(content, str):
            content = content.encode()
        path = entry.get("path") or PurePosixPath(entry["resolved_url"]).name
        files.append((path, content, entry.get("role")))
        extracted = extract_text(path, content)
        if extracted:
            texts.append(f"## {path}\n\n{extracted}")
    digest = hashlib.sha256()
    for path, content, _ in sorted(files):
        digest.update(path.encode() + b"\0" + content)
    sha = digest.hexdigest()
    if old and old.get("sha256") == sha:
        return "unchanged", old

    previous_text = store.read_text(f"{rel}/text.md", "") or ""
    if old:
        prev = store.path(f"{rel}/prev/{old.get('version', 1)}")
        if prev.exists():
            shutil.rmtree(prev)
        prev.mkdir(parents=True, exist_ok=True)
        for path in store.path(f"{rel}/files").glob("**/*"):
            if path.is_file():
                target = prev / path.relative_to(store.path(f"{rel}/files"))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)

    current_files = store.path(f"{rel}/files")
    if current_files.exists():
        shutil.rmtree(current_files)
    for path, content, _ in files:
        target = store.path(f"{rel}/files/{path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    text = "\n\n".join(texts)
    store.write_text(f"{rel}/text.md", text)
    title = item.get("title", item["id"])
    # Most demo-visible first: the "what changed" note, then the summary.
    change_note = _llm(gemma.change_note, title, previous_text, text) if old else None
    summary = _llm(gemma.summarize_doc, title, text)
    if item.get("due"):
        # The manifest due date wins anyway, so skip the model call.
        deadlines = [{"what": f"{title} due", "due": item["due"]}]
    else:
        deadlines = _llm(gemma.extract_deadlines, title, text, None) or []

    workspace = None
    if any(role == "tests" for _, _, role in files):
        workspace = f"repo/{item['id']}"
        root = store.path(workspace)
        root.mkdir(parents=True, exist_ok=True)
        starter_name = None
        for path, content, role in files:
            name = PurePosixPath(path).name
            if name == "README.md" or role == "tests":
                (root / name).write_bytes(content)
            elif role == "starter":
                starter_name = name
                starter = root / name
                if not starter.exists():
                    starter.write_bytes(content)
                elif old:
                    prior = store.path(f"{rel}/prev/{old.get('version', 1)}/{path}")
                    if prior.exists() and starter.read_bytes() != prior.read_bytes() and starter.read_bytes() != content:
                        (root / f"{name}.new").write_bytes(content)
                    else:
                        (root / f"{name}.new").unlink(missing_ok=True)
        if old and starter_name and (root / f"{starter_name}.new").exists():
            workspace_note = f"Updated starter saved as {starter_name}.new; your {starter_name} was preserved."
        else:
            workspace_note = None
    else:
        workspace_note = None

    meta = {
        "doc_id": doc_id, "course": course, "item_id": item["id"], "type": item.get("type", "doc"),
        "title": item.get("title", item["id"]), "version": item.get("version", 1), "sha256": sha,
        "fetched_at": now_iso(), "summary": summary, "change_note": change_note,
        "deadlines": deadlines, "due": item.get("due"), "workspace": workspace,
    }
    try:
        meta["llm"] = gemma.last_llm()
    except Exception:
        meta["llm"] = None
    if workspace_note:
        meta["workspace_note"] = workspace_note
    store.write_json(f"{rel}/meta.json", meta)
    return ("changed" if old else "new"), meta
