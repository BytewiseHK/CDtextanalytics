import requests
from bs4 import BeautifulSoup
import os
import random
import re
from urllib.parse import urljoin

# Fetch and parse a webpage
def fetch_page(url):
    """
    Fetches and parses a webpage while ensuring proper encoding handling.
    """
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
        response.encoding = response.apparent_encoding  # Detect and set proper encoding
        soup = BeautifulSoup(response.text, "html.parser")
        return soup
    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

# Extract articles with titles, URLs, and dates
def extract_articles(soup, base_url):
    """
    Extracts links (articles) with their titles and dates from a webpage.
    """
    articles = []
    for link in soup.find_all("a", href=True):
        title = link.get_text(strip=True)
        url = urljoin(base_url, link["href"])  # Convert to absolute URL
        if title and url:
            # Attempt to extract a date from nearby tags (if available)
            date = None
            date_tag = link.find_previous_sibling("time") or link.find_next_sibling("time")
            if date_tag:
                date = date_tag.get_text(strip=True)
            articles.append({"title": title, "date": date, "url": url})
    return articles

# Extract content from an article page
def extract_content(soup):
    """
    Extracts the title, date, and main content from an article webpage.
    """
    try:
        title = soup.find("title").get_text(strip=True) if soup.find("title") else "No title found"
        date = None
        # Attempt to extract the date from <time> or similar tags
        date_tag = soup.find("time")
        if date_tag:
            date = date_tag.get_text(strip=True)

        # Attempt to find the main content
        content = ""
        for tag in ["article", "section", "div"]:
            content_container = soup.find(tag)
            if content_container:
                paragraphs = content_container.find_all("p")
                if paragraphs:
                    content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                    break
        if not content:
            paragraphs = soup.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

        return {"title": title, "date": date, "content": content.strip()}
    except Exception as e:
        print(f"Error extracting content: {e}")
        return None

# Create a unique folder for saving results
def create_results_folder(base_path, base_url):
    """
    Creates a results folder inside the specified base path.
    The folder name is based on the provided URL and a random number.
    """
    random_number = random.randint(1000, 9999)
    folder_name = base_url.replace("https://", "").replace("http://", "").replace("/", "_")
    folder_name = folder_name[:50]  # Limit folder name length
    full_folder_name = f"{folder_name}_{random_number}"
    output_folder = os.path.join(base_path, full_folder_name)
    os.makedirs(output_folder, exist_ok=True)
    return output_folder

# Sanitize strings for safe file names
def sanitize_filename(name):
    """
    Sanitizes a string to make it safe for use as a file name.
    """
    if name is None:
        name = "Unknown"  # Default value for None
    return re.sub(r'[\/:*?"<>|]', '_', name)

# Write content to a text file
def save_content_to_file(content, output_folder):
    """
    Saves the extracted article content to a text file.
    """
    title = content.get("title", "Untitled")
    date = content.get("date", "UnknownDate")
    title_safe = sanitize_filename(title)
    date_safe = sanitize_filename(date)
    filename = f"{title_safe}_{date_safe}.txt"
    file_path = os.path.join(output_folder, filename)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"Title: {content['title']}\n")
            f.write(f"Date: {content['date']}\n")
            f.write(f"URL: {content['url']}\n\n")
            f.write(content['content'])
    except Exception as e:
        print(f"Error saving content to file: {e}")

# Main function
def main():
    # Input: Get the starting URL from the user
    start_url = input("Please enter the starting URL: ").strip()
    try:
        batch_size = int(input("Enter the number of URLs to process in the first batch: ").strip())
    except ValueError:
        print("Invalid input. Please enter a valid number.")
        return

    # Validate the URL
    if not start_url.startswith("http"):
        print("Invalid URL. Please make sure to include 'http://' or 'https://'.")
        return

    # Create a results folder
    base_path = "/workspaces/CDtextanalytics/processing_scripts/crawl_results"
    output_folder = create_results_folder(base_path, start_url)
    print(f"Results will be saved in: {output_folder}")

    # Initialize variables
    discovered_urls = set()  # Track all discovered URLs
    discovered_urls.add(start_url)
    to_visit_urls = [start_url]  # URLs to visit
    visited_urls = set()  # Track visited URLs
    urls_processed = 0  # Counter for the number of processed URLs

    # Start crawling
    while to_visit_urls:
        # Get the next URL to visit
        current_url = to_visit_urls.pop(0)
        if current_url in visited_urls:
            continue

        print(f"\nFetching URL: {current_url}")
        soup = fetch_page(current_url)
        if not soup:
            print(f"Failed to fetch {current_url}. Skipping.")
            continue

        # Mark the URL as visited
        visited_urls.add(current_url)

        # Check if the current page has actual content
        content = extract_content(soup)
        if content and content["content"]:
            content["url"] = current_url
            print(f"Found article: {content['title']}")
            save_content_to_file(content, output_folder)
        else:
            print(f"No meaningful content found at {current_url}.")

        # Extract new URLs from the current page
        print("Extracting links...")
        articles = extract_articles(soup, current_url)
        for article in articles:
            article_url = article["url"]
            if article_url not in discovered_urls:
                discovered_urls.add(article_url)
                to_visit_urls.append(article_url)

        # Increment the processed URLs counter
        urls_processed += 1
        print(f"Processed {urls_processed} URLs.")

        # Check if the batch size limit is reached
        if urls_processed % batch_size == 0:
            print(f"\nProcessed {urls_processed} URLs so far.")
            print(f"Discovered {len(discovered_urls)} total URLs.")
            print(f"Remaining to visit: {len(to_visit_urls)} URLs.")
            user_input = input("Do you want to continue? (y to continue, anything else to stop): ").strip().lower()
            if user_input != "y":
                print("Stopping the crawl.")
                break
            try:
                batch_size = int(input("Enter the number of URLs to process in the next batch: ").strip())
            except ValueError:
                print("Invalid input. Stopping the crawl.")
                break

    # Summary
    print("\nCrawl completed.")
    print(f"Total URLs visited: {len(visited_urls)}")
    print(f"Results saved in: {output_folder}")


if __name__ == "__main__":
    main()
