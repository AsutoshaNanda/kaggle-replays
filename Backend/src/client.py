import requests
from playwright.sync_api import sync_playwright


class KaggleReplayClient:
    def __init__(self):
        self.session = requests.Session()

        with sync_playwright() as p:
            browser = p.chromium.launch()

            context = browser.new_context(
                storage_state="auth.json"
            )

            cookies = context.cookies()

            for cookie in cookies:
                self.session.cookies.set(
                    cookie["name"],
                    cookie["value"]
                )

            browser.close()
