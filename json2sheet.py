import json
import pandas as pd

# Function to calculate word count for a given text field
def calculate_word_count(text):
    if isinstance(text, str):  # Check if text is a string
        return len(text.split())  # Split by whitespace and count words
    return 0  # Return 0 if the field is empty or not a string

# Load the JSON file
def load_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data

# Convert JSON to Excel and add the word count column
def json_to_spreadsheet_with_word_count(json_file, excel_file, text_field):
    # Load JSON data
    data = load_json(json_file)

    # Convert JSON to a pandas DataFrame
    df = pd.DataFrame(data)

    # Check if the specified text field exists in the data
    if text_field not in df.columns:
        print(f"Error: The specified text field '{text_field}' does not exist in the JSON data.")
        return

    # Add a new column for word count
    df['word_count'] = df[text_field].apply(calculate_word_count)

    # Save the DataFrame to an Excel file
    df.to_excel(excel_file, index=False)  # Removed encoding='utf-8'
    print(f"Spreadsheet saved to {excel_file}")

# Main function
def main():
    # Input JSON file (replace 'data.json' with your JSON file path)
    json_file = '/workspaces/CDtextanalytics/crawlresults/news_river_18Jan2025.json'

    # Output Excel file
    excel_file = 'output.xlsx'

    # Specify the text field for word count calculation (e.g., 'content' or 'abstract')
    text_field = 'content'  # Change this to the field you want to analyze

    # Convert JSON to Excel with word count
    json_to_spreadsheet_with_word_count(json_file, excel_file, text_field)

# Run the program
if __name__ == "__main__":
    main()