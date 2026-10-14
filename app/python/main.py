"""PGAS App Lab entry point (runs in the app's Python container on the UNO Q).

Start it from the board with:  arduino-app-cli app start user:pgas
Then drive it with:            python3 -m pgas.capture ...   (see README)
"""

from arduino.app_utils import App, Bridge

from pgas.board import Runtime

runtime = Runtime(bridge=Bridge)
Bridge.provide("pgas_sample", runtime.on_sample)
runtime.resume_if_needed()
print("PGAS ready: waiting for jobs in data/jobs/pending", flush=True)

App.run(user_loop=runtime.loop)
