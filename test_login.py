import asyncio
from instagrapi import Client

def test():
    cl = Client()
    try:
        print("Logging in...")
        cl.login("Dereck_111111", "Dereck_1111")
        print("Login successful!")
        medias = cl.hashtag_medias_top("biznes", amount=1)
        print("Fetched medias:", len(medias))
        if medias:
            print("URL:", f"https://www.instagram.com/p/{medias[0].code}/")
    except Exception as e:
        print("ERROR:", e)

test()
