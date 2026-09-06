from pathlib import Path
import base64
import json
import zlib

parts = sorted(Path(".github/scripts").glob("acoustic-round2.part*"))
if not parts:
    raise SystemExit("acoustic round-2 payload is missing")

payload = "".join(part.read_text() for part in parts)
files = json.loads(zlib.decompress(base64.b64decode(payload)).decode())
for target_path, content in files.items():
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
