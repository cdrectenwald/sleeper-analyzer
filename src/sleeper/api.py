import time
import requests

BASE = "https://api.sleeper.app/v1"

def get_json(path: str, *, sleep_s: float = 0.15, timeout_s: int = 30, retries: int = 5):
    url = f"{BASE}{path}"
    last_err = None

    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=timeout_s)
            if r.status_code == 200:
                time.sleep(sleep_s)
                return r.json()

            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue

            r.raise_for_status()

        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)

    raise RuntimeError(f"Failed to GET {url} after {retries} retries. Last error: {last_err}")
