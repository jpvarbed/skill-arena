#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path


EXEC_URL = "https://exe.dev/exec"
KEY_ENV = "exe_dev_skill_arena_forever_ssh_key"
BOX_PREFIX = "t2-"


def box_name_for_instance(instance_id):
    slug = re.sub(r"[^a-z0-9-]+", "-", str(instance_id).lower()).strip("-")
    slug = re.sub(r"-+", "-", slug) or "instance"
    return (BOX_PREFIX + slug)[:20].rstrip("-")


def default_requester(command, key):
    request = urllib.request.Request(
        EXEC_URL,
        data=command.encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "text/plain",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode()
    return json.loads(body) if body.strip() else {}


class ExeBoxClient:
    def __init__(self, runner=None, requester=None, key=None):
        self.runner = runner or subprocess.run
        self.requester = requester or default_requester
        self.key = key if key is not None else os.environ.get(KEY_ENV)

    def _request(self, command):
        if not self.key:
            raise RuntimeError(f"{KEY_ENV} is required for exe.dev lifecycle calls")
        return self.requester(command, self.key)

    def create(self, name):
        return self._request(f"new --name={name} --no-email --json")

    def remove(self, name):
        return self._request(f"rm {name}")

    def list(self):
        data = self._request("ls")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("boxes"), list):
            return data["boxes"]
        return []

    def cleanup(self, prefix=BOX_PREFIX):
        removed = []
        for item in self.list():
            name = item.get("name") if isinstance(item, dict) else str(item)
            if name.startswith(prefix):
                self.remove(name)
                removed.append(name)
        return removed

    def ssh(self, name, command, timeout=None):
        return self.runner(
            _ssh_args(name, command),
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

    def scp_from(self, name, remote_path, local_path):
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        return self.runner(
            [
                "scp",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                f"{name}.exe.xyz:{remote_path}",
                str(local_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            stdin=subprocess.DEVNULL,
        )

    def write_text(self, name, remote_path, text):
        if not text:
            # `cat > f` with empty stdin hangs until timeout on some ssh paths — truncate instead
            proc = self.runner(
                _ssh_args(name, f": > {remote_path}"),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"failed to write {remote_path}: {proc.stderr}")
            return proc
        proc = self.runner(
            _ssh_args(name, f"cat > {remote_path}"),
            input=text,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"failed to write {remote_path}: {proc.stderr}")
        return proc

    def wait_ready(self, name, poll_s=10, timeout_s=120):
        deadline = time.monotonic() + timeout_s
        last_stderr = ""
        while time.monotonic() <= deadline:
            proc = self.ssh(name, "echo READY", timeout=30)
            last_stderr = proc.stderr
            if proc.returncode == 0 and proc.stdout.strip() == "READY":
                return True
            if poll_s:
                time.sleep(poll_s)
        raise TimeoutError(f"{name} did not become ready: {last_stderr}")


def _ssh_args(name, command):
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{name}.exe.xyz",
        "--",
        command,
    ]


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("cleanup")
    args = parser.parse_args(argv)
    if args.command == "cleanup":
        removed = ExeBoxClient().cleanup()
        print(json.dumps({"removed": removed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
