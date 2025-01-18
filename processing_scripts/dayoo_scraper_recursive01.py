import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import os
import datetime
import random
from urllib.parse import urljoin

# Function to fetch and parse a webpage
def fetch_page(url):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

# Function to extract articles and their publication date from a page
def extract_articles(soup, base_url):
    articles = []
    for item in soup.find_all("a", href=True):  # Find all anchor tags with href
        try:
            title = item.get_text(strip=True)
            url = urljoin(base_url, item["href"])  # Build the full URL
            # Check if the link is an article
            if "/2025" in url or "/2024" in url:  # Example: filter article URLs
                articles.append({"title": title, "url": url})
        except AttributeError:
            continue
    return articles

# Function to extract content from an article
def extract_content(soup):
    # Extract title, date, and main content
    try:
        title = soup.find("h1").get_text(strip=True)
        date = soup.find("span", class_="time").get_text(strip=True)
        content = soup.find("div", id="wza_content").get_text(strip=True)
        return {"title": title, "date": date, "content": content}
    except AttributeError:
        return None

# Function to filter articles by date (last 7 days)
def is_recent(date_str):
    try:
        # Parse the date (adjust format based on the website's date format)
        article_date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        # Calculate the time difference
        today = datetime.datetime.now()
        return (today - article_date).days <= 7
    except ValueError:
        return False

# Recursive function to scrape articles
def scrape_recursive(url, visited, base_url, depth=3):
    if depth == 0 or url in visited:
        return []
    visited.add(url)

    # Fetch and parse the page
    soup = fetch_page(url)
    if not soup:
        return []

    # Extract articles from the current page
    articles = extract_articles(soup, base_url)

    # Extract content for each article
    results = []
    for article in articles:
        if article["url"] not in visited:
            article_soup = fetch_page(article["url"])
            if article_soup:
                content = extract_content(article_soup)
                if content and is_recent(content["date"]):  # Filter by date
                    results.append({**article, **content})

    # Recursively visit links on this page
    for article in articles:
        results.extend(scrape_recursive(article["url"], visited, base_url, depth - 1))

    return results

# Function to create a unique folder for each run
def create_output_folder(base_path):
    random_number = random.randint(1000, 9999)
    folder_name = os.path.join(base_path, f"crawlresults_{random_number}")
    os.makedirs(folder_name, exist_ok=True)
    return folder_name, random_number

# Function to save data to JSON
def save_to_json(data, folder_path, base_filename, random_number):
    filename = os.path.join(folder_path, f"{base_filename}_{random_number}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Data saved to {filename}")
    return filename

# Function to save data to Excel
def save_to_excel(data, folder_path, base_filename, random_number):
    filename = os.path.join(folder_path, f"{base_filename}_{random_number}.xlsx")
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"Data saved to {filename}")
    return filename

# Function to generate a report
def generate_report(folder_path, random_number, num_urls_visited, num_items_downloaded, json_file, excel_file):
    report_filename = os.path.join(folder_path, f"report_{random_number}.txt")
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write("Crawl Report\n")
        f.write(f"Random Folder ID: {random_number}\n")
        f.write(f"Total URLs Visited: {num_urls_visited}\n")
        f.write(f"Total Items Downloaded: {num_items_downloaded}\n")
        f.write(f"JSON File: {json_file}\n")
        f.write(f"Excel File: {excel_file}\n")
    print(f"Report saved to {report_filename}")
    return report_filename

# Main function
def main():
    # Start URL (Dayoo portal)
    start_url = "https://news.dayoo.com/"
    base_output_folder = "/workspaces/CDtextanalytics/crawlresults"

    # Create an output folder for this run
    output_folder, random_number = create_output_folder(base_output_folder)
    print(f"Output folder created: {output_folder}")

    # Start recursive scraping
    print("Starting recursive scraping...")
    visited_urls = set()
    results = scrape_recursive(start_url, visited_urls, start_url, depth=3)

    # Save results
    json_file = save_to_json(results, output_folder, "dayoo_articles", random_number)
    excel_file = save_to_excel(results, output_folder, "dayoo_articles", random_number)

    # Generate a report
    generate_report(
        output_folder,
        random_number,
        num_urls_visited=len(visited_urls),
        num_items_downloaded=len(results),
        json_file=json_file,
        excel_file=excel_file,
    )

# Run the program
if __name__ == "__main__":
    main()