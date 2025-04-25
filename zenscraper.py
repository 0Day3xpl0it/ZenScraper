#!/usr/bin/python3

import asyncio
import random
import json
import sys
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
import argparse
import re
from playwright.async_api import async_playwright

print("\nZenScraper created by 0Day3xpl0it\n")

# Define file paths for user agents and cookies
UA_PATH = Path("user_agents.txt")
COOKIE_PATH = Path("x_cookies.json")

# Load a random user-agent string from file to simulate different browsers
def get_random_user_agent(file_path="user_agents.txt"):
    try:
        lines = Path(file_path).read_text(encoding="utf-8").splitlines()
        return random.choice([ua.strip() for ua in lines if ua.strip()])
    except Exception:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# Select a random language header to mimic different user locales
def get_random_lang():
    langs = ["en-US,en;q=0.9", "en-GB,en;q=0.8", "en;q=0.7"]
    return random.choice(langs)

# Try to retrieve the full tweet text if it's truncated on initial load
async def hydrate_full_text(tweet_id, page):
    try:
        variables = {
            "focalTweetId": tweet_id,
            "with_rux_injections": False,
            "includePromotedContent": False,
            "withCommunity": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withBirdwatchNotes": False,
            "withVoice": True,
            "withV2Timeline": True
        }
        encoded_vars = urllib.parse.quote(json.dumps(variables))
        query_url = f"https://x.com/i/api/graphql/TweetDetailID/TweetDetail?variables={encoded_vars}"
        response = await page.request.get(query_url)
        data = await response.json()
        instrs = data.get("data", {}).get("threaded_conversation_with_injections_v2", {}).get("instructions", [])
        for instr in instrs:
            for entry in instr.get("entries", []):
                if entry.get("entryId", "").startswith("tweet-"):
                    t = entry["content"]["itemContent"]["tweet_results"]["result"]
                    full = t.get("legacy", {}).get("full_text")
                    return full
    except Exception:
        pass
    return None

# Main function to scrape tweets from a specific user profile
async def scrape_user_tweets(cfg):
    tweets = []
    seen_ids = set()
    cursor = None

    async with async_playwright() as p:
        # Launch a Chromium browser instance
        browser = await p.chromium.launch(headless=cfg.headless)
        context = await browser.new_context(
            user_agent=get_random_user_agent(),
            locale=get_random_lang(),
            viewport={"width": 1280, "height": 800}
        )

        # Try to load session cookies if available
        try:
            cookie_data = json.load(open(COOKIE_PATH))
            await context.add_cookies(cookie_data["cookies"])
            print("[DEBUG] Cookies loaded")
        except Exception as e:
            print(f"[!] Failed to load cookies: {e}")

        page = await context.new_page()

        # Set up a response handler to parse data when tweet API responses arrive
        async def handle_response(response):
            nonlocal cursor, tweets, seen_ids
            if "UserTweets" in response.url:
                print("[DEBUG] Response received for UserTweets")
                try:
                    data = await response.json()
                    result = data["data"]["user"]["result"]
                    instructions = (
                        result.get("timeline_v2", {}).get("timeline", {}).get("instructions") or
                        result.get("timeline", {}).get("timeline", {}).get("instructions") or
                        result.get("timeline", {}).get("instructions") or []
                    )
                    print(f"[DEBUG] Found {len(instructions)} instruction blocks")

                    for item in instructions:
                        for entry in item.get("entries", []):
                            eid = entry.get("entryId", "")
                            if eid.startswith("tweet-"):
                                t = entry["content"]["itemContent"]["tweet_results"]["result"]
                                legacy = t.get("legacy", {})
                                tweet_id = t.get("rest_id")
                                if not tweet_id or tweet_id in seen_ids:
                                    continue

                                full_text = legacy.get("full_text", "")
                                full_text = re.sub(r'\s+', ' ', full_text).strip()
                                created_at = legacy.get("created_at", "unknown")

                                dt = None
                                if created_at != "unknown":
                                    try:
                                        dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
                                    except:
                                        dt = None

                                # Filter tweets by provided date range
                                if dt:
                                    if cfg.since_after and dt < cfg.since_after:
                                        continue
                                    if cfg.before and dt >= cfg.before:
                                        continue

                                # Skip tweets depending on --type setting
                                is_rt = full_text.strip().startswith("RT @")
                                is_rep = full_text.strip().startswith("@")
                                if cfg.type == "tweets" and (is_rt or is_rep):
                                    continue
                                if cfg.type == "retweets" and not is_rt:
                                    continue

                                # If tweet appears shortened, try hydrating it
                                if full_text.strip().endswith("…"):
                                    hydrated = await hydrate_full_text(tweet_id, page)
                                    if hydrated:
                                        print(f"[DEBUG] Hydrated full text for {tweet_id}")
                                        full_text = hydrated

                                tweets.append({"id": tweet_id, "text": full_text, "created_at": created_at})
                                seen_ids.add(tweet_id)
                                if len(tweets) >= cfg.max:
                                    return

                            elif eid.startswith("cursor-bottom"):
                                cursor = entry["content"]["value"]
                                print(f"[DEBUG] Found cursor: {cursor}")
                except Exception as e:
                    print(f"[!] JSON parse failed: {e}")

        page.on("response", handle_response)

        # Navigate to the target user profile
        await page.goto(f"https://x.com/{cfg.username}", timeout=60000)
        print(f"[DEBUG] Navigated to https://x.com/{cfg.username}")
        await page.wait_for_timeout(3000)

        # Simulate scrolling down to load more tweets
        for i in range(cfg.scrolls):
            print(f"[DEBUG] Scroll {i+1}")
            if len(tweets) >= cfg.max or not cursor:
                break
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight);")
            await page.wait_for_timeout(2000)

        await browser.close()
        return tweets[:cfg.max]

