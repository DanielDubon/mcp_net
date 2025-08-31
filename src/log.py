from pathlib import Path
from datetime import datetime
import json

LOG_DIR = Path("logs"); LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "interactions.jsonl"

def jdump(event: dict):
    event = {"ts": datetime.utcnow().isoformat()+"Z", **event}
    LOG_FILE.open("a", encoding="utf-8").write(json.dumps(event, ensure_ascii=False) + "\n")
