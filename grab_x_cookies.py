#!/usr/bin/env python3

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

# Cookies required for authenticated scraping
REQUIRED_COOKIE_NAMES = {"auth_token", "ct0", "twid"}
LOGIN_SCENARIOS = {
            "suspicious_login": {
                "selector": "//*[contains(text(), 'Suspicious login prevented')]",
                "action": "click",
                "action_selector": "//*[contains(text(), 'Got it')]"
            },
            "authentication_code": {
                "selector": "//*[contains(text(), 'Enter code')]",
                "action": "input",
                "prompt_message": "Enter 2FA code:",
                "next_button": "//*[contains(text(), 'Next')]"
            },
            "email_verification": {
                "selector": "//*[contains(text(), 'Confirmation code')]",
                "action": "input",
                "prompt_message": "Enter email verification code:",
                "next_button": "//*[contains(text(), 'Next')]"
            },
            "phone-email": {
                "selector": "//*[contains(text(), 'Phone or email')]",
                "action": "input",
                "prompt_message": "Enter email or phone number:",
                "next_button": "//*[contains(text(), 'Next')]"
            },
            "phone_verification": {
                "selector": "//*[contains(text(), 'Verify your phone')]",
                "action": "input",
                "prompt_message": "Enter phone verification code:",
                "next_button": "//*[contains(text(), 'Next')]"
            },
            "phone_verify_identity": {
                "selector": "//*[contains(text(), 'Phone number')]",
                "action": "input",
                "prompt_message": "Enter the phone number",
                "next_button": "//*[contains(text(), 'Next')]"
            },
        }
LOGIN_URL = "https://x.com/login"


def save_auth_cookies(username, password, output_path="x_cookies.json"):
    """
    A simple Playwright script that navigates to Twitter/X, logs in with provided credentials,
    handles various login scenarios, and saves cookies.
    
    Args:
        username (str): Twitter username, email, or phone
        password (str): Twitter password
    """
    with sync_playwright() as p:
        print("[*] Launching Playwright's Chromium...")
        
        # This will use Playwright's bundled Chromium
        browser = p.chromium.launch(headless=False)

        # Create a new context (like a fresh browser profile)
        context = browser.new_context()
        page = context.new_page()

        def check_scenarios():
            """
            Check for and handle various login scenarios
            Returns a tuple of (scenario_detected, needs_input, scenario_info)
            """
            for name, scenario in LOGIN_SCENARIOS.items():
                try:
                    print(f"Checking for {name}...")
                    element = page.wait_for_selector(
                        scenario["selector"], 
                        state="visible", 
                        timeout=1000
                    )
                    print(f"Detected {name}")

                    if scenario["action"] == "click":
                        action_element = page.wait_for_selector(
                            scenario["action_selector"], 
                            state="visible", 
                            timeout=1000
                        )
                        action_element.click()
                        print(f"Clicked {scenario['action_selector']}")
                        # Return info about scenario but doesn't need input
                        return True, False, None

                    elif scenario["action"] == "input":
                        # If there's a specific input selector, use that instead of the detected element
                        input_element = element
                        if "input_selector" in scenario:
                            input_element = page.wait_for_selector(
                                scenario["input_selector"], 
                                state="visible", 
                                timeout=1000
                            )
                            print(f"Found input element using selector: {scenario['input_selector']}")

                        # Get user input for this scenario
                        user_input = input(scenario["prompt_message"] + " ")
                        
                        # Fill the input field
                        input_element.fill(user_input)
                        print(f"Entered user input for {name}")
                        
                        # Click next button if available
                        if scenario.get("next_button"):
                            next_btn = page.wait_for_selector(
                                scenario["next_button"],
                                state="visible",
                                timeout=1000
                            )
                            next_btn.click()
                            print(f"Clicked next button for {name}")
                        
                        return True, True, None

                except Exception as e:
                    print(f"Scenario check error ({name}): {e}")
                    continue

            # No scenarios detected
            return False, False, None
        
        print(f"[*] Navigating to {LOGIN_URL}")
        page.goto(LOGIN_URL)

        page.wait_for_load_state("networkidle")

        # Find and fill username field
        username_input = page.wait_for_selector(
            "//*[contains(text(), 'Phone, email, or username')]",
            state="visible",
            timeout=10000
        )
        print(f"Found username input, inserting {username}")
        username_input.fill(username)

        # Click Next button
        next_button = page.wait_for_selector(
            "//*[contains(text(), 'Next')]",
            state="visible",
            timeout=10000
        )
        next_button.click()
        print("Entered username and clicked next")

        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

        # Check for scenarios after username entry
        print("Checking for scenarios after username entry...")
        scenario_detected, needs_input, _ = check_scenarios()
        if scenario_detected:
            print("Handled post-username scenario")
        
        # Continue to password if no blocking scenario
        if not scenario_detected or needs_input:
            # Find and fill password field
            password_input = page.wait_for_selector(
                "//*[contains(text(), 'Password')]",
                state="visible",
                timeout=10000
            )
            password_input.fill(password)
            print("Entered password")

            # Click Login button
            login_button = page.wait_for_selector(
                "//button[@data-testid='LoginForm_Login_Button']",
                state="visible",
                timeout=10000
            )
            login_button.click()
            print("Clicked login button")

            # Wait a bit for login to complete
            page.wait_for_timeout(3000)
            
            # Check for scenarios after login attempt
            print("Checking for scenarios after login attempt...")
            scenario_detected, needs_input, _ = check_scenarios()
            if scenario_detected:
                print("Handled post-login scenario")
        
        print("Login process completed, waiting on Twitter...")

        page.wait_for_timeout(3000)

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
    save_auth_cookies(username="your_username", password="your_password")
    