# In agent/tools/introspection.py
from datetime import datetime, timezone

def calculate_time_difference(start_time_iso: str, end_time_iso: str) -> str:
    """
    Calculates the difference between two ISO 8601 formatted timestamps.

    Args:
        start_time_iso (str): The starting timestamp in ISO 8601 format (e.g., '2023-10-27T10:00:00Z').
        end_time_iso (str): The ending timestamp in ISO 8601 format (e.g., '2023-10-27T10:05:00Z').

    Returns:
        str: A human-readable string describing the time difference.
    """
    try:
        start_time = datetime.fromisoformat(start_time_iso.replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(end_time_iso.replace('Z', '+00:00'))
        
        # Ensure timestamps are timezone-aware for correct subtraction
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        difference = end_time - start_time
        
        seconds = difference.total_seconds()
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        return f"The time difference is {int(days)} days, {int(hours)} hours, {int(minutes)} minutes, and {seconds:.2f} seconds."

    except Exception as e:
        return f"Error: Could not calculate time difference. Ensure timestamps are in valid ISO 8601 format. Details: {e}"