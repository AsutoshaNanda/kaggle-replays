from playwright.sync_api import sync_playwright

def log_response(response):
    if "CompetitionService/ListCompetitions" in response.url:
        try:
            print(response.text()[:3000])
            exit()
        except:
            pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    context = browser.new_context(
        storage_state="auth.json"
    )

    page = context.new_page()

    page.on("response", log_response)

    page.goto("https://www.kaggle.com/competitions")

    input("Press Enter...")
