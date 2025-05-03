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

UA_PATH = Path("user_agents.txt")
COOKIE_PATH = Path("x_cookies.json")

def get_random_user_agent(file_path="user_agents.txt"):
    try:
        lines = Path(file_path).read_text(encoding="utf-8").splitlines()
        return random.choice([ua.strip() for ua in lines if ua.strip()])
    except Exception:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

def get_random_lang():
    langs = ["en-US,en;q=0.9", "en-GB,en;q=0.8", "en;q=0.7"]
    return random.choice(langs)

# Full hydration to recover missing fields (likes, retweets, etc)
async def hydrate_full_tweet(tweet_id, page):
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
                    tweet_result = entry["content"]["itemContent"]["tweet_results"]["result"]
                    return tweet_result.get("legacy", {})
    except Exception:
        pass
    return None

def format_tweets_as_text(tweets):
    output = []
    for tweet in tweets:
        type_tag = "[Original]"
        if tweet.get("text", "").strip().startswith("RT @"):
            type_tag = "[Retweet]"
        elif tweet.get("in_reply_to_screen_name"):
            type_tag = "[Reply]"

        reply_info = "None"
        if tweet.get("in_reply_to_screen_name"):
            reply_info = f"@{tweet['in_reply_to_screen_name']}"
            if tweet.get("in_reply_to_user_id") and tweet.get("in_reply_to_status_id"):
                reply_info += f" (User ID: {tweet['in_reply_to_user_id']}, Status ID: {tweet['in_reply_to_status_id']})"

        media_info = "None"
        if tweet.get("media"):
            media_info = "\n".join([f"{m['type'].capitalize()}: {m['url']}" for m in tweet["media"]])

        mentions_info = ", ".join(tweet.get("mentions", [])) if tweet.get("mentions") else "None"
        hashtags_info = ", ".join(tweet.get("hashtags", [])) if tweet.get("hashtags") else "None"
        urls_info = ", ".join(tweet.get("urls", [])) if tweet.get("urls") else "None"

        tweet_text = (
            f"{type_tag}\n"
            f"Tweet ID: {tweet['id']}\n"
            f"Text: {tweet['text']}\n"
            f"Created At: {tweet['created_at']}\n"
            f"In Reply To: {reply_info}\n"
        )

        if tweet.get("likes"):
            tweet_text += f"Likes: {tweet['likes']}\n"
        if tweet.get("retweets"):
            tweet_text += f"Retweets: {tweet['retweets']}\n"
        if tweet.get("replies"):
            tweet_text += f"Replies: {tweet['replies']}\n"
        if tweet.get("bookmarks"):
            tweet_text += f"Bookmarks: {tweet['bookmarks']}\n"

        tweet_text += (
            f"Mentions: {mentions_info}\n"
            f"Hashtags: {hashtags_info}\n"
            f"URLs: {urls_info}\n"
            f"Media:\n{media_info}\n"
            f"----------------------------------------"
        )
        output.append(tweet_text)
    return "\n".join(output)

