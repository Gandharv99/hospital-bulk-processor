"""
Async services for communicating with the Hospital Directory API.
Handles concurrent hospital creation and batch activation.
"""
import asyncio
import logging
from typing import List, Dict, Tuple
import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

async def create_single_hospital(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore, 
    hospital_data: Dict[str, str], 
    batch_id: str, 
    row_number: int) -> Tuple[int, Dict]:
    """
    Create a single hospital via the Hospital Directory API.

    Uses a semaphore to limit concurrent requests and avoid overwhelming
    the external API.
    
    Args:
        client: An instance of httpx.AsyncClient for making HTTP requests.
        semaphore: An asyncio.Semaphore to limit concurrent requests.
        hospital_data: A dictionary containing 'name', 'address', and optionally 'phone'.
        batch_id: The unique identifier for the current batch upload.
        row_number: The row number in the CSV for logging purposes.
    Returns:
        A tuple of (row_number, response_data) where response_data is the API response or error info.
    """
    payload = {
        "name": hospital_data['name'],
        "address": hospital_data['address'],
        "phone": hospital_data.get('phone', ''),
        "creation_batch_id": batch_id}
    url = f"{settings.HOSPITAL_API_BASE_URL}/hospitals/"

    async with semaphore:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Successfully created hospital '{hospital_data['name']}' (Row {row_number})")
            return row_number, {
                "row": row_number,
                "hospital_id": data.get("id"),
                "name": data.get("name"),
                "status": "created"
            }
        except httpx.HTTPStatusError as e:
            logger.warning("Hospital creation failed for '%s' (Row %d): %s - %s", hospital_data['name'], row_number, e.response.status_code, e.response.text)
            return row_number, {
                "row": row_number,
                "hospital_id": None,
                "name": hospital_data['name'],
                "status": "failed",
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"  # Include first 200 chars of response text for context
            }
        except httpx.RequestError as e:
            logger.warning("Hospital creation failed for '%s' (Row %d): %s", hospital_data['name'], row_number, str(e))
            return row_number, {
                "row": row_number,
                "hospital_id": None,
                "name": hospital_data['name'],
                "status": "failed",
                "error": f"Request error: {str(e)}"
            }


async def activate_batch(client: httpx.AsyncClient, batch_id: str) -> bool:
    """
    Activate all hospitals in a batch via PATCH endpoint.

    Args:
        client: An instance of httpx.AsyncClient for making HTTP requests.
        batch_id: The unique identifier for the batch to activate.
    Returns:
        True if activation succeeded, False otherwise.
    """
    url = f"{settings.HOSPITAL_API_BASE_URL}/hospitals/batch/{batch_id}/activate"
    try:
        response = await client.patch(url)
        response.raise_for_status()
        logger.info(f"Batch {batch_id} activated successfully.")
        return True
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error(f"Batch activation failed for batch {batch_id}: {str(e)}")
        return False


async def process_hospitals_bulk(
    hospitals: List[Dict[str, str]],
    batch_id: str,
) -> Tuple[List[Dict], bool]:
    """
    Process the bulk hospital creation and activation.
    Creates hospitals concurrently and then activates the batch if all creations succeed.

    Args:
        hospitals: A list of dictionaries with hospital data (name, address, phone).
        batch_id: The unique identifier for the current batch upload.
    Returns:
        A tuple of (results_list, batch_activation_bool) where results_list ordered by the original hospital list and 
        batch_activation_bool indicates if the batch was activated.
    """
    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS)
    timeout = httpx.Timeout(settings.HOSPITAL_API_TIMEOUT)

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Fire off all hospital creation tasks concurrently
        tasks = [
            create_single_hospital(client, semaphore, hospital, batch_id, row_number)
            for row_number, hospital in enumerate(hospitals, start=1)
        ]
        creation_results = await asyncio.gather(*tasks)
        # Sort results by original row number to maintain order
        creation_results.sort(key=lambda x: x[0])
        ordered_results = [result for _, result in creation_results]
        # Check if all hospitals were created successfully
        all_success = all(result['status'] == 'created' for result in ordered_results)
        # Activate batch if all creations succeeded
        batch_activated = False
        if all_success:
            batch_activated = await activate_batch(client, batch_id)
            if batch_activated:
                for result in ordered_results:
                    result['status'] = 'created_and_activated'
            else:
                for result in ordered_results:
                    if result['status'] == 'created':
                        result['status'] = 'created_but_activation_failed'
        
        return ordered_results, batch_activated