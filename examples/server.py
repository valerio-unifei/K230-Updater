"""Reference server for tests (PC, stdlib only).

  GET  /update?chipid=..&last_update=..  -> 200 zip of ./package if newer, else 204
  POST /report  JSON {chipid, objects, temp, ...} -> printed

Build the package: put main.py, manifest.json ({"version": "1.0.0"}) and
models/*.kmodel in ./package. Zip is built with no compression (kmodel-friendly).
Run: python server.py  (port 8000)
"""
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

PACKAGE = os.path.join(os.path.dirname(__file__), "package")


def package_date():
    newest = max(os.path.getmtime(os.path.join(d, f))
                 for d, _, fs in os.walk(PACKAGE) for f in fs)
    return datetime.fromtimestamp(newest, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def build_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for d, _, fs in os.walk(PACKAGE):
            for f in fs:
                full = os.path.join(d, f)
                z.write(full, os.path.relpath(full, PACKAGE).replace("\\", "/"))
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path != "/update":
            return self.send_error(404)
        q = parse_qs(u.query)
        chipid = q.get("chipid", [""])[0]
        last = q.get("last_update", [""])[0]
        date = package_date()
        print("update check chipid=%s last=%s server=%s" % (chipid, last, date))
        if last and last >= date:
            self.send_response(204)
            self.end_headers()
            return
        body = build_zip()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Updated-At", date)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/report":
            return self.send_error(404)
        n = int(self.headers.get("Content-Length", 0))
        print("report:", json.loads(self.rfile.read(n) or b"{}"))
        self.send_response(200)
        self.end_headers()


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
