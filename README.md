# K230-Updater
MicroPython library for CanMV K230: remote updates from a private GitHub repo (main + `.kmodel` files), a hardware-watchdog safeguard with rollback and fix-forward updates, and thermal throttling of capture FPS.

Full documentation (Portuguese): [docs/DOCUMENTACAO.md](docs/DOCUMENTACAO.md)

HTTP zip updates (`update_url`: `GET ?chipid=..&last_update=..`) and a segmentation example (`examples/segmentation_app`, `examples/server.py`) are described there.

## SD card layout
```
/sdcard/main.py          launcher (this repo's main.py, never updated remotely)
/sdcard/config.json      copy of config.example.json (keep the token secret)
/sdcard/k230_updater/    this library
/sdcard/app/current|previous|state.json   managed automatically
```

## Private repo layout
`manifest.json` + files. `entry` defaults to `main.py`; models are listed like any file:
```json
{"version": "1.0.1", "entry": "main.py",
 "files": [{"path": "main.py", "sha256": "<hex>"},
           {"path": "models/det.kmodel", "sha256": "<hex>"}]}
```
Bump `version` on every release; each file's sha256 is verified. See `examples/app_main.py`.

## Safeguard
- Hardware WDT (`machine.WDT`) is fed only by the app via `guard.feed()` (or `Thermal.pace()`): a hang triggers a reset.
- A version is "trial" until it feeds the WDT for `confirm_after` seconds; a crash/reset before that counts as a failure.
- After `max_fails` failures the version is blacklisted and the previous one restored.
- On every boot (and via `guard.update_and_reset()`) a new, non-blacklisted version is installed, so publishing a fixed release with a new `version` recovers the device.

## Thermal control
`Thermal(max_temp, target_fps, ...)`: call `pace()` each frame. It lowers FPS at `max_temp`, pauses at `max_temp + critical_margin`, recovers with hysteresis. `on_throttle(level)` is a hook to also lower CPU/KPU frequency.

## Notes
Not tested on hardware. The temperature API varies by CanMV firmware: if auto-detection fails, pass `read=` returning °C. Verify `WDT(id, timeout)` (seconds) and `requests` HTTPS support on your firmware.

Gestor de atualizações remotas para a placa CanMV K230.
