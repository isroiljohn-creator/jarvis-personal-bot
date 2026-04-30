import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from cloud import CloudHub

async def main():
    cloud = CloudHub()
    url = "https://www.instagram.com/reels/DA8F9UBNV1V/" # Just an example reel
    print(f"Testing Instagram Download for {url}...")
    file_path = await cloud.insta_download_media(url)
    if file_path:
        print(f"SUCCESS: Downloaded to {file_path}")
        # Clean up
        if os.path.exists(file_path):
            os.unlink(file_path)
    else:
        print("FAILED: Could not download media.")

if __name__ == "__main__":
    asyncio.run(main())
