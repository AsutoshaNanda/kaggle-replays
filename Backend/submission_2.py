from playwright.sync_api import sync_playwright
import os

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

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

    competitions = page.evaluate(
        """
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
    """,
        {"xsrf": xsrf, "buildHash": build_hash},
    )

    print("\nCompetitions:\n")

    for i, comp in enumerate(competitions["competitions"], start=1):
        print(f"{i}. {comp['title']} ({comp['competitionName']})")

    competition_choice = int(input("\nSelect competition: "))

    competition = competitions["competitions"][competition_choice - 1]

    team = next(
        t for t in competitions["userTeams"] if t["competitionId"] == competition["id"]
    )

    team_id = team["id"]

    submissions = page.evaluate(
        """
    async ({xsrf, buildHash, teamId}) => {
        const r = await fetch(
            "/api/i/competitions.SubmissionService/ListSubmissions",
            {
                method: "POST",
                headers: {
                    "content-type": "application/json",
                    "x-xsrf-token": xsrf,
                    "x-kaggle-build-version": buildHash
                },
                body: JSON.stringify({
                    teamId: teamId,
                    pageSize: 50,
                    pageToken: "",
                    selector: {
                        listOption: "LIST_OPTION_DEFAULT",
                        sortOption: "SORT_OPTION_DEFAULT",
                        submissionIds: []
                    }
                })
            }
        );

        return await r.json();
    }
    """,
        {"xsrf": xsrf, "buildHash": build_hash, "teamId": team_id},
    )

    print("\nSubmissions:\n")

    submission_list = submissions["submissions"]

    for i, s in enumerate(submission_list, start=1):
        score = s.get("publicScoreFormatted", "-")
        print(f"{i}. {score} | {s['title']}")

    submission_choice = int(input("\nSelect submission: "))

    selected_submission = submission_list[submission_choice - 1]

    submission_id = selected_submission["id"]

    print("\nSelected Submission")
    print("ID   :", submission_id)
    print("Score:", selected_submission.get("publicScoreFormatted", "-"))
    print("Name :", selected_submission["title"])

    episodes = page.evaluate(
        """
    async ({xsrf, buildHash, submissionId}) => {
        const r = await fetch(
            "/api/i/competitions.EpisodeService/ListEpisodes",
            {
                method: "POST",
                headers: {
                    "content-type": "application/json",
                    "x-xsrf-token": xsrf,
                    "x-kaggle-build-version": buildHash
                },
                body: JSON.stringify({
                    submissionId: submissionId
                })
            }
        );

        return await r.json();
    }
    """,
        {"xsrf": xsrf, "buildHash": build_hash, "submissionId": submission_id},
    )

    episode_list = episodes["episodes"]

    print(f"\nTotal Episodes: {len(episode_list)}")

    confirm = input("\nDownload all replays? [Y/n]: ").strip().lower()

    if confirm not in ["", "y", "yes"]:
        browser.close()
        raise SystemExit

    competition_slug = competition["competitionName"]

    submission_name = (
        selected_submission["title"]
        .replace(".py", "")
        .replace(".zip", "")
        .replace(".tar.gz", "")
    )
    download_dir = os.path.join(
        "downloads", competition_slug, f"{submission_name}_replays"
    )
    os.makedirs(download_dir, exist_ok=True)

    print("\nDownloading replays...\n")

    for i, ep in enumerate(episode_list, start=1):
        episode_id = ep["id"]

        replay = page.evaluate(
            """
        async (episodeId) => {
            const r = await fetch(
                `/competitions/episodes/${episodeId}/replay.json`
            );

            return {
                status: r.status,
                text: await r.text()
            };
        }
        """,
            episode_id,
        )
        
        if replay["status"] == 200:

            filepath = os.path.join(
                download_dir,
                f"{episode_id}.json"
            )

            with open(
                filepath,
                "w",
                encoding="utf-8"
            ) as f:
                f.write(replay["text"])

            print(
                f"[{i}/{len(episode_list)}] Downloaded {episode_id}"
            )
        else:
            print(
                f"[{i}/{len(episode_list)}] Failed {episode_id}"
            )

    print("\nDone.")
    print("Saved to:")
    print(download_dir)

    browser.close()
