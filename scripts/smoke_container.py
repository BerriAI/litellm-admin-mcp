"""Check packaged HTTP startup without a real gateway or credentials."""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid

name = "admin-mcp-smoke-" + uuid.uuid4().hex[:10]
image = os.getenv("SMOKE_IMAGE", "litellm-admin-mcp:smoke")
def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()
try:
    docker("run", "--detach", "--name", name, "--read-only", "--cap-drop=ALL",
           "--security-opt=no-new-privileges:true", "--tmpfs", "/tmp",
           "--publish", "127.0.0.1::8080", "--env", "LITELLM_BASE_URL=https://gateway.example.com", image)
    port = docker("port", name, "8080/tcp").rsplit(":", 1)[1]
    base = "http://127.0.0.1:" + port
    deadline = time.monotonic() + 20
    while True:
        try:
            with urllib.request.urlopen(base + "/healthz", timeout=1) as response:
                assert json.load(response)["status"] == "ok"
            break
        except (urllib.error.URLError, OSError):
            if time.monotonic() > deadline:
                raise RuntimeError("Connector did not start") from None
            time.sleep(.2)
    try:
        urllib.request.urlopen(urllib.request.Request(base + "/mcp", data=b"{}"), timeout=2)
        raise AssertionError("Anonymous MCP access allowed")
    except urllib.error.HTTPError as error:
        assert error.code == 401
        assert error.headers["Cache-Control"] == "no-store"
    assert docker("exec", name, "id", "-u") == "10001"
    docker("exec", name, "python", "-c", "from litellm_admin_mcp.catalog import OPERATIONS; assert len(OPERATIONS) == 65")
    print("Container smoke passed: non-root startup, health, packaged catalog and anonymous access denied.")
finally:
    subprocess.run(["docker", "rm", "--force", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
