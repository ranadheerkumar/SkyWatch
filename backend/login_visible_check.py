import argparse
import asyncio
from getpass import getpass
import sys

from playwright.async_api import async_playwright


def _load_secrets() -> tuple[str, str]:
    email = input("Login email: ").strip()
    password = getpass("Login password: ")
    if not email or not password:
        raise RuntimeError("Login email and password are required.")
    return email, password


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open an application login page in a visible browser and login.")
    parser.add_argument(
        "--target-url",
        required=True,
        help="Login URL.",
    )
    parser.add_argument(
        "--keep-open-seconds",
        type=int,
        default=30,
        help="Keep the browser window open for this many seconds after login completes. Default: 30",
    )
    parser.add_argument("--email-selector", default="#user_email", help="CSS selector for the email field.")
    parser.add_argument("--password-selector", default="#user_password", help="CSS selector for the password field.")
    parser.add_argument("--submit-selector", default="input[type='submit']", help="CSS selector for the submit control.")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    target_url = args.target_url.strip()
    email, password = _load_secrets()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)

            await page.locator(args.email_selector).fill(email)
            await page.locator(args.password_selector).fill(password)
            await page.locator(args.submit_selector).click()

            await page.wait_for_load_state("networkidle", timeout=25_000)
            print(f"Page title: {await page.title()}")
            print(f"Final URL: {page.url}")

            if args.keep_open_seconds > 0:
                print(f"Keeping browser open for {args.keep_open_seconds} seconds for inspection...")
                await page.wait_for_timeout(args.keep_open_seconds * 1000)
        finally:
            await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"Login check failed: {exc}", file=sys.stderr)
        raise
