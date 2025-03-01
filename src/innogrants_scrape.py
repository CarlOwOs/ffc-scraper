import asyncio

from scrape import scrape_urls
from config.constants import INNOGRANTS_URL
    
async def main():
    await scrape_urls([INNOGRANTS_URL])

if __name__ == '__main__':
    asyncio.run(main())