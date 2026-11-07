"""Build an explicit deployment file list without databases or local secrets."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "app.py", "requirements.txt", ".python-version", "vercel.json",
    "backend/requirements.txt", "frontend/package.json", "frontend/pnpm-lock.yaml",
    "frontend/pnpm-workspace.yaml", "frontend/.npmrc", "frontend/index.html",
    "frontend/tsconfig.json", "frontend/vite.config.ts",
]
FILES += [str(p.relative_to(ROOT)).replace("\\", "/") for pattern in ["backend/app/*.py", "frontend/src/*"] for p in ROOT.glob(pattern) if p.is_file()]


def package():
    files = []
    digest = hashlib.sha256()
    for name in sorted(set(FILES)):
        raw = (ROOT / name).read_bytes()
        content = raw.decode("utf-8-sig")
        files.append({"file": name, "data": content, "encoding": "utf-8"})
        digest.update(name.encode() + b"\0" + raw + b"\0")
    return {"files": files, "sha256": digest.hexdigest()}


if __name__ == "__main__":
    result = package()
    payload = json.dumps(result, ensure_ascii=True)
    if "--metadata" in sys.argv:
        print(json.dumps({"sha256": result["sha256"], "files": len(result["files"]), "chunks": (len(payload) + 9999) // 10000}))
    elif "--file" in sys.argv:
        name = sys.argv[sys.argv.index("--file") + 1]
        print(json.dumps(next(f for f in result["files"] if f["file"] == name)))
    elif "--chunk" in sys.argv:
        start = int(sys.argv[sys.argv.index("--chunk") + 1]) * 10000
        print(json.dumps(payload[start:start + 10000]))
    else:
        print(payload)
