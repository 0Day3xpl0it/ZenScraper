#!/usr/bin/env python3

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

# Cookies required for authenticated scraping
REQUIRED_COOKIE_NAMES = {"auth_token", "ct0", "twid"}

def save_auth_cookies(output_path="x_cookies.json"):
    with sync_playwright() as p:
        print("[*] Launching Playwright's Chromium...")
        
        # This will use Playwright's bundled Chromium
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )

        # Create a new context (like a fresh browser profile)
        context = browser.new_context()
        page = context.new_page()
        
        print("[*] Navigating to https://x.com/home")
        page.goto("https://x.com/home", wait_until="domcontentloaded")

        input("[*] Once you're fully logged in and the X homepage is visible, press ENTER... ")

        print("[*] Extracting auth cookies...")
        cookies = context.cookies()
        auth_cookies = [
            c for c in cookies
            if ".x.com" in c["domain"] and c["name"] in REQUIRED_COOKIE_NAMES
        ]

        if len(auth_cookies) < 3:
            print("[!] Warning: Missing one or more required cookies (auth_token, ct0, twid)")

        Path(output_path).write_text(json.dumps({"cookies": auth_cookies}, indent=2), encoding="utf-8")
        print(f"[+] Saved minimal auth cookies to {output_path}")

        context.close()
        browser.close()

if __name__ == "__main__":
    save_auth_cookies()