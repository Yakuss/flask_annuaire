import csv
import os
import traceback # For detailed error logging
from flask import Flask, request, jsonify
from flask_cors import CORS # Import CORS
from fuzzywuzzy import fuzz

# --- Flask App Setup ---
app = Flask(__name__)
# Enable CORS for all origins by default.
# For production, restrict origins:
# CORS(app, resources={r"/search/*": {"origins": ["http://localhost:4200", "http://your-frontend-domain.com"]}})
CORS(app)

# --- Configuration ---
CSV_FILE_PATH = 'All_docs.csv' # Make sure this file exists in the same directory or provide the full path
REQUIRED_MODE_EXERCICE = 'Médecin de Libre Pratique'
FIELDNAMES = [
    'Nom & Prénom',
    'Spécialité',
    'Mode Exercice',
    'Adresse Professionnelle',
    'Téléphone',
    'Governorate'
]
# Increased threshold for higher accuracy name matching
FUZZY_THRESHOLD = 90

# --- Data Loading ---
def load_doctors_data(filepath):
    """
    Loads and cleans doctor data from the specified CSV file.
    Handles potential errors during file reading and parsing.
    """
    doctors = []
    if not os.path.exists(filepath):
        print(f"Error: CSV file not found at {filepath}")
        return [] # Return empty list if file doesn't exist

    try:
        with open(filepath, mode='r', encoding='utf-8-sig') as csvfile: # Use 'utf-8-sig' to handle potential BOM
            # Uncomment and adjust delimiter if your CSV uses something other than comma (e.g., semicolon)
            # reader = csv.DictReader(csvfile, fieldnames=FIELDNAMES, delimiter=';')
            reader = csv.DictReader(csvfile, fieldnames=FIELDNAMES)

            try:
                # Attempt to skip the header row
                header = next(reader)
                print(f"CSV Header Skipped: {header}") # Log the header being skipped
            except StopIteration:
                print("Warning: CSV file appears to be empty or header row is missing.")
                return [] # File is empty or has no data rows

            # Validate header if necessary (optional)
            # expected_header = {name: None for name in FIELDNAMES} # Create dict keys from FIELDNAMES
            # if header != expected_header:
            #     print(f"Warning: CSV header mismatch. Expected something like {FIELDNAMES}, got {header}")
            #     # Decide whether to proceed or return []

            line_number = 2 # Start counting after header
            for row in reader:
                # Basic check for empty or malformed rows
                if not row or not any(row.values()):
                    print(f"Warning: Skipping empty or potentially malformed row at line {line_number}.")
                    line_number += 1
                    continue

                # Clean keys and values, handle potential None values
                cleaned_row = {}
                for key, value in row.items():
                    clean_key = key.strip() if key else ''
                    clean_value = value.strip() if value else ''
                    cleaned_row[clean_key] = clean_value

                # Ensure all expected FIELDNAMES exist in the cleaned row, defaulting to ''
                final_row = {}
                for field in FIELDNAMES:
                     # Prioritize value from cleaned_row if key exists, otherwise default to ''
                    final_row[field] = cleaned_row.get(field, '')

                doctors.append(final_row)
                line_number += 1

        print(f"Successfully loaded and processed {len(doctors)} records from {filepath}")
        # Optional: Print first few records for verification
        # if doctors:
        #    print("First few loaded records:")
        #    for i in range(min(3, len(doctors))):
        #        print(doctors[i])
        return doctors

    except FileNotFoundError:
        print(f"Error: File not found at {filepath}")
        return []
    except csv.Error as e:
        print(f"Error reading CSV file: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred while reading the CSV: {e}")
        traceback.print_exc() # Print full traceback for debugging
        return []

# --- Load Data on Startup ---
doctors_list = load_doctors_data(CSV_FILE_PATH)
if not doctors_list:
    print("-----------------------------------------------------------")
    print("Warning: doctors_list is empty. The API might not find any doctors.")
    print(f"Please ensure '{CSV_FILE_PATH}' exists, is readable, correctly formatted (UTF-8),")
    print(f"and contains data matching the expected FIELDNAMES: {FIELDNAMES}")
    print("-----------------------------------------------------------")


# --- API Endpoints ---

@app.route('/')
def index():
    """Root endpoint for basic API status check."""
    return jsonify({
        "message": "Doctor Search API (Boolean Check) is running.",
        "status": "OK",
        "data_loaded": bool(doctors_list),
        "record_count": len(doctors_list)
    })

