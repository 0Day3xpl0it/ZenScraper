# ZenScraper

ZenScraper is an asynchronous scraper built with PlayWright and json designed for efficiently retrieving tweets from X.com (formerly Twitter). It supports scraping original tweets, retweets, and filtering tweets by date.

## Key Features

- **Flexible Scraping:** Choose to scrape original tweets, retweets, or both.
- **Date Filtering:** Filter tweets based on specific date ranges (`--since-after`, `--before`).
- **Session Authentication:** Uses cookies for authenticated scraping sessions.
- **Configurable Output:** Outputs scraped data to JSON format with structured metadata or a cleaned text format.
- **Headless or Visible Mode:** Operate in headless mode for automation or visible mode for debugging.

## Requirements

- Python 3.8 or newer
- [Playwright](https://playwright.dev)

## Installation

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/0Day3xpl0it/zenscraper.git
cd zenscraper
chmod +x *.py
pip install -r requirements.txt
playwright install
```

Next, generate an authenticated session cookie:

```bash
python3 grab_x_cookies.py
```

This script will create the `x_cookies.json` file necessary for authenticated scraping.

## Usage

Basic command structure:

```bash
python3 zenscraper.py --username <username> [options]
```

### Example with Time Filters

Scrape tweets from the @elonmusk account within a specific date range:

```bash
python3 zenscraper.py --username elonmusk --since-after 2025-01-01T00:00:00 --before 2025-02-01T00:00:00 --type tweets --output elonmusk_jan.json --scrolls 40 --max 200
```

This command collects up to 200 original tweets from January 2025, saving the output to elonmusk`_jan.json`.

## Command-Line Options

| Option          | Description                                  | Default Value       |
| --------------- | -------------------------------------------- | ------------------- |
| `--username`    | **(Required)** X.com username to scrape      | -                   |
| `--type`        | Content type: `tweets`, `retweets`, `bio`, or `all` | `all`               |
| `--output`      | Output file (.json or .txt)                  | `<username>.json`   |
| `--since-after` | Include tweets after this date (ISO 8601)    | None                |
| `--before`      | Include tweets before this date (ISO 8601)   | None                |
| `--scrolls`     | Number of scroll actions                     | 30                  |
| `--max`         | Maximum tweets to retrieve                   | 50                  |
| `--no-headless` | Display browser during scraping              | Headless by default |
| `--delay`       | Add delay for throttling                     | 2                   | 

## TODO

- Add functionality to expand full text for tweets and retweets (complete - 5/8/25)
- Add functionality to retrieve additional tweet data types (complete - 5/8/25)
- Add functionality to grab all user bio datacomplete - (5/9/25)
- Add functionality to effectively grab replies and thread them to parent conversations

## Important Notes

- A valid `x_cookies.json` file is required for authenticated scraping.
- Include multiple user-agent strings in `user_agents.txt` for request rotation.
- Date options do not currently work with retweets as the X search function doesn't show retweets.
- The scraper leverages asynchronous Playwright operations for optimal speed and efficiency.
- It is recommended to use a backup X account to perform scraping activities to prevent issues. 

## Contributing

Contributions are welcome! Open an issue or submit a pull request for improvements.

## License

ZenScraper is licensed under the MIT License. See [LICENSE](LICENSE) for details.

