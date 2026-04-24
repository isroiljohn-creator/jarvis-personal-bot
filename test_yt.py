from youtubesearchpython import VideosSearch
import json

def fetch_yt():
    videosSearch = VideosSearch('#biznes shorts', limit = 3)
    results = videosSearch.result()['result']
    out = []
    for r in results:
        out.append({
            "title": r.get("title"),
            "url": r.get("link"),
            "views": r.get("viewCount", {}).get("short"),
        })
    print(json.dumps(out, indent=2))

fetch_yt()
