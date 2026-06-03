from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    context = browser.new_context()

    page = context.new_page()

    page.goto("https://www.kaggle.com")

    input("Login to Kaggle then press Enter...")

    context.storage_state(path="auth.json")

    browser.close()
