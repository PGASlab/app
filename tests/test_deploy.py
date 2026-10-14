"""Run scripts/deploy.sh against a fake board (fake ssh + arduino-app-cli),
then start the deployed main.py with a fake arduino.app_utils module and
drive a hood capture through the real CLI on the deployed copy."""

import os
import shutil
import subprocess
import sys
import textwrap
import time

import pytest

from pgas import config

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("tar") is None,
                                reason="needs bash and tar")


def _fake_bin(tmp_path):
    b = tmp_path / "bin"
    b.mkdir()
    (b / "ssh").write_text('#!/bin/sh\nshift\nexec sh -c "$1"\n')
    (b / "arduino-app-cli").write_text('#!/bin/sh\necho "arduino-app-cli $*" >> "$FAKE_LOG"\n')
    for f in b.iterdir():
        f.chmod(0o755)
    return b


FAKE_APP_UTILS = textwrap.dedent('''
    import threading, time, random
    class _Bridge:
        handlers = {}
        drawn = []
        def provide(self, name, fn): self.handlers[name] = fn
        def call(self, name, *args, timeout=10): self.drawn.append(args[0])
        def notify(self, *a): pass
    Bridge = _Bridge()
    class App:
        @staticmethod
        def run(user_loop=None):
            def mcu():
                i = 0
                while True:
                    k = 600 if 35 <= i < 95 else 0
                    Bridge.handlers["pgas_sample"](3000 + k, 2500 + k, 2800 + k, 25.0, 60.0, 1)
                    i += 1
                    time.sleep(0.01)  # 100x faster than the real 1 Hz
            threading.Thread(target=mcu, daemon=True).start()
            while True:
                user_loop()
''')


def test_deploy_and_run_on_fake_board(tmp_path):
    app_dir = tmp_path / "ArduinoApps" / "pgas"
    env = dict(os.environ, PATH=f"{_fake_bin(tmp_path)}:{os.environ['PATH']}",
               PGAS_APP_DIR=str(app_dir), FAKE_LOG=str(tmp_path / "cli.log"))
    out = subprocess.run(["bash", str(config.REPO_ROOT / "scripts" / "deploy.sh"), "fake.local", "--boot"],
                         env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    for rel in ("app.yaml", "sketch/sketch.ino", "sketch/sketch.yaml", "python/main.py",
                "python/requirements.txt", "python/pgas/capture.py", "data/jobs/pending"):
        assert (app_dir / rel).exists(), rel
    assert not list(app_dir.rglob("__pycache__"))
    log = (tmp_path / "cli.log").read_text()
    assert "app start user:pgas" in log and "properties set default user:pgas" in log

    # Start the deployed app with a fake Bridge (fast clock).
    fake = tmp_path / "fake_site" / "arduino"
    fake.mkdir(parents=True)
    (fake / "__init__.py").write_text("")
    (fake / "app_utils.py").write_text(FAKE_APP_UTILS)
    py = dict(os.environ, PYTHONPATH=str(tmp_path / "fake_site"))
    proc = subprocess.Popen([sys.executable, "main.py"], cwd=app_dir / "python", env=py,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        cli = subprocess.run([sys.executable, "-m", "pgas.capture", "--mode", "hood", "--label", "fresh_test",
                              "--no-llm"], cwd=app_dir / "python", env=dict(os.environ),
                             capture_output=True, text=True, timeout=60)
    finally:
        proc.kill()
        proc.wait()
    assert cli.returncode == 0, cli.stdout + cli.stderr
    assert "STEP 1/3" in cli.stdout and "MOVE NOW" in cli.stdout and "STEP 3/3" in cli.stdout
    csvs = list((app_dir / "data" / "raw").glob("*_hood_fresh_test.csv"))
    assert len(csvs) == 1
