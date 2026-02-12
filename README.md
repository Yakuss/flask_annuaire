# Doctor Verifier

A Flask application for searching and verifying doctors from a CSV database. Provides two main services: detailed search with pagination and boolean verification checks.

## Features

- **Detailed Doctor Search** - Search doctors by name, specialty, and governorate with pagination
- **Quick Verification Check** - Boolean response to verify if a doctor exists in the database
- **Fuzzy Matching** - Intelligent name matching using fuzzywuzzy
- **CORS Support** - Cross-origin requests enabled for frontend integration

## Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv .
   ```

3. Activate the virtual environment:
   - Windows: `Scripts\activate`
   - macOS/Linux: `source bin/activate`

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Start the Flask server:
```bash
python all.py
```

The server will run on `http://localhost:5000`

### API Endpoints

#### 1. Detailed Doctor List Search
**POST** `/search/doctorsList`

Request body:
```json
{
  "name": "doctor name",
  "specialty": "specialty",
  "governorate": "governorate",
  "page": 1,
  "size": 20
}
```

#### 2. Doctor Verification Check
**POST** `/search/doctors`

Request body:
```json
{
  "name": "doctor name",
  "specialty": "specialty",
  "governorate": "governorate"
}
```

Response: `{"result": true/false}`

## CSV Format

Ensure your `All_docs.csv` file has the following columns:
- Nom & Prénom
- Spécialité
- Mode Exercice
- Adresse Professionnelle
- Téléphone
- Governorate

## Requirements

- Python 3.8+
- See `requirements.txt` for package dependencies
