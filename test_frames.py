import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://www.imsnsit.org/imsnsit/student.htm")
        frames = page.frames
        for f in frames:
            print(f"Frame name: {f.name}, url: {f.url}")
        await browser.close()

asyncio.run(test())
