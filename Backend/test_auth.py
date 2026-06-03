from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    context = browser.new_context(storage_state="auth.json")

    page = context.new_page()

    page.goto("https://www.kaggle.com")

    print(page.title())

    input("Press Enter...")

    browser.close()
