"""PGAS App Lab entry point (runs in the app's Python container on the UNO Q).

Start it from the board with:  arduino-app-cli app start user:pgas
Then drive it with:            python3 -m pgas.capture ...   (see README)
Live dashboard (same Wi-Fi):   http://<board-name>.local:7000
"""

from arduino.app_utils import App, Bridge

from pgas.board import Runtime
from pgas.web import LiveFeed

# Wi-Fi dashboard: the arduino:web_ui brick serves ../assets on port 7000 and
# pushes Socket.IO messages. PGAS keeps working without it.
feed = None
try:
    from arduino.app_bricks.web_ui import WebUI

    ui = WebUI()
    feed = LiveFeed(ui)
    ui.on_connect(feed.on_connect)
except Exception as e:  # noqa: BLE001 - brick missing or failed to start
    print(f"dashboard disabled: {e}", flush=True)

runtime = Runtime(bridge=Bridge, feed=feed)
Bridge.provide("pgas_sample", runtime.on_sample)
runtime.resume_if_needed()
print("PGAS ready: waiting for jobs in data/jobs/pending", flush=True)
if feed is not None:
    print("dashboard: http://<board-name>.local:7000", flush=True)

App.run(user_loop=runtime.loop)
