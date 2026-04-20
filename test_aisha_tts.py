import requests
import json

api_key = "kqhWCHW5.yDDBnMUq2RY267iPHJ2ekowzTnklYnqa"
headers = {"x-api-key": api_key, "Content-Type": "application/json"}
data = {"text": "Salom, bu test", "speaker": "aisha"}

endpoints = [
    "https://back.aisha.group/api/v1/tts/",
    "https://back.aisha.group/api/v1/tts/post/",
    "https://back.aisha.group/api/v2/tts/",
    "https://back.aisha.group/api/v2/tts/post/",
    "https://back.aisha.group/api/tts/post/"
]

for url in endpoints:
    r = requests.post(url, headers=headers, json=data)
    print(f"URL: {url} -> {r.status_code}")
    if r.status_code in [200, 201]:
        print(r.text[:200])

