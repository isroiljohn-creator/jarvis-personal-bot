from duckduckgo_search import DDGS
import json

def fetch_ig():
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text("site:instagram.com/reel biznes", max_results=5))
            print("RESULTS:", results)
    except Exception as e:
        print("ERROR:", e)

fetch_ig()
