import requests
from bs4 import BeautifulSoup
import random
import os
from urllib.parse import urljoin

# Function to fetch and parse a webpage
def fetch_page(url):
    """
    Fetches and parses a webpage while ensuring proper encoding handling.
    """
    try:
        # Fetch the page
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()

        # Detect encoding from headers or default to UTF-8
        if response.encoding is None:
            response.encoding = "utf-8"  # Default encoding

        # Parse the HTML content with BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")

        # Check for encoding in meta tags
        meta_tag = soup.find("meta", attrs={"charset": True})
        if meta_tag:
            response.encoding = meta_tag["charset"]
        else:
            # Check for <meta http-equiv="Content-Type">
            meta_tag = soup.find("meta", attrs={"http-equiv": "Content-Type"})
            if meta_tag and "charset=" in meta_tag.get("content", ""):
                response.encoding = meta_tag["content"].split("charset=")[-1]

        # Re-parse the page with the detected encoding
        soup = BeautifulSoup(response.content.decode(response.encoding, errors="replace"), "html.parser")

        return soup
    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

# Function to extract all URLs from a page
def extract_links(soup, base_url):
    """
    Extracts all links (URLs) with visible text from the webpage.
    """
    links = []
    for link in soup.find_all("a", href=True):
        title = link.get_text(strip=True)
        url = urljoin(base_url, link["href"])  # Make the URL absolute
        if title and url:  # Only include links with visible text
            links.append({"title": title, "url": url})
    return links

# Function to extract the actual content from a page
def extract_content(soup):
    """
    Extracts the title and main content from a webpage.
    """
    try:
        # Extract the page title
        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else "No title found"

        # Attempt to extract the main content
        content = ""

        # Look for specific tags likely to contain main content
        for tag in ["article", "section", "div"]:
            content_container = soup.find(tag)
            if content_container:
                paragraphs = content_container.find_all("p")
                if paragraphs:
                    content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                    break  # Stop when main content is found

        # If no content found in specific tags, fallback to all <p> tags
        if not content:
            paragraphs = soup.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

        # If there's still no content, provide a default message
        if not content:
            content = "No meaningful content found."

        return {
            "title": title_text,
            "content": content,
        }
    except Exception as e:
        print(f"Error extracting content: {e}")
        return None

# Function to display a list of links and ask the user to choose one
def display_links(links):
    """
    Displays a list of links and asks the user to select one.
    """
    print("\nLinks found on the page:")
    for i, link in enumerate(links):
        print(f"{i + 1}. {link['title']} ({link['url']})")

    # Ask the user to choose a link by index
    while True:
        try:
            choice = int(input("\nEnter the number of the link you want to visit (or 0 to stop): ").strip())
            if choice == 0:
                return None  # User wants to stop
            if 1 <= choice <= len(links):
                return links[choice - 1]
            else:
                print("Invalid choice. Please select a valid number.")
        except ValueError:
            print("Invalid input. Please enter a number.")

# Function to create an output folder for reports and data
def create_output_folder(base_path):
    """
    Creates a unique output folder for storing reports and data.
    """
    random_number = random.randint(1000, 9999)
    folder_name = os.path.join(base_path, f"crawl_data_{random_number}")
    os.makedirs(folder_name, exist_ok=True)
    return folder_name

# Function to save extracted content to a file
def save_content_to_file(content, output_folder):
    """
    Saves the extracted content (title and content) to a text file.
    """
    if not content or content["content"] == "No meaningful content found":
        print("No meaningful content to save.")
        return None

    filename = generate_unique_filename("page_content", "txt")
    file_path = os.path.join(output_folder, filename)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"Title: {content['title']}\n")
            f.write("\nContent:\n")
            f.write(content["content"])
    except Exception as e:
        print(f"Error writing content to file: {e}")

    print(f"Content saved to: {file_path}")
    return file_path

# Function to generate a unique file name
def generate_unique_filename(base_name, extension):
    random_number = random.randint(1000, 9999)
    return f"{base_name}_{random_number}.{extension}"

# Main function
def main():
    """
    Main function to fetch and process a webpage.
    """
    # Request a URL from the user
    start_url = input("Please enter the starting URL: ").strip()

    # Validate the URL
    if not start_url.startswith("http"):
        print("Invalid URL. Please make sure to include 'http://' or 'https://'.")
        return

    # Base output folder
    base_output_folder = "./crawl_results"

    # Create a unique folder for this run
    output_folder = create_output_folder(base_output_folder)
    print(f"Output folder created: {output_folder}")

    # Start crawling
    current_url = start_url
    while True:
        print(f"\nFetching URL: {current_url}")
        soup = fetch_page(current_url)

        if not soup:
            print("Failed to fetch or parse the page. Exiting.")
            break

        # Extract and display links
        links = extract_links(soup, current_url)
        if not links:
            print("No links found on the page. Exiting.")
            break

        # Extract content from the current page
        content = extract_content(soup)
        if content:
            save_content_to_file(content, output_folder)

        # Display links and let the user choose one
        selected_link = display_links(links)
        if not selected_link:
            print("User stopped the program.")
            break

        # Move to the selected link
        current_url = selected_link["url"]

if __name__ == "__main__":
    main()