from .guard import Guard
from .thermal import Thermal
from .updater import Updater, UpdateError

# Set by the launcher so the downloaded app can do: `from k230_updater import guard`
guard = None


def set_guard(g):
    global guard
    guard = g
