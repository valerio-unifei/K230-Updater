"""Minimal streaming ZIP extractor for MicroPython (no zipfile dependency).

Supports methods 0 (stored) and 8 (deflate). Stored entries are copied in
chunks, so large .kmodel files should be zipped with *no compression*
(`zip -0`). Deflate entries are read into RAM before inflating.
"""
import struct
import io

from . import util

CHUNK = 4096


def _inflate(data):
    try:
        import deflate
        with deflate.DeflateIO(io.BytesIO(data), deflate.RAW) as d:
            return d.read()
    except ImportError:
        pass
    try:
        import zlib
        return zlib.decompress(data, -15)
    except (ImportError, AttributeError):
        pass
    import uzlib
    return uzlib.decompress(data, -15)


def _safe(name):
    if name.startswith("/") or ".." in name.split("/") or "\\" in name:
        raise ValueError("unsafe path in zip: " + name)
    return name


def extract(zip_path, dest, feed=None):
    """Extracts zip_path into dest. Returns the list of extracted names."""
    feed = feed or (lambda: None)
    names = []
    with open(zip_path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        tail = min(size, 65557)
        f.seek(size - tail)
        buf = f.read(tail)
        pos = buf.rfind(b"PK\x05\x06")
        if pos < 0:
            raise ValueError("not a zip file")
        count, cd_size, cd_off = struct.unpack("<HII", buf[pos + 10:pos + 20])
        f.seek(cd_off)
        entries = []
        for _ in range(count):
            h = f.read(46)
            if h[:4] != b"PK\x01\x02":
                raise ValueError("bad central directory")
            method, = struct.unpack("<H", h[10:12])
            csize, usize, nlen, elen, clen = struct.unpack("<IIHHH", h[20:34])
            lh_off, = struct.unpack("<I", h[42:46])
            name = f.read(nlen).decode()
            f.read(elen + clen)
            entries.append((name, method, csize, usize, lh_off))

        for name, method, csize, usize, lh_off in entries:
            if name.endswith("/"):
                continue
            _safe(name)
            f.seek(lh_off)
            lh = f.read(30)
            if lh[:4] != b"PK\x03\x04":
                raise ValueError("bad local header")
            nlen, elen = struct.unpack("<HH", lh[26:30])
            f.seek(lh_off + 30 + nlen + elen)
            out = dest + "/" + name
            if "/" in name:
                util.makedirs(out.rsplit("/", 1)[0])
            with open(out, "wb") as o:
                if method == 0:
                    left = csize
                    while left:
                        b = f.read(min(CHUNK, left))
                        if not b:
                            raise ValueError("truncated zip")
                        o.write(b)
                        left -= len(b)
                        feed()
                elif method == 8:
                    o.write(_inflate(f.read(csize)))
                else:
                    raise ValueError("unsupported zip method %d" % method)
            feed()
            names.append(name)
    return names
