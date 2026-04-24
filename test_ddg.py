from duckduckgo_search import DDGS
import json

def fetch_ig():
    with DDGS() as ddgs:
        results = list(ddgs.text("site:tiktok.com biznes", max_results=5))
        print(json.dumps(results, indent=2))

fetch_ig()
