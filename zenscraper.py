#!/usr/bin/env python3
# ZenScraper created by 0Day3xpl0it

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

UA_PATH     = Path("user_agents.txt")
COOKIE_PATH = Path("x_cookies.json")

# Fetches a random user agent from a file for browser requests
def get_random_user_agent(file_path="user_agents.txt"):
    try:
        lines = Path(file_path).read_text(encoding="utf-8").splitlines()
        return random.choice([ua.strip() for ua in lines if ua.strip()])
    except Exception:
        return ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")

# Selects a random language code for browser requests
def get_random_lang():
    return random.choice(["en-US,en;q=0.9", "en-GB,en;q=0.8", "en;q=0.7"])

# Fetches detailed tweet data when engagement counts are zero
async def hydrate_full_tweet(tweet_id, page, original_legacy=None):
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
        q = urllib.parse.quote(json.dumps(variables))
        url = ("https://x.com/i/api/graphql/TweetDetailID/"
               f"TweetDetail?variables={q}")
        r = await page.request.get(url)
        if r.status != 200:
            print(f"[!] Hydration failed for tweet {tweet_id}: HTTP {r.status}")
            return original_legacy
        data = await r.json()
        instrs = (
            data.get("data", {})
                .get("threaded_conversation_with_injections_v2", {})
                .get("instructions", [])
        )
        for instr in instrs:
            for entry in instr.get("entries", []):
                if entry.get("entryId", "").startswith("tweet-"):
                    res = entry["content"]["itemContent"]["tweet_results"]["result"]
                    await asyncio.sleep(0.5)  # Delay to avoid rate limiting
                    return res.get("legacy", {})
        print(f"[!] Hydration failed for tweet {tweet_id}: No tweet entry found")
        return original_legacy
    except Exception as e:
        print(f"[!] Hydration failed for tweet {tweet_id}: {str(e)}")
        return original_legacy

# Formats tweet data as plain text for output
def format_tweets_as_text(tweets):
    lines = []
    for t in tweets:
        tag = "[Original]"
        if t.get("retweet_full_text") is not None:
            tag = "[Retweet]"
        elif t.get("text", "").strip().startswith("RT @"):
            tag = "[Retweet]"
        elif t.get("parent"):
            tag = "[Reply]"

        media_block = "None"
        if t.get("media"):
            media_block = "\n".join(f"{m['type'].capitalize()}: {m['url']}"
                                    for m in t["media"])

        expanded_urls_block = "None"
        if t.get("expanded_urls"):
            expanded_urls_block = "\n".join(t["expanded_urls"])

        tweet_lines = [
            f"{tag}",
            f"ID: {t['id']}",
            f"URL: {t['url']}",
        ]
        if t.get("text") is not None:
            tweet_lines.append(f"Text: {t['text']}")
        elif t.get("retweet_full_text") is not None:
            tweet_lines.append(f"Retweet Full Text: {t['retweet_full_text']}")
        tweet_lines.extend([
            f"Created: {t.get('created_at','?')}",
            f"Parent: {t.get('parent')}",
            f"Parent URL: {t.get('parent_url')}",
            f"Likes: {t.get('likes') or t.get('favorite_count')}",
            f"Retweets: {t.get('retweets') or t.get('retweet_count')}",
            f"Replies: {t.get('replies')}",
            f"Media:\n{media_block}",
            f"Expanded URLs:\n{expanded_urls_block}",
            "----------------------------------------"
        ])
        lines.append("\n".join(tweet_lines))
    return "\n".join(lines)

