#!/usr/bin/env python3

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

# Update this to your browser's user profile path
CHROME_USER_DATA_DIR = "/home/anon/.config/chromium"  # or "google-chrome" / "Brave-Browser"

# Cookies required for authenticated scraping
REQUIRED_COOKIE_NAMES = {"auth_token", "ct0", "twid"}

def save_auth_cookies(output_path="x_cookies.json"):
    with sync_playwright() as p:
        print("[*] Launching browser with user profile...")

        browser = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_USER_DATA_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )

        page = browser.new_page()
        print("[*] Navigating to https://x.com/home")
        page.goto("https://x.com/home", wait_until="domcontentloaded")

        input("[*] Once you're fully logged in and the X homepage is visible, press ENTER... ")

        print("[*] Extracting auth cookies...")
        cookies = browser.cookies()
        auth_cookies = [
            c for c in cookies
            if ".x.com" in c["domain"] and c["name"] in REQUIRED_COOKIE_NAMES
        ]

        if len(auth_cookies) < 3:
            print("[!] Warning: Missing one or more required cookies (auth_token, ct0, twid)")

        Path(output_path).write_text(json.dumps({"cookies": auth_cookies}, indent=2), encoding="utf-8")
        print(f"[+] Saved minimal auth cookies to {output_path}")

        browser.close()

if __name__ == "__main__":
    save_auth_cookies()
