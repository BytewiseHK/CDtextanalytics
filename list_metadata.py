import json

# Load the JSON file
def load_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data

# Extract all unique keys (metadata fields) in the JSON file
def extract_metadata_keys(data):
    # Use a set to store unique keys
    all_keys = set()

    # Iterate through each item in the JSON data
    for item in data:
        # Add keys from the current item to the set
        all_keys.update(item.keys())

    return sorted(all_keys)  # Return sorted list of unique keys

# Main function
def main():
    # Path to your JSON file (replace 'data.json' with your file's path)
    file_path = '/workspaces/CDtextanalytics/crawlresults/news_river_18Jan2025.json'
    
    # Load the JSON file
    data = load_json(file_path)
    
    # Extract metadata keys
    metadata_keys = extract_metadata_keys(data)
    
    # Print the metadata keys
    print("Metadata keys in the JSON file:")
    for key in metadata_keys:
        print(f"- {key}")

# Run the program
if __name__ == "__main__":
    main()