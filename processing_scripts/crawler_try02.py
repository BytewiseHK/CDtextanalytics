import requests
from bs4 import BeautifulSoup
import json
import pandas as pd

# Function to fetch and parse a webpage
def fetch_page(url):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

# Function to extract the main article
def extract_main_article(soup):
    try:
        title = soup.find("h1", id="wza_hd").get_text(strip=True)
        publish_date = soup.find("span", class_="time").get_text(strip=True)
        source = soup.find("span", class_="source").get_text(strip=True).replace("来源:", "").strip()
        content = soup.find("div", id="wza_content").get_text(strip=True)

        return {
            "title": title,
            "publish_date": publish_date,
            "source": source,
            "content": content,
            "word_count": len(content.split()) if content else 0,
        }
    except AttributeError:
        print("Error extracting main article details.")
        return None

# Function to extract recommended articles
def extract_recommended_articles(soup):
    articles = []
    for item in soup.find_all("div", class_="news-item"):
        try:
            title_tag = item.find("div", class_="h2tit").find("a")
            title = title_tag.get_text(strip=True)
            url = title_tag["href"]

            summary_tag = item.find("div", class_="news-abst")
            summary = summary_tag.get_text(strip=True) if summary_tag else ""

            publish_date_tag = item.find("div", class_="news-time")
            publish_date = publish_date_tag.get_text(strip=True) if publish_date_tag else ""

            articles.append({
                "title": title,
                "url": url,
                "summary": summary,
                "publish_date": publish_date,
            })
        except AttributeError:
            print("Error extracting a recommended article.")
    return articles

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
    # URL of the article page
    url = "https://news.dayoo.com/china/202501/18/139997_54777019.htm"  # Replace with the actual URL

    # Fetch and parse the page
    soup = fetch_page(url)
    if not soup:
        print("Failed to fetch the webpage.")
        return

    # Extract the main article
    print("Extracting main article...")
    main_article = extract_main_article(soup)
    if main_article:
        print("Main article extracted successfully.")
        print(main_article)
    else:
        print("No main article found.")

    # Extract recommended articles
    print("Extracting recommended articles...")
    recommended_articles = extract_recommended_articles(soup)
    if recommended_articles:
        print(f"{len(recommended_articles)} recommended articles extracted.")
    else:
        print("No recommended articles found.")

    # Combine all data
    data = {
        "main_article": main_article,
        "recommended_articles": recommended_articles,
    }

    # Save to JSON
    save_to_json(data, "articles.json")

    # Save recommended articles to Excel
    if recommended_articles:
        save_to_excel(recommended_articles, "recommended_articles.xlsx")

# Run the program
if __name__ == "__main__":
    main()
