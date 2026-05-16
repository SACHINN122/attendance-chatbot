from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating to root...")
        page.goto("https://www.imsnsit.org/imsnsit/")
        page.wait_for_timeout(2000)
        
        # Click Student Login link (might be in a frame)
        for frame in page.frames:
            if frame.locator("text='Student Login'").count() > 0:
                print(f"Found Student Login in frame {frame.name}, clicking...")
                frame.locator("text='Student Login'").click()
                break
                
        page.wait_for_timeout(5000)
        
        print("Taking screenshot...")
        page.screenshot(path="debug_login.png", full_page=True)
        
        print("Frames found:")
        for frame in page.frames:
            print(f"- Frame name: '{frame.name}', url: {frame.url}")
            inputs = frame.locator("input").count()
            print(f"  Contains {inputs} inputs")
            if inputs > 0:
                print("  Input names:", [inp.get_attribute("name") for inp in frame.locator("input").all()])
        
        browser.close()

if __name__ == "__main__":
    main()
