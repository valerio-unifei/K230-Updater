import os
import json


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def is_dir(path):
    try:
        return os.stat(path)[0] & 0x4000 != 0
    except OSError:
        return False


def makedirs(path):
    cur = ""
    for part in path.split("/"):
        if not part:
            cur = "/"
            continue
        cur = cur + part if cur.endswith("/") or cur == "" else cur + "/" + part
        if not exists(cur):
            os.mkdir(cur)


def rmtree(path):
    if not exists(path):
        return
    if not is_dir(path):
        os.remove(path)
        return
    for name in os.listdir(path):
        rmtree(path + "/" + name)
    os.rmdir(path)


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    # Write to a temp file then rename, so a reset never leaves a half-written file.
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    try:
        os.remove(path)
    except OSError:
        pass
    os.rename(tmp, path)
