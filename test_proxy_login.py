import asyncio
from instagrapi import Client

def test():
    cl = Client()
    # cl.set_proxy("http://38.250.126.225:999")
    try:
        print("Setting proxy and logging in...")
        cl.set_proxy("http://38.250.126.225:999")
        cl.login("Dereck_111111", "Dereck_1111")
        print("Login successful!")
        medias = cl.hashtag_medias_top("biznes", amount=1)
        print("Fetched medias:", len(medias))
    except Exception as e:
        print("ERROR:", e)

test()
