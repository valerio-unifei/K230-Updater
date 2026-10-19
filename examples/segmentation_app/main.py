# Complete example app (lives in the update package as main.py):
# YOLOv8-seg .kmodel inference on the K230 camera, thermal-governed FPS, and
# periodic POST of {chipid, objects, temp} to config.json "report_url".
#
# UNTESTED TEMPLATE: adapt MODEL, sizes, labels, input dtype/normalisation and
# the CanMV media API calls to your firmware version and model export.
import time
import json
import gc

import ulab.numpy as np
import nncase_runtime as nn
from media.sensor import Sensor, CAM_CHN_ID_0
from media.media import MediaManager

import requests
import k230_updater
from k230_updater import Thermal
from k230_updater.device import chip_id

MODEL = "models/yolov8n_seg.kmodel"
SIZE = 320                  # square model input
NUM_CLASSES = 80
NUM_MASK = 32
CONF = 0.4
IOU = 0.5
REPORT_EVERY_S = 10
MAX_TEMP = 75
TARGET_FPS = 15

guard = k230_updater.guard
with open("/sdcard/config.json") as f:
    REPORT_URL = json.load(f).get("report_url")

CHIPID = chip_id()


def read_temp():
    import machine
    return machine.temperature()   # adjust to your firmware


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0


def segment(kpu, img):
    """Returns list of (box, score, cls, mask_pixels)."""
    arr = img.to_numpy_ref()                       # (3, SIZE, SIZE) uint8, RGB planar
    data = np.array(arr, dtype=np.float32) / 255.0
    data = data.reshape((1, 3, SIZE, SIZE))
    kpu.set_input_tensor(0, nn.from_numpy(data))
    kpu.run()
    pred = kpu.get_output_tensor(0).to_numpy()[0]      # (4+nc+32, N)
    proto = kpu.get_output_tensor(1).to_numpy()[0]     # (32, SIZE/4, SIZE/4)

    cls_scores = pred[4:4 + NUM_CLASSES, :]
    best = np.max(cls_scores, axis=0)
    cands = []
    for i in range(best.shape[0]):
        s = best[i]
        if s >= CONF:
            cands.append((s, i))
    cands.sort(key=lambda c: -c[0])
    cands = cands[:50]

    kept = []
    for s, i in cands:
        cx, cy, w, h = pred[0, i], pred[1, i], pred[2, i], pred[3, i]
        box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        if all(iou(box, k[0]) < IOU for k in kept):
            cls = int(np.argmax(cls_scores[:, i]))
            kept.append((box, s, cls, i))

    results = []
    if kept:
        ph = proto.shape[1]
        flat = proto.reshape((NUM_MASK, ph * ph))
        for box, s, cls, i in kept:
            coef = pred[4 + NUM_CLASSES:4 + NUM_CLASSES + NUM_MASK, i]
            logits = np.dot(coef.reshape((1, NUM_MASK)), flat)   # (1, ph*ph)
            pixels = int(np.sum(logits > 0))                     # sigmoid(x) > 0.5
            results.append((box, s, cls, pixels))
    return results


def report(count, temp, pixels):
    if not REPORT_URL:
        return
    payload = {"chipid": CHIPID, "objects": count, "temp": temp,
               "mask_pixels": pixels}
    try:
        r = requests.post(REPORT_URL, json=payload)
        r.close()
    except Exception as e:
        print("report failed:", e)


sensor = Sensor(width=SIZE, height=SIZE)
sensor.reset()
sensor.set_framesize(width=SIZE, height=SIZE, chn=CAM_CHN_ID_0)
sensor.set_pixformat(Sensor.RGBP888, chn=CAM_CHN_ID_0)
MediaManager.init()
sensor.run()

kpu = nn.kpu()
guard.feed()
kpu.load_kmodel(MODEL)       # can be slow: WDT was fed just before
guard.feed()

gov = Thermal(max_temp=MAX_TEMP, target_fps=TARGET_FPS, min_fps=1,
              read=read_temp, feed=guard.feed)
last_report = time.time()
count = 0
pixels = 0

try:
    while True:
        img = sensor.snapshot(chn=CAM_CHN_ID_0)
        res = segment(kpu, img)
        count = len(res)
        pixels = sum(r[3] for r in res)
        del img
        gc.collect()

        if time.time() - last_report >= REPORT_EVERY_S:
            last_report = time.time()
            report(count, read_temp(), pixels)
        gov.pace()
finally:
    sensor.stop()
    MediaManager.deinit()
