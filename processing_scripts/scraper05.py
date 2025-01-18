# write a program to read a URL provided by the user and extract the list of articles from the page and also extract the titles and dates from the URL; then go to 10 articles from the list that have content (with actual articles) to read URLs there as well to see if there are any new URLs not yet found and extract the titles and dates from those URLs as well. The output would be a spreadsheet to list all the articles with title, date and URL 

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import csv
import os

# Fetch and parse a webpage
def fetch_page(url):
    """
    Fetches and parses a webpage while ensuring proper encoding handling.
    """
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        return soup
    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

# Extract articles with titles, dates, and URLs
def extract_articles(soup, base_url):
    """
    Extracts articles from a page, returning a list of dictionaries with title, date, and URL.
    """
    articles = []
    for link in soup.find_all("a", href=True):
        title = link.get_text(strip=True)
        url = urljoin(base_url, link["href"])  # Make the URL absolute
        if title and url:
            # Attempt to extract a date from nearby elements (if available)
            date = None
            date_tag = link.find_previous_sibling("time") or link.find_next_sibling("time")
            if date_tag:
                date = date_tag.get_text(strip=True)

            articles.append({"title": title, "date": date, "url": url})
    return articles

# Extract content from a single article page
def extract_content(soup):
    """
    Extracts the main content of an article.
    """
    content = ""
    for tag in ["article", "section", "div"]:
        content_container = soup.find(tag)
        if content_container:
            paragraphs = content_container.find_all("p")
            if paragraphs:
                content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                break
    return content.strip()

# Write articles to a CSV file
def write_to_csv(articles, output_file):
    """
    Writes a list of articles to a CSV file.
    """
    with open(output_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["title", "date", "url"])
        writer.writeheader()
        writer.writerows(articles)

# Main program logic
def main():
    # Get the starting URL from the user
    start_url = input("Please enter the starting URL: ").strip()

    # Validate the URL
    if not start_url.startswith("http"):
        print("Invalid URL. Please make sure to include 'http://' or 'https://'.")
        return

    # Fetch the starting page and extract articles
    print(f"Fetching the starting URL: {start_url}")
    soup = fetch_page(start_url)
    if not soup:
        print("Failed to fetch the starting page. Exiting.")
        return

    print("Extracting articles from the starting page...")
    articles = extract_articles(soup, start_url)
    print(f"Found {len(articles)} articles.")

    # Track visited URLs to avoid revisiting
    visited_urls = set()
    visited_urls.add(start_url)

    # Prepare a list for final results
    final_results = []

    # Process up to 10 articles with actual content
    articles_with_content = 0
    for article in articles:
        if articles_with_content >= 10:
            break

        article_url = article["url"]
        if article_url in visited_urls:
            continue

        print(f"Fetching article URL: {article_url}")
        article_soup = fetch_page(article_url)
        if not article_soup:
            print(f"Failed to fetch article URL: {article_url}")
            continue

        # Extract the article content
        content = extract_content(article_soup)
        if not content:
            print(f"No meaningful content found for URL: {article_url}")
            continue

        # Add the article to the final results
        final_results.append(article)
        articles_with_content += 1
        visited_urls.add(article_url)

        # Extract additional URLs from the current article page
        print(f"Extracting additional articles from {article_url}...")
        additional_articles = extract_articles(article_soup, article_url)
        for additional_article in additional_articles:
            additional_url = additional_article["url"]
            if additional_url not in visited_urls:
                visited_urls.add(additional_url)
                articles.append(additional_article)  # Add to overall list

    # Save the results to a CSV file
    output_file = os.path.join(os.getcwd(), "articles.csv")
    print(f"Saving results to {output_file}...")
    write_to_csv(final_results, output_file)
    print("Done! All articles have been saved to the spreadsheet.")

if __name__ == "__main__":
    main()