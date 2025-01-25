import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import random
import os
import datetime

# Function to fetch and parse a webpage
def fetch_page(url):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

# Function to extract main headlines (top image slider)
def extract_main_headlines(soup):
    headlines = []
    for item in soup.select(".img-item"):
        try:
            title = item.select_one(".txt-area a").get_text(strip=True)
            url = item.select_one(".txt-area a")["href"]
            image = item.select_one(".img-area img")["src"]
            headlines.append({"title": title, "url": url, "image": image})
        except AttributeError:
            print("Error extracting a main headline.")
    return headlines

# Function to extract recommended articles ("精彩推荐")
def extract_recommended_articles(soup):
    articles = []
    for item in soup.select(".dy-news .news-box"):
        try:
            title = item.select_one(".txt-area h3 a").get_text(strip=True)
            url = item.select_one(".txt-area h3 a")["href"]
            image = item.select_one(".img-area img")["src"]
            summary = item.select_one(".abst").get_text(strip=True) if item.select_one(".abst") else ""
            articles.append({"title": title, "url": url, "image": image, "summary": summary})
        except AttributeError:
            print("Error extracting a recommended article.")
    return articles

# Function to extract hot news ("热闻")
def extract_hot_news(soup):
    hot_news = []
    for item in soup.select(".gz24h .bd dl"):
        try:
            title = item.select_one("dt a.news-title").get_text(strip=True)
            url = item.select_one("dt a.news-title")["href"]
            image = item.select_one(".img-area img")["src"] if item.select_one(".img-area img") else None
            summary = item.select_one(".txt-area").get_text(strip=True) if item.select_one(".txt-area") else ""
            time = item.select_one(".news-time").get_text(strip=True) if item.select_one(".news-time") else ""
            hot_news.append({"title": title, "url": url, "image": image, "summary": summary, "time": time})
        except AttributeError:
            print("Error extracting a hot news item.")
    return hot_news

# Function to extract articles from a specific section (e.g., "广州24小时")
def extract_section_articles(soup, section_selector):
    articles = []
    for item in soup.select(section_selector + " .list-area li a"):
        try:
            title = item.get_text(strip=True)
            url = item["href"]
            articles.append({"title": title, "url": url})
        except AttributeError:
            print("Error extracting a section article.")
    return articles

# Function to create a unique folder for each run
def create_output_folder(base_path):
    # Generate a unique folder name based on the current timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = os.path.join(base_path, f"crawlresults_{timestamp}")
    os.makedirs(folder_name, exist_ok=True)
    return folder_name

# Function to save data to JSON
def save_to_json(data, folder_path, base_filename):
    filename = os.path.join(folder_path, f"{base_filename}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Data saved to {filename}")

# Function to save data to Excel
def save_to_excel(data, folder_path, base_filename):
    filename = os.path.join(folder_path, f"{base_filename}.xlsx")
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"Data saved to {filename}")

# Main function
def main():
    # Portal URL
    url = "https://news.dayoo.com/"

    # Base output folder
    base_output_folder = "/workspaces/CDtextanalytics/crawlresults"

    # Create a unique folder for this run
    output_folder = create_output_folder(base_output_folder)
    print(f"Output folder created: {output_folder}")

    # Fetch and parse the portal page
    soup = fetch_page(url)
    if not soup:
        print("Failed to fetch the webpage.")
        return

    # Extract different types of content
    print("Extracting main headlines...")
    main_headlines = extract_main_headlines(soup)

    print("Extracting recommended articles...")
    recommended_articles = extract_recommended_articles(soup)

    print("Extracting hot news...")
    hot_news = extract_hot_news(soup)

    print("Extracting 'Guangzhou 24 Hours' articles...")
    guangzhou_24_hours = extract_section_articles(soup, ".observe")

    # Combine all data into a dictionary
    data = {
        "main_headlines": main_headlines,
        "recommended_articles": recommended_articles,
        "hot_news": hot_news,
        "guangzhou_24_hours": guangzhou_24_hours,
    }

    # Save data to JSON
    save_to_json(data, output_folder, "dayoo_portal")

    # Save each section to its own Excel file
    if main_headlines:
        save_to_excel(main_headlines, output_folder, "main_headlines")
    if recommended_articles:
        save_to_excel(recommended_articles, output_folder, "recommended_articles")
    if hot_news:
        save_to_excel(hot_news, output_folder, "hot_news")
    if guangzhou_24_hours:
        save_to_excel(guangzhou_24_hours, output_folder, "guangzhou_24_hours")

# Run the program
if __name__ == "__main__":
    main()