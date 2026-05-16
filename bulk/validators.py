"""
CSV validation logic for hospital bulk upload.
Separates validation concerns from view logic.
"""
import csv
import io
from typing import List, Dict
from django.conf import settings
import re

PHONE_REGEX = re.compile(r'^[\d\s\-\+\(\)\.]{7,20}$')

class CSVValidatorError(Exception):
    """Custom exception for CSV validation errors."""
    pass

def is_valid_phone(phone: str) -> bool:
    """
    Phone validation: allows digits and common separators,
    requires at least 7 digits, total length 7-20 characters.
    """
    if not PHONE_REGEX.match(phone):
        return False
    digit_count = sum(c.isdigit() for c in phone)
    return digit_count >= 7

def validate_and_parse_csv(file) -> List[Dict[str, str]]:
    """
    Validates the uploaded CSV file and parses it into a list of dictionaries.
    
    Args:
        file: The uploaded CSV file (InMemoryUploadedFile).
    Returns:
        List of dicts like [{"name": "...", "address": "...", "phone": "..."}]
    Raises:
        CSVValidatorError: If the file is not a valid CSV or if required columns are missing.
    """
    # 1. Check filename extension
    if not file.name.lower().endswith('.csv'):
        raise CSVValidatorError("Invalid file type. Please upload a .csv file.")
    # 2. Decode the file content
    try:
        decoded_file = file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        raise CSVValidatorError("Unable to decode the file. Please ensure it's a valid UTF-8 encoded CSV.")
    # 3. Parse CSV content
    csv_reader = csv.DictReader(io.StringIO(decoded_file))
    # 4. Validate required columns
    required_columns = {'name', 'address'}
    if not csv_reader.fieldnames:
        raise CSVValidatorError("CSV file is empty or no header row found.")
    csv_columns = {col.strip().lower() for col in csv_reader.fieldnames}
    missing_columns = required_columns - csv_columns
    if missing_columns:
        raise CSVValidatorError(
            f"Missing required columns: {', '.join(sorted(missing_columns))}. "
            f"Required: name, address. Optional: phone."
        )
    # 5. Read and validate each rows
    hospitals = []
    for row_index, row in enumerate(csv_reader, start=1):
        # Normalize keys to lowercase and strip whitespace
        normalized_row = {key.strip().lower(): (value or '').strip() for key, value in row.items()}
        name = normalized_row.get('name')
        address = normalized_row.get('address')
        phone = normalized_row.get('phone', '')  # Optional field
        if not name:
            raise CSVValidatorError(f"Row {row_index}: 'name' is required.")
        if not address:
            raise CSVValidatorError(f"Row {row_index}: 'address' is required.")
        if phone and not is_valid_phone(phone):
            raise CSVValidatorError(f"Row {row_index}: 'phone' is not valid.")

        hospital = {'name': name, 'address': address}
        if phone:
            hospital['phone'] = phone
        hospitals.append(hospital)
    # 6. Check for row count
    if len(hospitals) == 0:
        raise CSVValidatorError("CSV file contains no valid hospital entries.")
    max_allowed_rows = settings.MAX_HOSPITALS_PER_BATCH
    if len(hospitals) > max_allowed_rows:
        raise CSVValidatorError(f"Too many rows. Maximum allowed is {max_allowed_rows}.")
    return hospitals
