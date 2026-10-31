import httpx


def fetch(url):
    response = httpx.get(url, timeout=httpx.Timeout(8.0, connect=3.0))
    response.raise_for_status()
    return response.content
