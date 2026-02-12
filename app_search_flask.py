import csv
import os
import traceback # For detailed error logging
import math # For ceiling division
from flask import Flask, request, jsonify
from flask_cors import CORS # Import CORS
from fuzzywuzzy import fuzz

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app) # Enable CORS for all origins

# --- Configuration ---
CSV_FILE_PATH = 'All_docs.csv' # Make sure this file exists
REQUIRED_MODE_EXERCICE = 'Médecin de Libre Pratique'
FIELDNAMES = [
    'Nom & Prénom',
    'Spécialité',
    'Mode Exercice',
    'Adresse Professionnelle',
    'Téléphone',
    'Governorate'
]
FUZZY_THRESHOLD = 85
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20 # Number of items per page
MAX_PAGE_SIZE = 100 # Optional: Prevent excessive page sizes

# --- Data Loading (Keep your existing function) ---
def load_doctors_data(filepath):
    # ... (your existing load_doctors_data function - no changes needed here) ...
    doctors = []
    if not os.path.exists(filepath):
        print(f"Error: CSV file not found at {filepath}")
        return []

    try:
        with open(filepath, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile, fieldnames=FIELDNAMES)
            try:
                header = next(reader)
                # Optional: Validate header if necessary
                # print(f"CSV Header Skipped/Validated: {header}")
            except StopIteration:
                print("Warning: CSV file appears to be empty or header row is missing.")
                return []

            line_number = 2
            for row in reader:
                if not row or not any(row.values()):
                    # print(f"Warning: Skipping empty or potentially malformed row at line {line_number}.")
                    line_number += 1
                    continue

                cleaned_row = {}
                valid_row = False # Flag to check if row has at least one known field populated
                for key, value in row.items():
                    clean_key = key.strip() if key else None
                    if clean_key and clean_key in FIELDNAMES:
                        cleaned_value = value.strip() if value else ''
                        cleaned_row[clean_key] = cleaned_value
                        if cleaned_value: # Check if the value is non-empty
                             valid_row = True
                    # Optional: Log unknown fields if needed
                    # elif clean_key:
                    #     print(f"Warning: Skipping unknown field '{clean_key}' at line {line_number}")

                if not valid_row:
                    # print(f"Warning: Skipping row at line {line_number} as it contained no data in known fields.")
                    line_number += 1
                    continue

                # Ensure all expected FIELDNAMES exist, defaulting to ''
                final_row = {}
                for field in FIELDNAMES:
                    final_row[field] = cleaned_row.get(field, '')

                doctors.append(final_row)
                line_number += 1

        print(f"Successfully loaded and processed {len(doctors)} records from {filepath}")
        return doctors

    except FileNotFoundError:
        print(f"Error: File not found at {filepath}")
        return []
    except csv.Error as e:
        print(f"Error reading CSV file at line {reader.line_num if 'reader' in locals() else 'unknown'}: {e}")
        traceback.print_exc()
        return []
    except Exception as e:
        print(f"An unexpected error occurred while reading the CSV: {e}")
        traceback.print_exc()
        return []

# --- Load Data on Startup ---
doctors_list = load_doctors_data(CSV_FILE_PATH)
if not doctors_list:
    print("-----------------------------------------------------------")
    print("Warning: doctors_list is empty. The API will not find any doctors.")
    print(f"Please ensure '{CSV_FILE_PATH}' exists, is readable, correctly formatted (UTF-8),")
    print(f"and contains data matching the expected FIELDNAMES: {FIELDNAMES}")
    print("-----------------------------------------------------------")

# --- Helper Function for Pagination Params ---
def get_pagination_params():
    """Gets and validates page and size parameters from query string."""
    try:
        page = int(request.args.get('page', DEFAULT_PAGE))
        size = int(request.args.get('size', DEFAULT_PAGE_SIZE))
    except ValueError:
        return None, None, 'Page and size parameters must be integers.'

    if page < 1:
        page = 1 # Default to page 1 if requested page is invalid

    if size <= 0:
         return None, None, f'Page size must be positive. Default is {DEFAULT_PAGE_SIZE}. Max is {MAX_PAGE_SIZE}.'
        # Or default: size = DEFAULT_PAGE_SIZE

    if size > MAX_PAGE_SIZE:
        print(f"Warning: Requested page size {size} exceeds maximum {MAX_PAGE_SIZE}. Clamping to max.")
        size = MAX_PAGE_SIZE

    return page, size, None


# --- API Endpoints ---

@app.route('/')
def index():
    """Root endpoint for basic API status check."""
    return jsonify({
        "message": "Doctor Search API is running.",
        "status": "OK",
        "data_loaded": bool(doctors_list),
        "record_count": len(doctors_list)
    })

