"""Browser smoke checks against a local test server; never deletes real media."""

import json
import os

from playwright.sync_api import sync_playwright

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:18000")


def main():
    payload = [
        {
            "Id": item_id,
            "Name": 'Film <img src=x onerror="window.injected=true">',
            "ProductionYear": 2020,
            "Path": "/movies/" + item_id + ".mkv",
            "ProviderIds": {"Tmdb": "123"},
            "MediaSources": [
                {"Size": size, "MediaStreams": [{"Type": "Video", "Width": 1920, "Height": 1080}]}
            ],
        }
        for item_id, size in [("keep", 2000000000), ("remove", 1000000000)]
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE_URL)
        page.locator("#jsonFile").set_input_files(
            {
                "name": "movies.json",
                "mimeType": "application/json",
                "buffer": json.dumps(payload).encode(),
            }
        )
        page.locator("#scanFileBtn").click()
        page.locator(".group").wait_for()
        assert page.locator(".group").count() == 1
        assert page.locator("input[data-id]:checked").count() == 0
        assert page.locator(".group img").count() == 0
        assert not page.evaluate("window.injected === true")
        page.locator("#selectAllBtn").click()
        assert page.locator("input[data-id]:checked").count() == 1
        assert page.locator("#deleteBtn").is_disabled()
        page.locator("#filterInput").fill("not-found")
        assert page.locator(".group").count() == 0
        page.locator("#filterInput").fill("")
        page.locator("#selectNoneBtn").click()

        # Simulated Jellyfin responses only: verify confirmation and request contents.
        result = page.request.post(
            BASE_URL + "/api/v1/scans/file",
            multipart={
                "file": {
                    "name": "movies.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(payload).encode(),
                }
            },
        ).json()
        result["source"] = "jellyfin"
        page.route("**/api/v1/scans/jellyfin", lambda route: route.fulfill(json=result))
        delete_calls = []

        def deletion(route):
            body = route.request.post_data_json
            delete_calls.append(body)
            route.fulfill(
                json={
                    "requested_ids": body["item_ids"],
                    "deleted_ids": [],
                    "failed_ids": {},
                    "dry_run": body["dry_run"],
                }
            )

        page.route("**/api/v1/scans/*/delete", deletion)
        page.locator("#baseUrl").fill("https://example.com")
        page.locator("#apiKey").fill("test-key")
        page.locator("#scanJellyfinBtn").click()
        page.wait_for_function(
            "document.querySelector('#status').textContent.includes('Scan abgeschlossen')"
        )
        page.locator("#selectAllBtn").click()
        assert page.locator("#deleteBtn").is_enabled()
        page.locator("#dryRunBtn").click()
        page.wait_for_function(
            "document.querySelector('#status').textContent.includes('Prüfung abgeschlossen')"
        )
        assert delete_calls == [{"dry_run": True, "item_ids": ["remove"]}]
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator("#deleteBtn").click()
        assert len(delete_calls) == 1
        page.screenshot(path="/tmp/jellyfin-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path="/tmp/jellyfin-mobile.png", full_page=True)
        assert not errors, errors
        browser.close()
    print(
        "Browser checks passed: upload, XSS escaping, selection, filter, dry run, cancel, mobile layout"
    )


if __name__ == "__main__":
    main()
