"""Remote updater for a private GitHub repository.

Repository layout (on the update branch):

    manifest.json   {"version": "1.2.0", "entry": "main.py",
                     "files": [{"path": "main.py", "sha256": "..."},
                               {"path": "models/det.kmodel", "sha256": "..."}]}
    main.py
    models/det.kmodel

Files are fetched through the GitHub contents API with a token, verified with
SHA-256, staged, and only then swapped in atomically (current -> previous).
"""
import os
import gc

try:
    import requests
except ImportError:
    import urequests as requests

try:
    import hashlib
except ImportError:
    import uhashlib as hashlib

try:
    import ubinascii as binascii
except ImportError:
    import binascii

from . import util

CHUNK = 4096


class UpdateError(Exception):
    pass


class Updater:
    def __init__(self, repo, token, root="/sdcard/app", branch="main", feed=None):
        """repo: 'owner/name'. token: fine-grained PAT with Contents:read.
        feed: callable invoked during downloads (feed the hardware watchdog)."""
        self.repo = repo
        self.token = token
        self.branch = branch
        self.root = root
        self.feed = feed or (lambda: None)
        self.current = root + "/current"
        self.previous = root + "/previous"
        self.staging = root + "/staging"
        util.makedirs(root)

    def _get(self, path):
        url = "https://api.github.com/repos/%s/contents/%s?ref=%s" % (
            self.repo, path, self.branch)
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github.raw+json",
            "User-Agent": "k230-updater",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            code = resp.status_code
            resp.close()
            raise UpdateError("GET %s -> HTTP %d" % (path, code))
        return resp

    def remote_manifest(self):
        resp = self._get("manifest.json")
        try:
            manifest = resp.json()
        finally:
            resp.close()
        if "version" not in manifest or "files" not in manifest:
            raise UpdateError("invalid manifest")
        return manifest

    def local_manifest(self):
        return util.read_json(self.current + "/manifest.json")

    def _download(self, rel, dest, expected_sha):
        resp = self._get(rel)
        h = hashlib.sha256()
        try:
            util.makedirs(dest.rsplit("/", 1)[0])
            with open(dest, "wb") as f:
                raw = getattr(resp, "raw", None)
                if raw is not None and hasattr(raw, "read"):
                    while True:
                        buf = raw.read(CHUNK)
                        if not buf:
                            break
                        h.update(buf)
                        f.write(buf)
                        self.feed()
                else:
                    data = resp.content
                    h.update(data)
                    f.write(data)
        finally:
            resp.close()
            gc.collect()
        digest = binascii.hexlify(h.digest()).decode()
        if expected_sha and digest != expected_sha.lower():
            raise UpdateError("sha256 mismatch for " + rel)

    def install(self, manifest):
        """Download every file to staging, verify, then swap into place."""
        util.rmtree(self.staging)
        util.makedirs(self.staging)
        try:
            for item in manifest["files"]:
                rel = item["path"]
                self._download(rel, self.staging + "/" + rel, item.get("sha256"))
                self.feed()
            util.write_json(self.staging + "/manifest.json", manifest)
        except Exception:
            util.rmtree(self.staging)
            raise
        util.rmtree(self.previous)
        if util.exists(self.current):
            os.rename(self.current, self.previous)
        os.rename(self.staging, self.current)

    def check_and_install(self, skip_versions=()):
        """Returns the installed version string, or None if nothing to do."""
        manifest = self.remote_manifest()
        version = str(manifest["version"])
        local = self.local_manifest()
        if version in skip_versions:
            return None
        if local and str(local.get("version")) == version:
            return None
        self.install(manifest)
        return version

    def rollback(self):
        """Replace current with previous. Returns True if a rollback happened."""
        if not util.exists(self.previous):
            return False
        util.rmtree(self.current)
        os.rename(self.previous, self.current)
        return True
