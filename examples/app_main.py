# Example of the app that lives in the private repo as main.py.
import time
import k230_updater
from k230_updater import Thermal

guard = k230_updater.guard
gov = Thermal(max_temp=75, target_fps=30, min_fps=2, feed=guard.feed)

last_update_check = time.time()
while True:
    # img = sensor.snapshot(); results = run_kmodel(img)  # your pipeline
    gov.pace()  # holds FPS, throttles on heat, feeds the watchdog
    if time.time() - last_update_check > 3600:
        last_update_check = time.time()
        guard.update_and_reset()
