import requests
import json
try:
    res = requests.get("https://proxylist.geonode.com/api/proxy-list?limit=5&page=1&sort_by=lastChecked&sort_type=desc&protocols=http%2Chttps")
    data = res.json()
    for proxy in data.get("data", []):
        print(f"{proxy['protocols'][0]}://{proxy['ip']}:{proxy['port']}")
except Exception as e:
    print(e)
