"""Generates figs/diagrama_blocos.png (block diagram of k230_updater).
Run: python docs/latex/make_diagram.py   (needs matplotlib)
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs", "diagrama_blocos.png")

fig, ax = plt.subplots(figsize=(15, 10))
ax.set_xlim(0, 150)
ax.set_ylim(0, 100)
ax.axis("off")

COL = {"ext": "#e6e6e6", "core": "#cfe2ff", "safe": "#ffe0b3",
       "app": "#d4f0d4", "therm": "#ffd1d1", "store": "#f0e0ff"}
B = {}


def group(x, y, w, h, title):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1.5",
                                fc="none", ec="#777", lw=1.2, ls="--"))
    ax.text(x + 1.5, y + h - 2.5, title, fontsize=10.5, fontweight="bold", color="#444")


def box(key, x, y, w, h, text, kind, fs=9.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.0",
                                fc=COL[kind], ec="#333", lw=1.4))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)
    B[key] = (x, y, w, h)


def pt(key, side):
    x, y, w, h = B[key]
    return {"l": (x, y + h / 2), "r": (x + w, y + h / 2),
            "t": (x + w / 2, y + h), "b": (x + w / 2, y)}[side]


def arrow(a, sa, b, sb, text=None, rad=0.0, color="#222", off=(0, 0), ls="-"):
    p, q = pt(a, sa), pt(b, sb)
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=15, lw=1.5,
                                 color=color, ls=ls, connectionstyle="arc3,rad=%s" % rad,
                                 shrinkA=2, shrinkB=2))
    if text:
        ax.text((p[0] + q[0]) / 2 + off[0], (p[1] + q[1]) / 2 + off[1], text, fontsize=8.5,
                ha="center", va="center", color=color,
                bbox=dict(fc="white", ec="none", pad=1))


ax.text(75, 97, "k230\\_updater - diagrama em blocos".replace("\\", ""), ha="center",
        fontsize=16, fontweight="bold")

# Row 1: external sources -> updater -> storage
group(1, 66, 34, 28, "Fontes externas")
box("gh", 4, 80, 28, 9, "GitHub privado\n(API contents + token)", "ext")
box("http", 4, 69, 28, 9, "Servidor HTTP\nGET ?chipid&last_update\n-> zip", "ext")

group(42, 66, 58, 28, "Atualizador (updater.py, ziputil.py)")
box("upd", 45, 79, 52, 10, "Updater.check_and_install()\nmodo GitHub  |  modo HTTP zip", "core")
box("dl", 45, 69, 24, 8, "download em blocos\n+ verificacao SHA-256", "core", 9)
box("zip", 73, 69, 24, 8, "ziputil.extract()\nzip -> staging", "core", 9)

group(108, 66, 41, 28, "Armazenamento /sdcard/app")
box("cur", 111, 80, 35, 8, "current/  (versao ativa)", "store")
box("prev", 111, 70, 35, 8, "previous/  (rollback)", "store")

# Row 2: guard + state
group(1, 33, 70, 29, "Salva-guarda (guard.py)")
box("boot", 4, 43, 30, 14, "Guard.boot()\n1) conta falha se 'trial'\n2) blacklist + rollback\n3) try_update()\n4) executa o app", "safe")
box("wdt", 38, 43, 30, 14, "WDT de hardware\nfeed() pelo app\nconfirm_after -> 'ok'", "safe")
box("state", 4, 35, 64, 5.5, "state.json: status (trial/ok), fails, bad[]", "store", 9)

# Row 2 right: application
group(78, 33, 71, 29, "Aplicacao baixada (current/main.py + .kmodel)")
box("app", 81, 43, 30, 14, "main.py\n(exec com cwd=current/)", "app")
box("kpu", 115, 43, 31, 14, "Inferencia KPU\nsegmentacao .kmodel\n-> contagem de objetos", "app")
box("post", 81, 35, 65, 5.5, "POST {chipid, objects, temp} -> report_url", "app", 9)

# Row 3: thermal and hardware
group(1, 2, 70, 27, "Controle termico (thermal.py)")
box("sens", 4, 6, 28, 12, "Sensor de\ntemperatura do chip", "therm")
box("gov", 38, 6, 30, 12, "Thermal.pace()\nreduz FPS / pausa\ncom histerese", "therm")

group(78, 2, 71, 27, "Hardware")
box("cam", 81, 6, 30, 12, "Camera / Sensor\n(captura de quadros)", "ext")
box("cid", 115, 6, 31, 12, "machine.chipid()\n(device.py)", "ext")

# Arrows
arrow("gh", "r", "upd", "l", "token", off=(0, 2))
arrow("http", "r", "dl", "l", None, rad=0.0)
ax.add_patch(FancyArrowPatch((57,79),(57,77),arrowstyle="-|>",mutation_scale=15,lw=1.5,color="#222"))
arrow("dl", "r", "zip", "l", None)
arrow("upd", "r", "cur", "l", "troca atomica", off=(0, 2))
arrow("cur", "b", "prev", "t", "vira previous", off=(-18, 0))
arrow("boot", "t", "dl", "b", "try_update()", off=(-8, 0))
arrow("boot", "r", "wdt", "l", None)
arrow("boot", "b", "state", "t", None)

arrow("boot", "b", "app", "b", None, rad=0.0, ls="--") if False else None
arrow("wdt", "r", "app", "l", "executa", off=(0, 2))
arrow("app", "r", "kpu", "l", None)
arrow("kpu", "b", "post", "t", None)
arrow("app", "b", "wdt", "b", None, rad=0.0, ls="--") if False else None
arrow("gov", "t", "wdt", "b", "feed()", off=(10, 0), color="#b36200")
arrow("sens", "r", "gov", "l", "temp")
arrow("gov", "r", "cam", "l", "FPS alvo", off=(0, 2))
arrow("cam", "t", "app", "b", "frames", off=(0, 0))
arrow("cid", "t", "post", "b", "chipid", off=(0, 0))
arrow("cid", "t", "kpu", "b", None) if False else None

plt.savefig(OUT, dpi=170, bbox_inches="tight", facecolor="white")
print("saved", OUT)

