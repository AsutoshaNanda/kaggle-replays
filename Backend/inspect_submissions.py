from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    context = browser.new_context(storage_state="auth.json")
    page = context.new_page()

    page.goto("https://www.kaggle.com/competitions")
    page.wait_for_timeout(3000)

    xsrf = page.evaluate("""
    () => document.cookie.match(/XSRF-TOKEN=([^;]+)/)?.[1]
    """)

    build_hash = page.evaluate("""
    () => document.cookie.match(/build-hash=([^;]+)/)?.[1]
    """)

    competitions = page.evaluate("""
    async ({xsrf, buildHash}) => {
        const r = await fetch(
            "/api/i/competitions.CompetitionService/ListCompetitions",
            {
                method: "POST",
                headers: {
                    "content-type": "application/json",
                    "x-xsrf-token": xsrf,
                    "x-kaggle-build-version": buildHash
                },
                body: JSON.stringify({
                    selector: {
                        competitionIds: [],
                        listOption: "LIST_OPTION_USER_ENTERED",
                        sortOption: "SORT_OPTION_NUM_TEAMS",
                        hostSegmentIdFilter: 0,
                        searchQuery: "",
                        prestigeFilter: "PRESTIGE_FILTER_UNSPECIFIED",
                        visibilityFilter: "VISIBILITY_FILTER_UNSPECIFIED",
                        participationFilter: "PARTICIPATION_FILTER_UNSPECIFIED",
                        tagIds: [],
                        excludeTagIds: [],
                        requireSimulations: false,
                        requireKernels: false,
                        requireHackathons: false
                    },
                    pageToken: "",
                    pageSize: 50,
                    readMask: "competitions,userTeams"
                })
            }
        );

        return await r.json();
    }
    """, {"xsrf": xsrf, "buildHash": build_hash})

    for i, comp in enumerate(competitions["competitions"], start=1):
        print(f"{i}. {comp['title']} ({comp['competitionName']})")

    choice = int(input("\nSelect competition: "))

    competition = competitions["competitions"][choice - 1]

    slug = competition["competitionName"]

    print("\nOpening submissions page for:", slug)

    def log_request(request):
        if "SubmissionService/ListSubmissions" in request.url:
            print("\nPOST DATA:")
            print(request.post_data)

    page.on("request", log_request)

    page.goto(
        f"https://www.kaggle.com/competitions/{slug}/submissions"
    )

    input("\nPress Enter after submissions page loads...")

    browser.close()
