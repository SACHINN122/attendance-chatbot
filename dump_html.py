import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page()
        await page.goto('https://www.imsnsit.org/imsnsit/student.htm')
        await asyncio.sleep(2)
        print(await page.content())
        
        frames = page.frames
        for f in frames:
            print(f"--- FRAME {f.name} ---")
            print(await f.content())
            
        await b.close()

asyncio.run(test())
