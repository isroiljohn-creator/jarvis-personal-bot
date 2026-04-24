import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from cloud import CloudHub

async def main():
    cloud = CloudHub()
    print("Testing Instagram Niche Trends for #biznes...")
    data = await cloud.insta_get_niche_trends("biznes", limit=1)
    print("RESULT:")
    print(data)

if __name__ == "__main__":
    asyncio.run(main())
