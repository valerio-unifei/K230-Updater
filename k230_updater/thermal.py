"""Thermal governor: throttles capture FPS (and optionally power) to stay
below a maximum temperature.

Usage in the capture loop:

    gov = Thermal(max_temp=75, target_fps=30, feed=guard.feed)
    while True:
        img = sensor.snapshot()
        ...inference...
        gov.pace()          # sleeps to hold the current FPS, adapts to temperature
"""
import time


def _default_reader():
    # The K230 temperature API differs between CanMV firmware builds, so try
    # known candidates and otherwise ask the user to pass `read=`.
    try:
        import machine
        if hasattr(machine, "temperature"):
            return machine.temperature
    except ImportError:
        pass
    try:
        from machine import TSENSOR
        ts = TSENSOR()
        return ts.read
    except Exception:
        pass
    raise RuntimeError("no temperature sensor found; pass read=callable returning deg C")


class Thermal:
    def __init__(self, max_temp, target_fps, min_fps=1, hysteresis=3,
                 critical_margin=5, interval_ms=2000, read=None, feed=None,
                 on_throttle=None):
        """
        max_temp: never exceed (deg C). FPS is reduced at/above it.
        hysteresis: FPS is raised again only below max_temp - hysteresis.
        critical_margin: at max_temp + margin, capture pauses until cooled.
        on_throttle(level): optional hook, level 0=normal, 1=throttled,
            2=paused. Use it to lower CPU/KPU frequency or disable peripherals.
        feed: watchdog feed callback, called while paused.
        """
        self.max_temp = max_temp
        self.target_fps = target_fps
        self.min_fps = min_fps
        self.hysteresis = hysteresis
        self.critical_margin = critical_margin
        self.interval_ms = interval_ms
        self._read = read or _default_reader()
        self._feed = feed or (lambda: None)
        self._hook = on_throttle
        self.fps = float(target_fps)
        self.temp = None
        self.level = 0
        self._last_check = time.ticks_ms()
        self._frame_start = time.ticks_ms()

    def _set_level(self, level):
        if level != self.level:
            self.level = level
            if self._hook:
                self._hook(level)

    def update(self):
        """Read temperature and adjust FPS. Normally called by pace()."""
        t = self._read()
        self.temp = t
        if t >= self.max_temp + self.critical_margin:
            self._set_level(2)
            while t > self.max_temp - self.hysteresis:
                self._feed()
                time.sleep_ms(1000)
                t = self._read()
            self.temp = t
            self.fps = float(self.min_fps)
        elif t >= self.max_temp:
            self.fps = max(float(self.min_fps), self.fps * 0.7)
        elif t <= self.max_temp - self.hysteresis:
            self.fps = min(float(self.target_fps), self.fps * 1.15 + 0.1)
        self._set_level(0 if self.fps >= self.target_fps else 1)

    def pace(self):
        """Call once per frame, after processing it."""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_check) >= self.interval_ms:
            self._last_check = now
            self.update()
        period = int(1000 / self.fps)
        elapsed = time.ticks_diff(time.ticks_ms(), self._frame_start)
        if elapsed < period:
            time.sleep_ms(period - elapsed)
        self._frame_start = time.ticks_ms()
        self._feed()