# Scrapes tweets or retweets from a user's timeline
async def scrape_user_tweets(cfg):
    tweets, seen_ids, cursor = [], set(), None
    tco_cache = {}  # Cache for resolved t.co links

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=cfg.headless)
        context = await browser.new_context(
            user_agent=get_random_user_agent(),
            locale=get_random_lang(),
            viewport={"width": 1280, "height": 800}
        )

        try:
            with open(COOKIE_PATH) as fh:
                cookie_data = json.load(fh)
            cookies = cookie_data if isinstance(cookie_data, list) else cookie_data.get("cookies", [])
            await context.add_cookies(cookies)
        except Exception as e:
            print(f"[!] Cookie error: {e}. Please update x_cookies.json with valid cookies.")
            sys.exit(1)

        page = await context.new_page()

        async def handle_response(response):
            nonlocal cursor
            if "UserTweets" in response.url or "SearchTimeline" in response.url:
                try:
                    data = await response.json()
                    instructions = []

                    if "UserTweets" in response.url:
                        user_result = data.get("data", {}).get("user", {}).get("result", {})
                        for pth in (
                            user_result.get("timeline_v2", {}).get("timeline", {}).get("instructions"),
                            user_result.get("timeline", {}).get("timeline", {}).get("instructions"),
                            user_result.get("legacy", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions"),
                        ):
                            if pth:
                                instructions = pth
                                break
                    else:  # SearchTimeline
                        instructions = (
                            data.get("data", {})
                                .get("search_by_raw_query", {})
                                .get("search_timeline", {})
                                .get("timeline", {})
                                .get("instructions", [])
                        )

                    for instr in instructions:
                        for entry in instr.get("entries", []):
                            eid = entry.get("entryId", "")
                            if eid.startswith("tweet-"):
                                t = entry["content"]["itemContent"]["tweet_results"]["result"]
                                tweet_id = t.get("rest_id")
                                if not tweet_id or tweet_id in seen_ids:
                                    print(f"[!] Skipping tweet {tweet_id}: Already processed or invalid ID")
                                    continue
                                seen_ids.add(tweet_id)

                                legacy = t.get("legacy", {})
                                # Hydration for UserTweets only
                                if "UserTweets" in response.url and (
                                    legacy.get("favorite_count", 0) == 0 and
                                    legacy.get("retweet_count", 0) == 0 and
                                    legacy.get("reply_count", 0) == 0
                                ):
                                    hyd = await hydrate_full_tweet(tweet_id, page)
                                    if hyd:
                                        legacy.update(hyd)
                                    else:
                                        print(f"[!] Skipping tweet {tweet_id}: Hydration failed")
                                        continue

                                # Handle note_tweet for extended text
                                note_text = (
                                    t.get("note_tweet", {})
                                    .get("note_tweet_results", {})
                                    .get("result", {})
                                    .get("text", "")
                                )
                                full_text = re.sub(r"\s+", " ", (note_text or legacy.get("full_text", ""))).strip()

                                # Handle retweets
                                orig_full_text = ""
                                rt_legacy = None
                                if full_text.startswith("RT @"):
                                    rt_status = legacy.get("retweeted_status_result", {}).get("result", {})
                                    if rt_status:
                                        rt_legacy = rt_status.get("legacy", {})
                                        rt_note = (
                                            rt_status.get("note_tweet", {})
                                            .get("note_tweet_results", {})
                                            .get("result", {})
                                            .get("text", "")
                                        )
                                        orig_full_text = re.sub(r"\s+", " ", (rt_note or rt_legacy.get("full_text", ""))).strip()
                                    if not orig_full_text and "UserTweets" in response.url:
                                        orig_id = legacy.get("retweeted_status_id_str")
                                        if orig_id:
                                            hyd_orig = await hydrate_full_tweet(orig_id, page)
                                            if hyd_orig:
                                                note_body = (
                                                    hyd_orig.get("note_tweet", {})
                                                        .get("note_tweet_results", {})
                                                        .get("result", {})
                                                        .get("text", "")
                                                )
                                                orig_full_text = re.sub(r"\s+", " ", (note_body or hyd_orig.get("full_text", ""))).strip()
                                                rt_legacy = hyd_orig

                                is_rt = full_text.startswith("RT @")
                                is_rep = full_text.startswith("@")

                                if cfg.type == "tweets" and (is_rt or is_rep):
                                    continue
                                if cfg.type == "retweets" and not is_rt:
                                    continue

                                # Filter retweets: show only text or retweet_full_text
                                text_value = full_text
                                retweet_full_text = None
                                if is_rt and orig_full_text:
                                    # Strip 'RT @username:' from text
                                    stripped_text = re.sub(r"^RT @[^:]+:\s*", "", full_text).strip()
                                    # If orig_full_text provides more data, use it and exclude text
                                    if orig_full_text != stripped_text and len(orig_full_text) > len(stripped_text):
                                        text_value = None
                                        retweet_full_text = orig_full_text
                                    else:
                                        text_value = full_text
                                        retweet_full_text = None
                                elif not is_rt:
                                    # Non-retweets: include text, exclude retweet_full_text
                                    text_value = full_text
                                    retweet_full_text = None

                                # Determine tweet type for display
                                tag = "[Original]"
                                if retweet_full_text is not None:
                                    tag = "[Retweet]"
                                elif full_text.startswith("RT @"):
                                    tag = "[Retweet]"
                                elif legacy.get("in_reply_to_status_id_str"):
                                    tag = "[Reply]"

                                # Display progress: Truncate text to 50 characters for readability
                                display_text = (text_value or retweet_full_text or "No text")
                                if len(display_text) > 50:
                                    display_text = display_text[:47] + "..."
                                print(f"Scraping tweet {tweet_id} {tag}: {display_text}")

                                # Extract media (use retweeted tweet's legacy for retweets)
                                media = []
                                seen_urls = set()
                                media_source = rt_legacy if is_rt and rt_legacy else legacy
                                for key in ("extended_entities", "entities"):
                                    for m in media_source.get(key, {}).get("media", []):
                                        if m["type"] == "photo":
                                            url = m["media_url_https"]
                                            if url not in seen_urls:
                                                media.append({"type": "image", "url": url})
                                                seen_urls.add(url)
                                        elif m["type"] in ("video", "animated_gif"):
                                            best = max(
                                                m.get("video_info", {}).get("variants", []),
                                                key=lambda v: v.get("bitrate", 0),
                                                default={}
                                            )
                                            url = best.get("url")
                                            if url and url not in seen_urls:
                                                media.append({"type": "video", "url": url})
                                                seen_urls.add(url)

                                # Extract expanded URLs from both legacy and rt_legacy (if retweet)
                                expanded_urls = []
                                seen_expanded_urls = set()
                                # First, check the retweeting tweet's legacy (where full_text comes from)
                                for key in ("extended_entities", "entities"):
                                    urls = legacy.get(key, {}).get("urls", [])
                                    for u in urls:
                                        expanded_url = u.get("expanded_url")
                                        if expanded_url and expanded_url not in seen_expanded_urls:
                                            expanded_urls.append(expanded_url)
                                            seen_expanded_urls.add(expanded_url)
                                # Then, check the retweeted tweet's rt_legacy (if applicable)
                                if is_rt and rt_legacy:
                                    for key in ("extended_entities", "entities"):
                                        urls = rt_legacy.get(key, {}).get("urls", [])
                                        for u in urls:
                                            expanded_url = u.get("expanded_url")
                                            if expanded_url and expanded_url not in seen_expanded_urls:
                                                expanded_urls.append(expanded_url)
                                                seen_expanded_urls.add(expanded_url)

                                # Fallback: If no expanded URLs found, resolve t.co links
                                if not expanded_urls:
                                    text_to_check = (text_value or "") + (" " + retweet_full_text if retweet_full_text else "")
                                    tco_links = re.findall(r"https://t\.co/[a-zA-Z0-9]+", text_to_check)
                                    for tco_url in tco_links:
                                        if tco_url not in seen_expanded_urls:
                                            if tco_url in tco_cache:
                                                expanded_url = tco_cache[tco_url]
                                            else:
                                                try:
                                                    response = await page.request.get(tco_url, max_redirects=10)
                                                    expanded_url = response.url
                                                    tco_cache[tco_url] = expanded_url
                                                    await asyncio.sleep(0.1)  # Reduced delay
                                                except Exception as e:
                                                    print(f"[!] Failed to resolve t.co URL {tco_url} for tweet {tweet_id}: {str(e)}")
                                                    continue
                                            if expanded_url and expanded_url not in seen_expanded_urls:
                                                expanded_urls.append(expanded_url)
                                                seen_expanded_urls.add(expanded_url)

                                # Construct URLs
                                tweet_url = f"https://x.com/{cfg.username}/status/{tweet_id}"
                                parent_id = legacy.get("in_reply_to_status_id_str", None)
                                parent_url = f"https://x.com/{cfg.username}/status/{parent_id}" if parent_id else None

                                # Normalize tweet data
                                tweet_data = {
                                    "id": tweet_id,
                                    "text": text_value,
                                    "retweet_full_text": retweet_full_text,
                                    "created_at": legacy.get("created_at", "unknown"),
                                    "likes": legacy.get("favorite_count", 0),
                                    "retweets": legacy.get("retweet_count", 0),
                                    "replies": legacy.get("reply_count", 0),
                                    "bookmarks": legacy.get("bookmark_count", 0),
                                    "media": media,
                                    "expanded_urls": expanded_urls,
                                    "parent": parent_id,
                                    "url": tweet_url,
                                    "parent_url": parent_url
                                }
                                tweets.append(tweet_data)
                                if len(tweets) >= cfg.max:
                                    return

                            elif eid.startswith("cursor-bottom"):
                                cursor = entry["content"]["value"]
                except Exception as e:
                    print(f"[!] Error processing response: {str(e)}")

        page.on("response", handle_response)

        if cfg.since_after or cfg.before:
            q_parts = [f"from:{cfg.username}"]
            if cfg.since_after:
                q_parts.append(f"since:{cfg.since_after.strftime('%Y-%m-%d')}")
            if cfg.before:
                q_parts.append(f"until:{cfg.before.strftime('%Y-%m-%d')}")
            q = urllib.parse.quote(" ".join(q_parts))
            url = f"https://x.com/search?q={q}&src=typed_query"
            await page.goto(url, timeout=60000)
            await page.click("text=Latest")
        else:
            await page.goto(f"https://x.com/{cfg.username}", timeout=60000)

        no_new = 0
        for _ in range(cfg.scrolls):
            if len(tweets) >= cfg.max:
                break
            prev_count = len(tweets)
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(max(2, cfg.delay))
            if len(tweets) == prev_count:
                no_new += 1
            else:
                no_new = 0
            if no_new >= 3:
                break

        # Sort tweets by created_at (newest to oldest)
        try:
            tweets.sort(
                key=lambda t: datetime.strptime(t["created_at"], "%a %b %d %H:%M:%S %z %Y"),
                reverse=True
            )
        except ValueError as e:
            print(f"[!] Error sorting tweets by date: {e}")

        await browser.close()
        return tweets[:cfg.max]

# Parses arguments and runs the scraper
if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Scrape tweets / retweets from X.com",
        formatter_class=argparse.RawTextHelpFormatter
    )
    ap.add_argument(
        "--username",
        required=True,
        help="(Required) X.com username to scrape"
    )
    ap.add_argument(
        "--type",
        choices=["all", "tweets", "retweets"],
        default="all",
        help="Content type: tweets, retweets, or all (default: all)"
    )
    ap.add_argument(
        "--output",
        help="Output file (.json or .txt) (default: <username>.json)"
    )
    ap.add_argument(
        "--since-after",
        help="Include tweets after this date (ISO 8601)"
    )
    ap.add_argument(
        "--before",
        help="Include tweets before this date (ISO 8601)"
    )
    ap.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Display browser during scraping (default: headless)"
    )
    ap.add_argument(
        "--scrolls",
        type=int,
        default=30,
        help="Number of scroll actions (default: 30)"
    )
    ap.add_argument(
        "--max",
        type=int,
        default=50,
        help="Maximum tweets to retrieve (default: 50)"
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Add delay for throttling (default: 2)"
    )
    args = ap.parse_args()

    class Cfg: pass
    cfg = Cfg()
    cfg.username = args.username
    cfg.type     = args.type
    cfg.output   = args.output
    cfg.headless = args.headless
    cfg.scrolls  = args.scrolls
    cfg.max      = args.max
    cfg.delay    = args.delay
    cfg.since_after = None
    cfg.before   = None
    if args.since_after:
        cfg.since_after = datetime.fromisoformat(args.since_after).replace(tzinfo=timezone.utc)
    if args.before:
        cfg.before = datetime.fromisoformat(args.before).replace(tzinfo=timezone.utc)

    result = asyncio.run(scrape_user_tweets(cfg))
    default_name = f"{cfg.username}.json"

    out_file = cfg.output or default_name
    print(f"[+] Collected {len(result)} items")

    try:
        with open(out_file, "w", encoding="utf-8") as fh:
            if out_file.lower().endswith(".txt"):
                fh.write(format_tweets_as_text(result))
            else:
                json.dump(result, fh, indent=2, ensure_ascii=False)
        print(f"[+] Saved → {out_file}")
    except Exception as e:
        print(f"[!] Write failed: {e}")