from playwright.sync_api import sync_playwright

def log_request(request):
    if "api/i/" in request.url:
        print(request.method, request.url)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    context = browser.new_context(storage_state="auth.json")

    page = context.new_page()

    page.on("request", log_request)

    page.goto(
        "https://www.kaggle.com/competitions/orbit-wars/submissions"
    )

    page.wait_for_timeout(10000)

    input("Press Enter...")

    browser.close()
