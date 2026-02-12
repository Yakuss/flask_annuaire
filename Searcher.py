# fuzzy_search_doctors.py
import pandas as pd
from thefuzz import process, fuzz
import os
import argparse # For command-line arguments

# --- Configuration ---
DEFAULT_CSV_FILE = "All_docs.csv" # Default file to search
# Adjust column names if they differ EXACTLY in your CSV
NAME_COLUMN = "Nom & Prénom"
SPECIALTY_COLUMN = "Spécialité"
GOVERNORATE_COLUMN = "Governorate"
ADDRESS_COLUMN = "Adresse Professionnelle" # Added for more context in results
PHONE_COLUMN = "Téléphone" # Added for more context in results

DEFAULT_SCORE_CUTOFF = 75 # How similar strings need to be (0-100). Adjust as needed.
DEFAULT_LIMIT = 5 # Default number of top matches to show

# --- Helper Functions ---
def load_data(csv_path):
    """Loads data from the CSV file into a pandas DataFrame."""
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at '{csv_path}'")
        return None
    try:
        df = pd.read_csv(csv_path)
        # Basic cleaning: fill potential NaN values in searchable columns with empty strings
        df[NAME_COLUMN] = df[NAME_COLUMN].fillna('')
        df[SPECIALTY_COLUMN] = df[SPECIALTY_COLUMN].fillna('')
        df[GOVERNORATE_COLUMN] = df[GOVERNORATE_COLUMN].fillna('')
        print(f"Successfully loaded {len(df)} records from '{csv_path}'")
        return df
    except FileNotFoundError:
        print(f"Error: File not found '{csv_path}'")
        return None
    except pd.errors.EmptyDataError:
        print(f"Error: File is empty '{csv_path}'")
        return None
    except Exception as e:
        print(f"Error loading CSV '{csv_path}': {e}")
        return None

def fuzzy_search(df, query, column, scorer=fuzz.WRatio, cutoff=DEFAULT_SCORE_CUTOFF, limit=DEFAULT_LIMIT):
    """
    Performs fuzzy search on a specific column of the DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame to search within.
        query (str): The search term.
        column (str): The name of the column to search in.
        scorer (function): The fuzzy matching function from thefuzz library.
                           fuzz.WRatio often works well for names/mixed strings.
                           fuzz.token_sort_ratio ignores word order.
                           fuzz.partial_ratio good for finding substrings.
        cutoff (int): The minimum similarity score (0-100) to consider a match.
        limit (int): The maximum number of matches to return.

    Returns:
        list: A list of tuples, where each tuple contains (matched_string, score, original_row_index).
              Returns None if the column doesn't exist or an error occurs.
    """
    if column not in df.columns:
        print(f"Error: Column '{column}' not found in the DataFrame.")
        return None
    if df[column].isnull().all():
         print(f"Warning: Column '{column}' contains only null/empty values.")
         return [] # Return empty list if column is all null

    # Extract the choices (unique values in the column for efficiency, map back later)
    # Keep track of original index to retrieve full row data
    choices_map = {text: index for index, text in df[column].astype(str).items() if text} # Map non-empty string value to its original index
    choices = list(choices_map.keys())

    if not choices:
        print(f"No non-empty choices found in column '{column}'.")
        return []

    print(f"\nSearching for '{query}' in column '{column}' (Scorer: {scorer.__name__}, Cutoff: {cutoff})...")
    # Use process.extract with the chosen scorer
    results = process.extract(query, choices, scorer=scorer, limit=limit*2, score_cutoff=cutoff) # Get more results initially, then filter
                                                                                                # *2 is arbitrary, adjust if needed

    # Map results back to original DataFrame index and ensure correct limit
    # results format: [(matched_string, score)]
    final_results = []
    if results:
        print(f"Found {len(results)} potential matches above cutoff.")
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        # Map back to index and keep within limit
        for matched_string, score in results[:limit]:
            # Find the first original index associated with this matched string
            # This assumes the string might appear multiple times, we take the first index
            original_index = choices_map.get(matched_string)
            if original_index is not None:
                 final_results.append((matched_string, score, original_index))
            else:
                 print(f"Warning: Could not map back matched string '{matched_string}' to original index.")

    return final_results[:limit] # Ensure we don't exceed the limit

def display_results(df, results, search_column):
    """Displays the fuzzy search results."""
    if not results:
        print("No matches found.")
        return

    print("\n--- Search Results ---")
    # Get the full rows for the matched indices
    matched_indices = [index for _, _, index in results]
    results_df = df.loc[matched_indices].copy() # Use .loc and .copy()

    # Add the score to the results DataFrame for display
    # Need to map score back based on the searched column's value in the results_df
    score_map = {index: score for _, score, index in results}
    results_df['Similarity Score'] = results_df.index.map(score_map)

    # Select and reorder columns for display
    display_columns = [NAME_COLUMN, SPECIALTY_COLUMN, GOVERNORATE_COLUMN, ADDRESS_COLUMN, PHONE_COLUMN, 'Similarity Score']
    # Filter out columns that might not exist if the input CSV changes
    display_columns = [col for col in display_columns if col in results_df.columns]

    print(results_df[display_columns].to_string(index=False))
    print("--------------------")


# --- Main Execution & Command Line Parsing ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fuzzy search doctors in a CSV file.")
    parser.add_argument("query", help="The search term (e.g., 'Mohamed', 'Nabel', 'Cardio').")
    parser.add_argument("-f", "--file", default=DEFAULT_CSV_FILE, help=f"Path to the CSV file (default: {DEFAULT_CSV_FILE}).")
    parser.add_argument("-c", "--column", required=True, choices=['name', 'specialty', 'governorate'],
                        help="Column to search in ('name', 'specialty', 'governorate').")
    parser.add_argument("-s", "--score", type=int, default=DEFAULT_SCORE_CUTOFF,
                        help=f"Minimum similarity score [0-100] (default: {DEFAULT_SCORE_CUTOFF}).")
    parser.add_argument("-l", "--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"Maximum number of results to show (default: {DEFAULT_LIMIT}).")
    parser.add_argument("--scorer", default='WRatio', choices=['WRatio', 'ratio', 'partial_ratio', 'token_sort_ratio', 'token_set_ratio'],
                        help=f"Fuzzy matching scorer to use (default: WRatio). Options: ratio, partial_ratio, token_sort_ratio, token_set_ratio, WRatio.")


    args = parser.parse_args()

    # Map column argument to actual DataFrame column name
    column_map = {
        'name': NAME_COLUMN,
        'specialty': SPECIALTY_COLUMN,
        'governorate': GOVERNORATE_COLUMN
    }
    search_column_name = column_map.get(args.column)

    # Map scorer argument to actual fuzz function
    scorer_map = {
         'WRatio': fuzz.WRatio,
         'ratio': fuzz.ratio,
         'partial_ratio': fuzz.partial_ratio,
         'token_sort_ratio': fuzz.token_sort_ratio,
         'token_set_ratio': fuzz.token_set_ratio
    }
    scorer_func = scorer_map.get(args.scorer, fuzz.WRatio) # Default to WRatio if invalid

    # Load data
    doctor_df = load_data(args.file)

    if doctor_df is not None and search_column_name:
        # Perform search
        search_results = fuzzy_search(
            df=doctor_df,
            query=args.query,
            column=search_column_name,
            scorer=scorer_func,
            cutoff=args.score,
            limit=args.limit
        )

        # Display results
        display_results(doctor_df, search_results, search_column_name)