import os


def append_page_to_output(output_file: str, page_content: str, page_number: int) -> str:
    """
    Append a page to the output file.
    
    Args:
        output_file: Path to the output file
        page_content: Content of the page to append
        page_number: Page number being appended
    
    Returns:
        Confirmation message
    """
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # Append the page content to the output file
        with open(output_file, 'a', encoding='utf-8') as f:
            # If file is not empty, add a form feed character to separate pages
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                f.write('\f')  # Form feed character to separate pages
            f.write(page_content)
        
        return f"Successfully appended page {page_number} to {output_file}"
    
    except Exception as e:
        return f"Error appending page {page_number}: {str(e)}"


def clear_output_file(output_file: str) -> str:
    """
    Clear/delete the output file to start fresh.
    
    Args:
        output_file: Path to the output file to clear
    
    Returns:
        Confirmation message
    """
    try:
        if os.path.exists(output_file):
            os.remove(output_file)
            return f"Cleared output file: {output_file}"
        else:
            return f"Output file does not exist: {output_file}"
    
    except Exception as e:
        return f"Error clearing output file: {str(e)}"