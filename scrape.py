import asyncio
from playwright.async_api import async_playwright
import os
import json
import random
from bs4 import BeautifulSoup
import markdown
from dotenv import load_dotenv

load_dotenv()
URLS = ["https://www.epfl.ch/innovation/startup/incubation/innogrants/innogrants-list/"]#[os.environ.get("INNOGRANTS_URL")]
OUTPUT_DIR = os.environ.get("OUTPUT_DIR")

print(OUTPUT_DIR, URLS)

async def save_content(url, content):
    filename = url.replace('/', '_').replace(':', '_').replace('?', '_').replace('&', '_')
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    html_path = os.path.join(OUTPUT_DIR, f'{filename}.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Saved HTML content to {html_path}")

    soup = BeautifulSoup(content, 'html.parser')

    data = {
        'url': url,
        'title': soup.title.string.strip() if soup.title and soup.title.string else '',
        'description': soup.find('meta', attrs={'name': 'description'})['content'].strip() if soup.find('meta', attrs={'name': 'description'}) else ''
    }
    json_path = os.path.join(OUTPUT_DIR, f'{filename}.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved JSON data to {json_path}")

    md_content = markdown.markdown(str(soup.body)) if soup.body else ''
    md_path = os.path.join(OUTPUT_DIR, f'{filename}.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"Saved Markdown content to {md_path}")

async def scrape_page(page, url):
    try:
        await page.goto(url, timeout=60000, wait_until='networkidle')
        content = await page.content()
        await save_content(url, content)
        print(f"Successfully scraped: {url}")
    except Exception as e:
        print(f"Error scraping {url}: {e}")
    
    # Random delay between 10 seconds and 2 minutes
    delay = random.uniform(10, 120)
    print(f"Waiting for {delay:.2f} seconds before next request...")
    await asyncio.sleep(delay)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        for url in URLS:
            await scrape_page(page, url)
            
        await browser.close()
    print("Scraping completed.")

if __name__ == '__main__':
    asyncio.run(main())