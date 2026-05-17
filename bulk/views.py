import asyncio
import logging
import time
import uuid

from django.conf import settings
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from adrf.views import APIView
from rest_framework import status as http_status
from rest_framework.decorators import api_view

from .validators import validate_and_parse_csv, CSVValidatorError
from .services import process_hospitals_bulk

logger = logging.getLogger(__name__)


@api_view(['GET'])
def health_check(request):
    """Simple health check endpoint."""
    return Response({"status": "healthy"}, status=http_status.HTTP_200_OK)

class HospitalBulkUploadView(APIView):
    """
    POST endpoint for bulk uploading hospitals via a CSV file.
    Accepts a multipart/form-data with csv file under file field.
    Returns a JSON Summary of the bulk processing operation.
    """
    parser_classes = [MultiPartParser]

    async def post(self, request, *args, **kwargs):
        start_time = time.perf_counter()
        # 1. Get the uploaded file
        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response({"error": "No file uploaded. Please upload a CSV file under the 'file' field."}, 
            status=http_status.HTTP_400_BAD_REQUEST)
        # 2. Validate and parse the CSV file
        try:
            hospitals_data = validate_and_parse_csv(csv_file)
        except CSVValidatorError as e:
            logger.warning("CSV validation failed: %s", str(e))
            return Response({"error": str(e)}, status=http_status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.warning("Unexpected error during CSV validation: %s", str(e))
            return Response({"error": "An unexpected error occurred during CSV validation."}, status=http_status.HTTP_400_BAD_REQUEST)
        # 3. Generate a unique batch ID for this upload
        batch_id = str(uuid.uuid4())
        logger.info("Processing bulk upload batch: %s with %d hospitals.", batch_id, len(hospitals_data))   
        # 4. Process the hospitals data asynchronously
        try:
            results, batch_activated = await process_hospitals_bulk(hospitals_data, batch_id)
        except Exception as e:
            logger.exception("Error during bulk processing: %s", str(e))
            return Response(
                {
                    'error': "Bulk processing failed due to an unexpected error.",
                    'details': str(e),
                    'batch_id': batch_id
                },
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)
        # 5. Build the response summary
        processed_count = sum(1 for r in results if r['status'] != 'failed')
        failed_count = sum(1 for r in results if r['status'] == 'failed')
        elapsed_time = round(time.perf_counter() - start_time, 3)

        response_data = {
            "batch_id": batch_id,
            "total_hospitals": len(results),
            "processed_hospitals": processed_count,
            "failed_hospitals": failed_count,
            "processing_time_seconds": elapsed_time,
            "batch_activated": batch_activated,
            "hospitals": results
        }

        # Decide HTTP status code based on results
        if failed_count == 0 and batch_activated:
            status_code = http_status.HTTP_201_CREATED
        elif failed_count == 0 and not batch_activated:
            status_code = http_status.HTTP_207_MULTI_STATUS  # Created but activation failed
        elif processed_count > 0:
            status_code = http_status.HTTP_207_MULTI_STATUS  # Partial success
        else:
            status_code = http_status.HTTP_502_BAD_GATEWAY  # All failed
        
        return Response(response_data, status=status_code)

class CSVValidationView(APIView):
    """
    POST endpoint to validate a CSV file without processing.
    Useful for clients to check if their CSV is correctly formatted before actual upload.
    """
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response({"error": "No file uploaded. Please upload a CSV file under the 'file' field."}, 
            status=http_status.HTTP_400_BAD_REQUEST)
        try:
            hospitals_data = validate_and_parse_csv(csv_file)
            return Response({
                "valid": True,
                "message": f"CSV is valid with {len(hospitals_data)} hospital entries.",
            }, status=http_status.HTTP_200_OK)
        except CSVValidatorError as e:
            logger.warning("CSV validation failed: %s", str(e))
            return Response({"valid": False, "error": str(e)}, status=http_status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.warning("Unexpected error during CSV validation: %s", str(e))
            return Response({"valid": False, "error": "An unexpected error occurred during CSV validation."}, status=http_status.HTTP_400_BAD_REQUEST)