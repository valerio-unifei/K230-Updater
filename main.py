# Permanent launcher: copy to /sdcard/main.py (with the k230_updater folder
# and config.json next to it). It is never updated remotely.
import json
import k230_updater
from k230_updater import Guard


def connect():
    import network
    import time
    nic = network.LAN()  # or network.WLAN(network.STA_IF) for Wi-Fi
    nic.active(True)
    if not nic.isconnected():
        # Wi-Fi: nic.connect("SSID", "PASSWORD")
        pass
    for _ in range(30):
        if nic.isconnected():
            return
        time.sleep(1)
    raise OSError("no network")


with open("/sdcard/config.json") as f:
    cfg = json.load(f)

g = Guard(cfg.get("repo"), cfg.get("token"), branch=cfg.get("branch", "main"),
          wdt_timeout=cfg.get("wdt_timeout", 10),
          max_fails=cfg.get("max_fails", 3),
          confirm_after=cfg.get("confirm_after", 60),
          connect=connect,
          update_url=cfg.get("update_url"))
k230_updater.set_guard(g)
g.boot()
