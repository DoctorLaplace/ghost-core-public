# In agent/tools/file_system.py

import os
import logging
from typing import List

logger = logging.getLogger(__name__)

def create_file(path: str, content: str = "") -> str:
    """
    Creates a new file at a specified path and writes content to it.
    If the file already exists, it will be completely overwritten.
    If the directory does not exist, it will be created automatically.

    Args:
        path (str): The absolute or relative path for the new file (e.g., 'E:\\Git Repositories\\Demo\\script.py').
        content (str): The string content to be written to the file. Can be multi-line. Defaults to an empty file.

    Returns:
        str: A success message if the file was created, or a detailed error message.
    """
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
            
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Successfully created and wrote to file: {path}")
        return f"Success: File '{path}' was created and written successfully."
    except Exception as e:
        error_msg = f"Error: Failed to create file '{path}'. Details: {e}"
        logger.error(error_msg, exc_info=True)
        return error_msg

def read_file(path: str) -> str:
    """
    Reads the entire content of a file at a specified path.

    Args:
        path (str): The path to the file to be read.

    Returns:
        str: The content of the file as a string, or an error message if it cannot be read.
    """
    try:
        if not os.path.isfile(path):
            return f"Error: File not found at path '{path}'."
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.info(f"Successfully read file: {path}")
        return content
    except Exception as e:
        error_msg = f"Error: Failed to read file '{path}'. Details: {e}"
        logger.error(error_msg, exc_info=True)
        return error_msg

def append_to_file(path: str, content: str) -> str:
    """
    Appends content to the end of an existing file.
    If the file does not exist, it will be created. A newline is NOT automatically added.

    Args:
        path (str): The path to the file.
        content (str): The string content to append. To add a new line, include '\\n' in your content.

    Returns:
        str: A success message or an error message.
    """
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(path, 'a', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Successfully appended to file: {path}")
        return f"Success: Content appended to file '{path}'."
    except Exception as e:
        error_msg = f"Error: Failed to append to file '{path}'. Details: {e}"
        logger.error(error_msg, exc_info=True)
        return error_msg

def list_directory(path: str = '.') -> str:
    """
    Lists all files and subdirectories within a specified directory path.

    Args:
        path (str): The directory path to inspect. Defaults to the current directory.

    Returns:
        str: A newline-separated list of files and directories, or an error message.
    """
    try:
        if not os.path.isdir(path):
            return f"Error: The path '{path}' is not a valid directory."
        items = os.listdir(path)
        logger.info(f"Listing items in directory: {path}")
        if not items:
            return f"The directory '{path}' is empty."
        
        # Add a marker to distinguish directories from files
        output_items = []
        for item in items:
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                output_items.append(f"{item}/  (Directory)")
            else:
                output_items.append(item)

        return "\n".join(output_items)
    except Exception as e:
        error_msg = f"Error: Failed to list directory '{path}'. Details: {e}"
        logger.error(error_msg, exc_info=True)
        return error_msg