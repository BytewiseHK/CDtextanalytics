import requests
from bs4 import BeautifulSoup
import json
import pandas as pd

# Function to fetch a webpage and parse it with BeautifulSoup
def fetch_page(url):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()  # Raise an exception for HTTP errors
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

# Function to extract articles from the webpage
def extract_articles(base_url):
    # Fetch the main page
    soup = fetch_page(base_url)
    if not soup:
        return []

    articles = []
    # Find article links or containers (adjust the selectors based on the website structure)
    for article in soup.find_all("div", class_="item"):  # Example selector
        try:
            # Extract article details
            title = article.find("a").get_text(strip=True)
            url = article.find("a")["href"]
            if not url.startswith("http"):  # Handle relative URLs
                url = base_url + url
            publish_date = article.find("span", class_="date").get_text(strip=True)  # Example date selector
            content = fetch_article_content(url)

            # Append the article data
            articles.append({
                "title": title,
                "url": url,
                "publish_date": publish_date,
                "content": content,
                "word_count": len(content.split()) if content else 0
            })
        except Exception as e:
            print(f"Error extracting article: {e}")
    return articles

# Function to fetch the content of an individual article
def fetch_article_content(article_url):
    soup = fetch_page(article_url)
    if not soup:
        return ""
    # Extract the main content (adjust the selector based on the website structure)
    content_div = soup.find("div", id="wza_content")  # Example selector
    if content_div:
        return content_div.get_text(strip=True)
    return ""

# Function to save data to JSON
def save_to_json(data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Data saved to {filename}")

# Function to save data to Excel
def save_to_excel(data, filename):
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"Data saved to {filename}")

# Main function
def main():
    base_url = "https://www.dayoo.com/"  # Replace with the target website's main URL
    output_json = "articles.json"
    output_excel = "articles.xlsx"

    # Extract articles from the main page
    print("Extracting articles...")
    articles = extract_articles(base_url)

    if not articles:
        print("No articles found. Exiting.")
        return

    # Save the data to JSON and Excel
    save_to_json(articles, output_json)
    save_to_excel(articles, output_excel)

# Run the program
if __name__ == "__main__":
    main()