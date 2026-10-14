"""Push advice to the vendor's phone via Telegram (optional).

PGAS works fully offline; Telegram is a convenience when the stall has a
connection. Without credentials, or when sending fails, the message is
appended to data/outbox.jsonl instead and nothing else is affected.

    PGAS_TELEGRAM_TOKEN    bot token from @BotFather
    PGAS_TELEGRAM_CHAT_ID  chat id to send to
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from . import config

OUTBOX = config.REPO_ROOT / "data" / "outbox.jsonl"


def _queue(text: str, reason: str, outbox: Path) -> dict:
    outbox.parent.mkdir(parents=True, exist_ok=True)
    rec = {"time": datetime.now().isoformat(timespec="seconds"), "text": text, "sent": False, "reason": reason}
    with open(outbox, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def send(text: str, outbox: Path = OUTBOX, timeout_s: float = 5.0) -> dict:
    token = os.environ.get("PGAS_TELEGRAM_TOKEN")
    chat = os.environ.get("PGAS_TELEGRAM_CHAT_ID")
    if not token or not chat:
        return _queue(text, "telegram not configured (stub)", outbox)
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                                    timeout=timeout_s) as r:
            ok = json.loads(r.read()).get("ok", False)
        if ok:
            return {"time": datetime.now().isoformat(timespec="seconds"), "text": text, "sent": True}
        return _queue(text, "telegram returned ok=false", outbox)
    except Exception as e:  # noqa: BLE001 - offline is normal
        return _queue(text, f"send failed: {type(e).__name__}", outbox)