# Add OPTIONS method to handle CORS preflight requests
@app.route('/search/doctors', methods=['POST', 'OPTIONS'])
def search_doctors():
    """
    Checks if at least one doctor exists based on criteria provided
    in the JSON request body. Filters fuzzily by name (high threshold),
    exactly by specialty and governorate (case-insensitive), and requires
    'Mode Exercice' to be 'Médecin de Libre Pratique'.

    Request Body (JSON):
    {
        "name": "optional search name",
        "specialty": "optional search specialty",
        "governorate": "optional search governorate"
    }

    Returns:
        JSON: {"result": true} if a match is found, {"result": false} otherwise.
              Returns error JSON on bad request or if data wasn't loaded.
    """
    # Handle CORS preflight request (OPTIONS)
    # Flask-CORS typically handles this, but explicit handling can aid debugging.
    if request.method == 'OPTIONS':
        response = jsonify(success=True)
        # Headers are usually added by Flask-CORS automatically
        return response

    # Check if doctor data is loaded
    if not doctors_list:
        print("Search attempt failed: Doctor data list is empty.")
        # Return 200 OK, as the request is valid, but no data to search
        return jsonify({"result": False, "reason": "No doctor data loaded on server"}), 200

    # --- Get Search Criteria from Request Body ---
    try:
        search_data = request.get_json(silent=True) # silent=True avoids error if body is not JSON
        if search_data is None:
             # Handle cases where body is empty or not valid JSON
             print("Received request with empty or non-JSON body. Assuming no search criteria.")
             search_data = {}

        # Safely get search terms, default to empty string, convert to lowercase
        search_name = search_data.get('name', '').strip().lower()
        search_specialty = search_data.get('specialty', '').strip().lower()
        search_governorate = search_data.get('governorate', '').strip().lower()

        print(f"Search Criteria - Name: '{search_name}', Specialty: '{search_specialty}', Governorate: '{search_governorate}'")

    except Exception as e:
        print(f"Error processing request JSON body: {e}")
        return jsonify({"error": f"Invalid request body format: {e}"}), 400

    # --- Iterate and Filter Doctors ---
    match_found = False
    for doctor in doctors_list:
        # --- MANDATORY FILTER: Mode Exercice ---
        # Use .get() with default '' for safety, compare case-insensitively
        mode_exercice = doctor.get('Mode Exercice', '').strip()
        if mode_exercice.lower() != REQUIRED_MODE_EXERCICE.lower():
            continue # Skip if not the required practice mode

        # --- FILTER: Name (Fuzzy Match) ---
        match_name = True # Default to True if no search name provided
        if search_name:
            doctor_name = doctor.get('Nom & Prénom', '').strip().lower()
            if not doctor_name: # Can't match if doctor record has no name
                match_name = False
            else:
                # Using token_set_ratio is good for matching names even if word order differs
                score = fuzz.token_set_ratio(search_name, doctor_name)
                match_name = score >= FUZZY_THRESHOLD
                # Optional: Log fuzzy match score for debugging
                # if match_name or score > FUZZY_THRESHOLD - 20: # Log scores close to threshold
                #    print(f"Fuzzy Match: '{search_name}' vs '{doctor_name}' -> Score: {score} (Threshold: {FUZZY_THRESHOLD}) -> Match: {match_name}")


        # --- FILTER: Specialty (Exact Match - Case-Insensitive) ---
        match_specialty = True # Default to True if no search specialty provided
        if search_specialty:
            doctor_specialty = doctor.get('Spécialité', '').strip().lower()
            match_specialty = search_specialty == doctor_specialty

        # --- FILTER: Governorate (Exact Match - Case-Insensitive) ---
        match_governorate = True # Default to True if no search governorate provided
        if search_governorate:
            doctor_governorate = doctor.get('Governorate', '').strip().lower()
            match_governorate = search_governorate == doctor_governorate

        # --- Combine Filters ---
        if match_name and match_specialty and match_governorate:
            print(f"Match found: {doctor}") # Log the matched doctor record
            match_found = True
            break # Found at least one match, no need to check further

    # --- Return Result ---
    if match_found:
        return jsonify({"result": True})
    else:
        print("No matching doctors found for the given criteria.")
        return jsonify({"result": False})

# --- Run the Flask App ---
if __name__ == '__main__':
    print("Starting Flask development server...")
    # Use host='0.0.0.0' to make the server accessible from other devices on the network
    # (useful for testing from mobile or other computers, or if running in Docker)
    # Keep debug=True for development (provides auto-reloading and detailed errors)
    # but set debug=False for production deployments.
    app.run(host='0.0.0.0', port=5000, debug=True)