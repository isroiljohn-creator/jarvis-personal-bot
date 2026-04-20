import requests

api_key = "kqhWCHW5.yDDBnMUq2RY267iPHJ2ekowzTnklYnqa"
url = "https://api.aisha.group/v1/audio/speech"
headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
data = {"model": "tts-1", "input": "Salom, bu test", "voice": "aisha"}
r = requests.post(url, headers=headers, json=data)
print(r.status_code, r.text[:200])
