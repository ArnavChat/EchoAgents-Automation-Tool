import subprocess
import time
import requests
import os
from utils import get_env, get_path

def wait_for_service(url, timeout=60):
    """Wait until a service at `url` responds with status < 500 or until timeout."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code < 500:
                print(f"Service at {url} is ready.")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    print(f"Timeout waiting for {url}")
    return False

# Services to start in sequence with URLs to check
services_to_wait_for = [
    ("run-timeline.ps1",      get_env("TIMELINE_URL",      "http://localhost:8000")),
    ("run-msg-proxy.ps1",     get_env("MSG_PROXY_URL",     "http://localhost:8001")),
    ("run-orchestrator.ps1",  get_env("ORCHESTRATOR_URL",  "http://localhost:8002")),
    ("run-voice-agent.ps1",   get_env("VOICE_AGENT_URL",   "http://localhost:8003")),
]

processes = []

for script_name, service_url in services_to_wait_for:
    # Build script path relative to SCRIPTS_DIR
    script_path = get_path(os.path.join(get_env("SCRIPTS_DIR"), script_name))
    print(f"Starting {script_path}...")

    # Start the service
    p = subprocess.Popen(
        ["powershell", "-ExecutionPolicy", "ByPass", "-File", str(script_path)],
        stdout=None,
        stderr=None
    )
    processes.append(p)

    # Wait for the service to be ready
    if not wait_for_service(service_url, timeout=120):
        print(f"{script_name} not ready, exiting.")
        exit(1)

# All services started and ready, now send audio to voice agent
audio_path = get_path(get_env("SAMPLE_AUDIO"))
if not audio_path.exists():
    print(f"Audio file not found: {audio_path}")
else:
    with open(audio_path, "rb") as f:
        files = {"file": f}
        try:
            response = requests.post(f"{get_env('VOICE_AGENT_URL', 'http://localhost:8003')}/voice/command", files=files)
            print("Response status:", response.status_code)
            print("Response body:", response.text)
        except Exception as e:
            print("Error making POST request:", e)