# Script entry point when run from the command line
if __name__ == "__main__":
    # Set up command-line arguments
    parser = argparse.ArgumentParser(description="Scrape tweets from a user profile on X.com")
    parser.add_argument("--username", help="USERNAME", required=True, metavar='')
    parser.add_argument("--type", choices=["all", "tweets", "retweets"], default="all")
    parser.add_argument("--output", help="json or text output", metavar='')
    parser.add_argument("--since-after", help="Datetime format: YYYY-MM-DDTHH:MM:SS", metavar='')
    parser.add_argument("--before", help="Datetime format: YYYY-MM-DDTHH:MM:SS")
    parser.add_argument("--no-headless", help="shows browser", dest="headless", action="store_false")
    parser.add_argument("--scrolls", help="default 30 scrolls", type=int, default=30, metavar='')
    parser.add_argument("--max", help="default 50 tweets", type=int, default=50, metavar='')
    args = parser.parse_args()

    # Convert parsed args into config object
    class Config: pass
    cfg = Config()
    cfg.username = args.username
    cfg.type = args.type
    cfg.output = args.output or f"{cfg.username}.json"
    cfg.headless = args.headless
    cfg.scrolls = args.scrolls
    cfg.max = args.max
    cfg.since_after = None
    cfg.before = None

    # Validate and parse optional date filters
    if args.since_after:
        try:
            cfg.since_after = datetime.fromisoformat(args.since_after).replace(tzinfo=timezone.utc)
        except:
            print("[!] Invalid --since-after format")
            sys.exit(1)
    if args.before:
        try:
            cfg.before = datetime.fromisoformat(args.before).replace(tzinfo=timezone.utc)
        except:
            print("[!] Invalid --before format")
            sys.exit(1)

    # Run the scraping coroutine
    tweets = asyncio.run(scrape_user_tweets(cfg))

    # Save the results to file
    print(f"[+] Collected {len(tweets)} tweets")
    try:
        with open(cfg.output, "w", encoding="utf-8") as f:
            json.dump(tweets, f, indent=2)
        print(f"[+] Saved to {cfg.output}")
    except Exception as e:
        print(f"[!] Failed to save file: {e}")