@app.route('/search/doctorsList', methods=['POST', 'OPTIONS'])
def search_doctors_detailed():
    """
    Searches for doctors based on criteria (name, specialty, governorate)
    provided in the JSON request body. Filters fuzzily by name, exactly by
    specialty and governorate (case-insensitive), and requires
    'Mode Exercice' to be 'Médecin de Libre Pratique'.

    Supports pagination via query parameters:
      - `page`: The page number to retrieve (default: 1).
      - `size`: The number of items per page (default: 20, max: 100).

    Request Body (JSON):
    {
        "name": "optional search name",
        "specialty": "optional search specialty",
        "governorate": "optional search governorate"
    }

    Returns:
        JSON: {
                 "doctors": [ list of doctor objects for the current page ],
                 "currentPage": current_page_number,
                 "pageSize": number_of_items_per_page,
                 "totalItems": total_number_of_matching_doctors,
                 "totalPages": total_number_of_pages
              }
              Returns error JSON on bad request or server error.
    """
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        response = jsonify(success=True)
        return response

    # --- Get Pagination Parameters ---
    page, size, error = get_pagination_params()
    if error:
        return jsonify({"error": error}), 400

    # --- Check if doctor data is loaded ---
    if not doctors_list:
        print("Search attempt failed: Doctor data list is empty.")
        # Return standard pagination response but with zero results
        return jsonify({
            "doctors": [],
            "currentPage": page,
            "pageSize": size,
            "totalItems": 0,
            "totalPages": 0,
            "message": "No doctor data loaded on server"
        })

    # --- Get Search Criteria from Request Body ---
    try:
        search_data = request.get_json(silent=True)
        if search_data is None:
             print("Received request with empty or non-JSON body. Treating as no specific criteria.")
             search_data = {}

        search_name = search_data.get('name', '').strip().lower()
        search_specialty = search_data.get('specialty', '').strip().lower()
        search_governorate = search_data.get('governorate', '').strip().lower()

        print(f"Search Criteria - Name: '{search_name}', Specialty: '{search_specialty}', Governorate: '{search_governorate}'")
        print(f"Pagination - Page: {page}, Size: {size}")

    except Exception as e:
        print(f"Error processing request JSON body: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Invalid request body format: {e}"}), 400

    # --- Iterate and Filter ALL Matching Doctors (in memory) ---
    all_matching_doctors = [] # Store all matches first
    try:
        for doctor in doctors_list:
            # Mandatory Mode Exercice Filter
            mode_exercice = doctor.get('Mode Exercice', '').strip()
            if REQUIRED_MODE_EXERCICE.lower() not in mode_exercice.lower(): # More flexible check
                continue

            # Name Filter (Fuzzy)
            match_name = True
            if search_name:
                doctor_name = doctor.get('Nom & Prénom', '').strip().lower()
                if not doctor_name:
                    match_name = False
                else:
                    score = fuzz.token_set_ratio(search_name, doctor_name)
                    match_name = score >= FUZZY_THRESHOLD

            # Specialty Filter (Exact Case-Insensitive)
            match_specialty = True
            if search_specialty:
                doctor_specialty = doctor.get('Spécialité', '').strip().lower()
                match_specialty = search_specialty == doctor_specialty

            # Governorate Filter (Exact Case-Insensitive)
            match_governorate = True
            if search_governorate:
                doctor_governorate = doctor.get('Governorate', '').strip().lower()
                match_governorate = search_governorate == doctor_governorate

            # Combine Filters
            if match_name and match_specialty and match_governorate:
                all_matching_doctors.append(doctor)

    except Exception as e:
        print(f"An error occurred during the search filtering process: {e}")
        traceback.print_exc()
        return jsonify({"error": "An internal error occurred during search."}), 500

    # --- Apply Pagination to the Filtered Results ---
    total_items = len(all_matching_doctors)
    total_pages = math.ceil(total_items / size) if size > 0 else 0

    # Calculate slice start and end indices
    start_index = (page - 1) * size
    end_index = start_index + size

    # Get the slice for the current page
    paginated_doctors = all_matching_doctors[start_index:end_index]

    # --- Return Paginated Result ---
    print(f"Found {total_items} total matching doctors. Returning page {page}/{total_pages} ({len(paginated_doctors)} items).")
    return jsonify({
        "doctors": paginated_doctors,
        "currentPage": page,
        "pageSize": size,
        "totalItems": total_items,
        "totalPages": total_pages
    })

# --- Run the Flask App ---
if __name__ == '__main__':
    print("Starting Flask development server...")
    app.run(host='0.0.0.0', port=5000, debug=True) # Use debug=False in production