from playwright.sync_api import sync_playwright

def log_request(request):
    if "CompetitionService/ListCompetitions" in request.url:
        print("URL:")
        print(request.url)

        print("\nHEADERS:")
        for k, v in request.headers.items():
            print(f"{k}: {v}")

        print("\nPOST DATA:")
        print(request.post_data)

        exit()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    context = browser.new_context(storage_state="auth.json")

    page = context.new_page()

    page.on("request", log_request)

    page.goto("https://www.kaggle.com/competitions")

    input("Press Enter...")
