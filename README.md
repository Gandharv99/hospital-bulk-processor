# Hospital Bulk Processing API

A Django-based bulk processing service that accepts CSV uploads of hospital records and creates them concurrently in an external Hospital Directory API. Built to demonstrate async I/O patterns for high-throughput external API integration.

## Live Demo

**API Base URL:** `https://hospital-bulk-processor-rphl.onrender.com`

**Endpoints:**
- `POST https://hospital-bulk-processor-rphl.onrender.com/api/hospitals/bulk` — Bulk create hospitals
- `POST https://hospital-bulk-processor-rphl.onrender.com/api/hospitals/bulk/validate` — Validate CSV without processing
- `GET https://hospital-bulk-processor-rphl.onrender.com/api/health` — Health check

**Interactive API Docs:** `https://hospital-bulk-processor-rphl.onrender.com/api/docs/`

> Note: Hosted on Render free tier. First request after idle may take 30-60 seconds (cold start). Subsequent requests are fast.

## Overview

This service acts as a bulk processing layer on top of the [Hospital Directory API](https://hospital-directory.onrender.com/docs). It accepts a CSV file with up to 20 hospital records, validates the data, fires concurrent creation requests for all hospitals under a single batch UUID, then activates the batch — returning a comprehensive summary.

### Processing Flow

```
CSV Upload
    ↓
Validation (file type, columns, row count, field constraints)
    ↓
Generate batch_id (UUID)
    ↓
Concurrent POST /hospitals/ for each row (async via asyncio.gather)
    ↓
PATCH /hospitals/batch/{batch_id}/activate (only if all succeeded)
    ↓
JSON response with batch_id, counts, timing, per-hospital status
```

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| Web Framework | Django 6.x | Mature, batteries-included, native async support |
| API Layer | DRF + adrf | DRF for parsers/responses; adrf for true async APIView support |
| HTTP Client | httpx | Async-compatible HTTP client for concurrent external API calls |
| Concurrency | asyncio.gather + Semaphore | Run 20 requests concurrently with bounded parallelism |
| Server | gunicorn + uvicorn workers | Production ASGI setup |
| Config | python-decouple | 12-factor environment-based configuration |
| Container | Docker + docker-compose | Reproducible builds, easy deployment |
| Hosting | Render | Auto-deploy from GitHub on push |

## Project Structure

```
hospital-bulk-processor/
├── bulk/
│   ├── validators.py       # CSV parsing & validation logic
│   ├── services.py         # Async external API integration
│   ├── views.py            # API endpoint (async via adrf)
│   └── urls.py             # App-level URL routing
├── core/
│   ├── settings.py         # Django configuration
│   ├── urls.py             # Project-level URL routing
│   └── asgi.py             # ASGI entry point
├── test_csv/               # Sample CSVs for manual testing
├── Dockerfile              # Production container image
├── docker-compose.yml      # Local container orchestration
├── .env.example            # Environment variable template
├── requirements.txt        # Python dependencies
└── manage.py
```

## API Reference

### `POST /api/hospitals/bulk`

Accepts a CSV file via multipart form data and bulk-creates hospitals.

**Request:**
- Content-Type: `multipart/form-data`
- Field: `file` (CSV file)

**CSV Format:**
```csv
name,address,phone
City General Hospital,123 Main Street,555-1234
Green Valley Medical,456 Oak Avenue,(555) 234-5678
Sunrise Care Center,789 Pine Road,
```

| Column | Required | Notes |
|---|---|---|
| `name` | Yes | Hospital name, non-empty |
| `address` | Yes | Hospital address, non-empty |
| `phone` | No | Loose validation: digits + common separators, 7-20 chars |

**Constraints:**
- Maximum 20 hospitals per upload
- File must have `.csv` extension
- UTF-8 encoding (BOM tolerated)

**Success Response (201 Created):**
```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_hospitals": 3,
  "processed_hospitals": 3,
  "failed_hospitals": 0,
  "processing_time_seconds": 1.234,
  "batch_activated": true,
  "hospitals": [
    {
      "row": 1,
      "hospital_id": 101,
      "name": "City General Hospital",
      "status": "created_and_activated"
    },
    {
      "row": 2,
      "hospital_id": 102,
      "name": "Green Valley Medical",
      "status": "created_and_activated"
    },
    {
      "row": 3,
      "hospital_id": 103,
      "name": "Sunrise Care Center",
      "status": "created_and_activated"
    }
  ]
}
```

**Hospital Status Values:**

| Status | Meaning |
|---|---|
| `created_and_activated` | Created successfully and batch was activated |
| `created_but_activation_failed` | Created successfully but batch activation step failed |
| `failed` | Creation failed for this row |

**HTTP Status Codes:**

| Code | Meaning |
|---|---|
| 201 | All hospitals created and batch activated |
| 207 | Partial success — some failed, or all created but activation failed |
| 400 | Validation error (bad CSV, missing columns, invalid data) |
| 500 | Unexpected server error |
| 502 | All hospitals failed (external API issue) |

**Validation Error Examples:**

```json
{ "error": "Invalid file type. Please upload a .csv file." }
{ "error": "Missing required columns: address, name. Required: name, address. Optional: phone." }
{ "error": "Row 2: 'name' is required." }
{ "error": "Row 1: 'phone' is not valid." }
{ "error": "Too many rows. Maximum allowed is 20." }
```

### `POST /api/hospitals/bulk/validate`

Validates a CSV file without creating any hospitals. Useful for clients to verify their data format before triggering the actual bulk processing.

**Request:**
- Content-Type: `multipart/form-data`
- Field: `file` (CSV file)

**Validation Rules:** Same as `POST /api/hospitals/bulk` (file type, required columns, row limits, field constraints).

**Success Response (200 OK):**
```json
{
  "valid": true,
  "message": "CSV is valid with 5 hospital entries."
}
```

**Error Response (400 Bad Request):**
```json
{
  "valid": false,
  "error": "Row 2: 'name' is required."
}
```

This endpoint is a **dry-run** — no external API calls are made, no hospitals are created, no batch is generated. It only runs the same validation pipeline used by the bulk processing endpoint.

### `GET /api/health`

Simple health check endpoint.

**Response (200 OK):**
```json
{ "status": "healthy" }
```

## Setup & Local Development

### Prerequisites

- Python 3.10+ (developed against 3.13)
- pip
- Docker Desktop (optional, for containerized run)

### Local Setup

```bash
# 1. Clone the repo
git clone https://github.com/Gandharv99/hospital-bulk-processor.git
cd hospital-bulk-processor

# 2. Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env as needed - the defaults work for local development

# 5. Run development server
python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000/api/hospitals/bulk`.

### Docker Setup

```bash
# Build and start
docker compose up --build

# In detached mode
docker compose up -d

# Stop
docker compose down
```

### Production-Like Local Run

Test with the actual production server (gunicorn + uvicorn workers):

```bash
gunicorn core.asgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker
```

## Testing

### Manual Testing

Sample CSV files are provided in `test_csv/` covering both success and failure scenarios:

| File | Scenario | Expected |
|---|---|---|
| `valid_small.csv` | 3 valid hospitals | 201, all activated |
| `valid_full_20.csv` | Maximum allowed (20 hospitals) | 201, all activated |
| `too_many.csv` | 21 rows | 400 |
| `missing_columns.csv` | Wrong headers | 400 |
| `empty_name.csv` | Empty required field | 400 |
| `invalid_phone.csv` | Bad phone format | 400 |
| `only_headers.csv` | No data rows | 400 |
| `wrong_extension.txt` | Not a CSV | 400 |

### Testing via Browser (DRF Browsable API)

Open `http://127.0.0.1:8000/api/hospitals/bulk` in a browser. The DRF interface provides a file upload form and pretty-printed response viewer.

### Testing via Postman

For dry-run validation (no hospitals created):
1. Method: `POST`
2. URL: `http://127.0.0.1:8000/api/hospitals/bulk/validate`
3. Body → form-data → key `file` (type File) → choose CSV
4. Send

For actual bulk processing:
1. Method: `POST`
2. URL: `http://127.0.0.1:8000/api/hospitals/bulk`
3. Body → form-data → key `file` (type File) → choose CSV
4. Send

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | (dev key) | Django secret key — set a strong value in production |
| `DEBUG` | `True` | Enable Django debug mode — must be `False` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list of allowed hosts |
| `HOSPITAL_API_BASE_URL` | `https://hospital-directory.onrender.com` | External API base URL |
| `HOSPITAL_API_TIMEOUT` | `30` | Per-request timeout in seconds |
| `MAX_HOSPITALS_PER_BATCH` | `20` | Maximum rows allowed per CSV |
| `MAX_CONCURRENT_REQUESTS` | `10` | Max concurrent external API calls |

## Deployment

The application is deployed on Render as a Docker service. Deployment is automatic on every push to the `main` branch.

**Production setup:**
- Docker image built from `Dockerfile`
- Runs `gunicorn` with `uvicorn.workers.UvicornWorker` workers
- Environment variables managed via Render dashboard