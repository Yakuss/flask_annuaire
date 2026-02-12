import csv
import os
import traceback
import math 
from flask import Flask, request, jsonify
from flask_cors import CORS
from fuzzywuzzy import fuzz

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app) # Enable CORS for all origins

# --- Configuration ---
CSV_FILE_PATH = 'All_docs.csv' 
REQUIRED_MODE_EXERCICE = 'Médecin de Libre Pratique'
FIELDNAMES = [
    'Nom & Prénom',
    'Spécialité',
    'Mode Exercice',
    'Adresse Professionnelle',
    'Téléphone',
    'Governorate'
]

# --- PRESERVING YOUR EXACT LOGIC CONSTANTS ---
# Script 1 (List) used 85
FUZZY_THRESHOLD_LIST = 85
# Script 2 (Check) used 90
FUZZY_THRESHOLD_CHECK = 90

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20 
MAX_PAGE_SIZE = 100 

# --- Data Loading (Shared by both) ---
def load_doctors_data(filepath):
    doctors = []
    if not os.path.exists(filepath):
        print(f"Error: CSV file not found at {filepath}")
        return []

    try:
        with open(filepath, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile, fieldnames=FIELDNAMES)
            try:
                header = next(reader)
            except StopIteration:
                print("Warning: CSV file appears to be empty or header row is missing.")
                return []

            line_number = 2
            for row in reader:
                if not row or not any(row.values()):
                    line_number += 1
                    continue

                cleaned_row = {}
                valid_row = False 
                for key, value in row.items():
                    clean_key = key.strip() if key else None
                    if clean_key and clean_key in FIELDNAMES:
                        cleaned_value = value.strip() if value else ''
                        cleaned_row[clean_key] = cleaned_value
                        if cleaned_value: 
                             valid_row = True

                if not valid_row:
                    line_number += 1
                    continue

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
        print(f"Error reading CSV file: {e}")
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
    print("Warning: doctors_list is empty.")
    print("-----------------------------------------------------------")

# --- Helper Function for Pagination ---
def get_pagination_params():
    try:
        page = int(request.args.get('page', DEFAULT_PAGE))
        size = int(request.args.get('size', DEFAULT_PAGE_SIZE))
    except ValueError:
        return None, None, 'Page and size parameters must be integers.'

    if page < 1: page = 1 
    if size <= 0: return None, None, f'Page size must be positive.'
    if size > MAX_PAGE_SIZE: size = MAX_PAGE_SIZE

    return page, size, None


# --- API Endpoints ---

@app.route('/')
def index():
    """Root endpoint for status check."""
    return jsonify({
        "message": "Doctor API (Combined Services) is running.",
        "status": "OK",
        "data_loaded": bool(doctors_list),
        "record_count": len(doctors_list)
    })

# ==========================================
# SERVICE 1: DETAILED LIST WITH PAGINATION
# ==========================================
@app.route('/search/doctorsList', methods=['POST', 'OPTIONS'])
def search_doctors_detailed():
    if request.method == 'OPTIONS':
        return jsonify(success=True)

    page, size, error = get_pagination_params()
    if error: return jsonify({"error": error}), 400

    if not doctors_list:
        return jsonify({"doctors": [], "currentPage": page, "pageSize": size, "totalItems": 0, "totalPages": 0, "message": "No data loaded"})

    try:
        search_data = request.get_json(silent=True) or {}
        search_name = search_data.get('name', '').strip().lower()
        search_specialty = search_data.get('specialty', '').strip().lower()
        search_governorate = search_data.get('governorate', '').strip().lower()
    except Exception as e:
        return jsonify({"error": f"Invalid request body format: {e}"}), 400

    all_matching_doctors = []
    try:
        for doctor in doctors_list:
            mode_exercice = doctor.get('Mode Exercice', '').strip()
            if REQUIRED_MODE_EXERCICE.lower() not in mode_exercice.lower():
                continue

            match_name = True
            if search_name:
                doctor_name = doctor.get('Nom & Prénom', '').strip().lower()
                if not doctor_name: match_name = False
                else:
                    # USES THRESHOLD 85 (FROM SCRIPT 1)
                    score = fuzz.token_set_ratio(search_name, doctor_name)
                    match_name = score >= FUZZY_THRESHOLD_LIST

            match_specialty = True
            if search_specialty:
                doctor_specialty = doctor.get('Spécialité', '').strip().lower()
                match_specialty = search_specialty == doctor_specialty

            match_governorate = True
            if search_governorate:
                doctor_governorate = doctor.get('Governorate', '').strip().lower()
                match_governorate = search_governorate == doctor_governorate

            if match_name and match_specialty and match_governorate:
                all_matching_doctors.append(doctor)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Internal error"}), 500

    total_items = len(all_matching_doctors)
    total_pages = math.ceil(total_items / size) if size > 0 else 0
    start_index = (page - 1) * size
    end_index = start_index + size
    paginated_doctors = all_matching_doctors[start_index:end_index]

    return jsonify({
        "doctors": paginated_doctors,
        "currentPage": page,
        "pageSize": size,
        "totalItems": total_items,
        "totalPages": total_pages
    })

# ==========================================
# SERVICE 2: BOOLEAN CHECK (YES/NO)
# ==========================================
@app.route('/search/doctors', methods=['POST', 'OPTIONS'])
def search_doctors_check():
    if request.method == 'OPTIONS':
        return jsonify(success=True)

    if not doctors_list:
        return jsonify({"result": False, "reason": "No data loaded"}), 200

    try:
        search_data = request.get_json(silent=True) or {}
        search_name = search_data.get('name', '').strip().lower()
        search_specialty = search_data.get('specialty', '').strip().lower()
        search_governorate = search_data.get('governorate', '').strip().lower()
    except Exception as e:
        return jsonify({"error": f"Invalid request body: {e}"}), 400

    match_found = False
    for doctor in doctors_list:
        mode_exercice = doctor.get('Mode Exercice', '').strip()
        # Strict equality check from Script 2 logic
        if mode_exercice.lower() != REQUIRED_MODE_EXERCICE.lower():
            continue

        match_name = True
        if search_name:
            doctor_name = doctor.get('Nom & Prénom', '').strip().lower()
            if not doctor_name: match_name = False
            else:
                # USES THRESHOLD 90 (FROM SCRIPT 2)
                score = fuzz.token_set_ratio(search_name, doctor_name)
                match_name = score >= FUZZY_THRESHOLD_CHECK

        match_specialty = True
        if search_specialty:
            doctor_specialty = doctor.get('Spécialité', '').strip().lower()
            match_specialty = search_specialty == doctor_specialty

        match_governorate = True
        if search_governorate:
            doctor_governorate = doctor.get('Governorate', '').strip().lower()
            match_governorate = search_governorate == doctor_governorate

        if match_name and match_specialty and match_governorate:
            match_found = True
            break

    if match_found:
        return jsonify({"result": True})
    else:
        return jsonify({"result": False})

# --- Run the Flask App ---
if __name__ == '__main__':
    print("Starting Combined Flask Server on Port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True)