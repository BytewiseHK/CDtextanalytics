import requests
from bs4 import BeautifulSoup
import random
import os
import datetime
from urllib.parse import urljoin

# Function to fetch and parse a webpage
def fetch_page(url):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

# Function to generate a unique report file name
def generate_report_filename(base_name):
    random_number = random.randint(1000, 9999)
    return f"{base_name}_{random_number}.txt"

# Function to analyze the structure of a URL and write a report
def analyze_url_structure(url, soup, output_folder):
    report_file = generate_report_filename("URL_report")
    report_path = os.path.join(output_folder, report_file)

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            # Write the URL
            f.write(f"URL Report for: {url}\n")
            f.write("=" * 50 + "\n\n")

            # Write the title of the page
            title = soup.title.string if soup.title else "No title found"
            f.write(f"Page Title: {title}\n\n")

            # Write meta tags
            f.write("Meta Tags:\n")
            for meta in soup.find_all("meta"):
                f.write(f"- {meta}\n")
            f.write("\n")

            # Write the structure of the page (list of div classes and IDs)
            f.write("Page Structure (div classes and IDs):\n")
            for div in soup.find_all("div"):
                div_class = div.get("class")
                div_id = div.get("id")
                if div_class or div_id:
                    f.write(f"- ID: {div_id}, Class: {div_class}\n")
            f.write("\n")

            # Write all links
            f.write("All Links Found on the Page:\n")
            for link in soup.find_all("a", href=True):
                f.write(f"- {link['href']}\n")
    except Exception as e:
        print(f"Error writing report: {e}")

    print(f"URL structure report saved to: {report_path}")
    return report_path

# Function to extract a list of articles from the page
def extract_articles(soup, base_url):
    articles = []
    for link in soup.find_all("a", href=True):
        title = link.get_text(strip=True)
        if title:  # Only include links with visible text
            url = urljoin(base_url, link["href"])
            articles.append({"title": title, "url": url})
    return articles

# Function to display extracted articles and ask the user to select one
def display_and_choose_article(articles):
    print("\nExtracted Articles:")
    for i, article in enumerate(articles):
        print(f"{i + 1}. {article['title']} ({article['url']})")

    print("\nEnter the number of the article you want to visit next (or 'q' to quit):")
    choice = input("> ").strip()
    if choice.lower() == "q":
        return None

    try:
        choice_index = int(choice) - 1
        if 0 <= choice_index < len(articles):
            return articles[choice_index]["url"]
        else:
            print("Invalid choice. Please try again.")
            return display_and_choose_article(articles)
    except ValueError:
        print("Invalid input. Please try again.")
        return display_and_choose_article(articles)

# Function to create an output folder for reports and data
def create_output_folder(base_path):
    random_number = random.randint(1000, 9999)
    folder_name = os.path.join(base_path, f"crawl_data_{random_number}")
    os.makedirs(folder_name, exist_ok=True)
    return folder_name

# Main function
def main():
    # Base output folder
    base_output_folder = "./crawl_results"

    # Create a unique folder for this run
    output_folder = create_output_folder(base_output_folder)
    print(f"Output folder created: {output_folder}")

    # Ask the user to enter a URL to analyze
    print("Enter the URL to start with:")
    start_url = input("> ").strip()

    # Start processing the URL
    current_url = start_url
    while current_url:
        print(f"\nFetching URL: {current_url}")
        soup = fetch_page(current_url)
        if not soup:
            print("Failed to retrieve the page. Exiting.")
            break

        # Analyze the structure of the URL and save the report
        print("Analyzing page structure...")
        analyze_url_structure(current_url, soup, output_folder)

        # Extract a list of articles from the page
        print("Extracting articles...")
        articles = extract_articles(soup, current_url)
        if not articles:
            print("No articles found on this page.")
            break

        # Ask the user which article to visit next
        next_url = display_and_choose_article(articles)
        if not next_url:
            print("Exiting program as requested by the user.")
            break

        # Set the next URL to visit
        current_url = next_url

    print("\nCrawl complete. Check the output folder for reports and data.")

if __name__ == "__main__":
    main()