import json
import time
from datetime import datetime, timezone
from pathlib import Path

import redis

from .config import ARTIFACT_DIR, REDIS_URL


def main():
    client = redis.from_url(REDIS_URL, decode_responses=True)
    heartbeat = Path(ARTIFACT_DIR) / "worker-heartbeat"
    heartbeat.parent.mkdir(parents=True, exist_ok=True)
    while True:
        now = datetime.now(timezone.utc).isoformat()
        heartbeat.write_text(now, encoding="utf-8")
        client.set("clinic:worker:heartbeat", json.dumps({"at": now, "service": "wait-distribution-worker"}), ex=45)
        time.sleep(5)


if __name__ == "__main__":
    main()
