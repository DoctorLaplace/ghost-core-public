# In agent/tools/web_search.py
import logging
import requests
import json
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def perform_search(query: str, num_results: int = 5) -> str:
    """
    Performs a web search using the Google Custom Search API and returns a formatted string of results.

    Args:
        query (str): The search query.
        num_results (int): The maximum number of results to return (max 10).

    Returns:
        str: A formatted string containing the search results, or an error message.
    """
    if not all([config.GOOGLE_API_KEY, config.SEARCH_ENGINE_ID]):
        return "Error: Google API key or Search Engine ID is not configured."
    if not query:
        return "Error: Received an empty query for web search."

    try:
        logger.info(f"Performing Google REST API search for: '{query}'")
        url = "https://customsearch.googleapis.com/customsearch/v1"
        params = {
            "key": config.GOOGLE_API_KEY,
            "cx": config.SEARCH_ENGINE_ID,
            "q": query,
            "num": num_results
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        res = response.json()

        items = res.get('items', [])
        if not items:
            return f"No search results found for '{query}'."

        output_lines = [f"--- Web Search Results for '{query}' ---"]
        for item in items:
            title = item.get('title', 'No Title')
            snippet = item.get('snippet', 'No Snippet')
            link = item.get('link', 'No Link')
            output_lines.append(f"Title: {title}")
            output_lines.append(f"Snippet: {snippet}")
            output_lines.append(f"Link: {link}")
            output_lines.append("-" * 20)
        
        return "\n".join(output_lines)

    except requests.exceptions.RequestException as e:
        logger.error(f"A request error occurred during Google search: {e}", exc_info=True)
        return f"Error: A network error occurred during the search: {e}"
    except Exception as e:
        logger.error(f"An error occurred parsing the Google search results: {e}", exc_info=True)
        return f"Error: An unexpected error occurred: {e}"