async def scrape_user_tweets(cfg):
    tweets = []
    seen_ids = set()
    cursor = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=cfg.headless)
        context = await browser.new_context(
            user_agent=get_random_user_agent(),
            locale=get_random_lang(),
            viewport={"width": 1280, "height": 800}
        )

        try:
            with open(COOKIE_PATH) as f:
                cookie_data = json.load(f)
            cookies = cookie_data if isinstance(cookie_data, list) else cookie_data.get("cookies", [])
            if not cookies:
                raise ValueError("No valid cookies found")
            await context.add_cookies(cookies)
            print("[DEBUG] Cookies loaded:", [c["name"] for c in cookies])
        except Exception as e:
            print(f"[!] Failed to load cookies: {e}")
            sys.exit(1)

        page = await context.new_page()

        async def handle_response(response):
            nonlocal cursor, tweets, seen_ids
            if "UserTweets" in response.url or "SearchTimeline" in response.url:
                try:
                    data = await response.json()
                    instructions = []
                    if "UserTweets" in response.url:
                        user_result = data.get("data", {}).get("user", {}).get("result", {})
                        possible_paths = [
                            user_result.get("timeline_v2", {}).get("timeline", {}).get("instructions"),
                            user_result.get("timeline", {}).get("timeline", {}).get("instructions"),
                            user_result.get("legacy", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions")
                        ]
                        for path in possible_paths:
                            if path:
                                instructions = path
                                break
                    else:
                        instructions = data.get("data", {}).get("search_by_raw_query", {}).get("search_timeline", {}).get("timeline", {}).get("instructions", [])

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

                                if dt:
                                    if cfg.since_after and dt < cfg.since_after:
                                        continue
                                    if cfg.before and dt >= cfg.before:
                                        continue

                                is_rt = full_text.strip().startswith("RT @")
                                is_rep = full_text.strip().startswith("@")
                                if cfg.type == "tweets" and (is_rt or is_rep):
                                    continue
                                if cfg.type == "retweets" and not is_rt:
                                    continue

                                # Full hydrate if missing engagement fields
                                if (
                                    legacy.get("favorite_count", 0) == 0 and
                                    legacy.get("retweet_count", 0) == 0 and
                                    legacy.get("reply_count", 0) == 0
                                ):
                                    hydrated_legacy = await hydrate_full_tweet(tweet_id, page)
                                    if hydrated_legacy:
                                        print(f"[DEBUG] Hydrated full legacy for {tweet_id}")
                                        legacy.update(hydrated_legacy)

                                reply_screen_name = legacy.get("in_reply_to_screen_name")
                                reply_user_id = legacy.get("in_reply_to_user_id_str")
                                reply_status_id = legacy.get("in_reply_to_status_id_str")
                                if not reply_screen_name and full_text.startswith("@"):
                                    match = re.match(r"@(\w+)", full_text)
                                    if match:
                                        reply_screen_name = match.group(1)
                                        reply_user_id = None
                                        reply_status_id = None

                                media = []
                                for entities_key in ["entities", "extended_entities"]:
                                    for m in legacy.get(entities_key, {}).get("media", []):
                                        if m["type"] == "photo":
                                            media.append({"type": "image", "url": m["media_url_https"]})
                                        elif m["type"] == "video" or m["type"] == "animated_gif":
                                            variants = m.get("video_info", {}).get("variants", [])
                                            best_variant = max(
                                                variants,
                                                key=lambda v: v.get("bitrate", 0),
                                                default={}
                                            )
                                            if best_variant.get("url"):
                                                media.append({"type": "video", "url": best_variant["url"]})

                                tweet_data = {
                                    "id": tweet_id,
                                    "text": full_text,
                                    "created_at": created_at
                                }

                                if reply_screen_name:
                                    tweet_data["in_reply_to_screen_name"] = reply_screen_name
                                if reply_user_id:
                                    tweet_data["in_reply_to_user_id"] = reply_user_id
                                if reply_status_id:
                                    tweet_data["in_reply_to_status_id"] = reply_status_id

                                if legacy.get("favorite_count", 0) > 0:
                                    tweet_data["likes"] = legacy.get("favorite_count", 0)
                                if legacy.get("retweet_count", 0) > 0:
                                    tweet_data["retweets"] = legacy.get("retweet_count", 0)
                                if legacy.get("bookmark_count", 0) > 0:
                                    tweet_data["bookmarks"] = legacy.get("bookmark_count", 0)
                                if legacy.get("reply_count", 0) > 0:
                                    tweet_data["replies"] = legacy.get("reply_count", 0)

                                if legacy.get("source", ""):
                                    tweet_data["source"] = legacy.get("source", "")

                                mentions = [m["screen_name"] for m in legacy.get("entities", {}).get("user_mentions", [])]
                                if mentions:
                                    tweet_data["mentions"] = mentions

                                urls = [u["expanded_url"] for u in legacy.get("entities", {}).get("urls", [])]
                                if urls:
                                    tweet_data["urls"] = urls

                                hashtags = [h["text"] for h in legacy.get("entities", {}).get("hashtags", [])]
                                if hashtags:
                                    tweet_data["hashtags"] = hashtags

                                if media:
                                    tweet_data["media"] = media

                                tweets.append(tweet_data)
                                seen_ids.add(tweet_id)
                                if len(tweets) >= cfg.max:
                                    return

                            elif eid.startswith("cursor-bottom"):
                                cursor = entry["content"]["value"]
                except Exception as e:
                    print(f"[!] JSON parse failed: {e}")

        page.on("response", handle_response)

        if cfg.since_after or cfg.before:
            query_parts = [f"from:{cfg.username}"]
            if cfg.since_after:
                since_date = cfg.since_after.strftime("%Y-%m-%d")
                query_parts.append(f"since:{since_date}")
            if cfg.before:
                before_date = cfg.before.strftime("%Y-%m-%d")
                query_parts.append(f"until:{before_date}")
            query = " ".join(query_parts)
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://x.com/search?q={encoded_query}&src=typed_query"
            await page.goto(search_url, timeout=60000)
            print(f"[DEBUG] Navigated to search: {search_url}")
            await page.click('text=Latest')
            print("[DEBUG] Clicked Latest tab")
            await page.wait_for_timeout(2000)
        else:
            await page.goto(f"https://x.com/{cfg.username}", timeout=60000)
            print(f"[DEBUG] Navigated to https://x.com/{cfg.username}")
            await page.wait_for_timeout(3000)

        # Scroll loop with early exit
        min_load_time = 2.0
        no_new_tweets_counter = 0
        for i in range(cfg.scrolls):
            print(f"[DEBUG] Scroll {i+1}")

            tweets_before_scroll = len(tweets)

            if len(tweets) >= cfg.max:
                print("[DEBUG] Reached max tweets limit.")
                break

            await page.wait_for_timeout(2000)
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(max(min_load_time, cfg.delay))

            tweets_after_scroll = len(tweets)

            if tweets_after_scroll == tweets_before_scroll:
                no_new_tweets_counter += 1
                print(f"[DEBUG] No new tweets after scroll ({no_new_tweets_counter}/3)")
            else:
                no_new_tweets_counter = 0

            if no_new_tweets_counter >= 3:
                print("[DEBUG] No new tweets after 3 attempts, exiting early.")
                break

        await browser.close()
        return tweets[:cfg.max]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape tweets from a user profile or search on X.com")
    parser.add_argument("--username", help="USERNAME", required=True, metavar='')
    parser.add_argument("--type", choices=["all", "tweets", "retweets"], default="all")
    parser.add_argument("--output", help="json or text output", metavar='')
    parser.add_argument("--since-after", help="Datetime format: YYYY-MM-DDTHH:MM:SS", metavar='')
    parser.add_argument("--before", help="Datetime format: YYYY-MM-DDTHH:MM:SS")
    parser.add_argument("--no-headless", help="shows browser", dest="headless", action="store_false")
    parser.add_argument("--scrolls", help="default 30 scrolls", type=int, default=30, metavar='')
    parser.add_argument("--max", help="default 50 tweets", type=int, default=50, metavar='')
    parser.add_argument("--delay", help="delay between scrolls in seconds (default: 2)", type=float, default=2.0, metavar='')
    args = parser.parse_args()

    class Config: pass
    cfg = Config()
    cfg.username = args.username
    cfg.type = args.type
    cfg.output = args.output or f"{cfg.username}.json"
    cfg.headless = args.headless
    cfg.scrolls = args.scrolls
    cfg.max = args.max
    cfg.since_after = None
    cfg.delay = args.delay
    cfg.before = None

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

    tweets = asyncio.run(scrape_user_tweets(cfg))

    print(f"[+] Collected {len(tweets)} tweets")
    try:
        with open(cfg.output, "w", encoding="utf-8") as f:
            if cfg.output.lower().endswith('.txt'):
                f.write(format_tweets_as_text(tweets))
            else:
                json.dump(tweets, f, indent=2, ensure_ascii=False)
        print(f"[+] Saved to {cfg.output}")
    except Exception as e:
        print(f"[!] Failed to save file: {e}")