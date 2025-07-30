import os


def extract_pages(
    input_file: str,
    output_file: str,
    page_numbers: list[int] | None = None,
    append: bool = True,
) -> str:
    """Extract pages from a text file where pages are separated by form feed characters (\f).

    Args:
        input_file: Path to the input text file
        output_file: Path to the output file where extracted pages will be written
        page_numbers: List of page numbers to extract (1-indexed). If None, extracts all pages.
        append: If True, append to output file. If False, overwrite.

    Returns:
        Path to the output file
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Delete output file if it exists and not appending
    if not append and os.path.exists(output_file):
        os.remove(output_file)
        print(f"Deleted existing output file: {output_file}")

    # Read the input file
    with open(input_file, encoding="utf-8") as f:
        content = f.read()

    # Split content by form feed character
    pages = content.split("\f")

    # If no specific pages requested, extract all
    if page_numbers is None:
        extracted_pages = pages
    else:
        # Convert to 0-indexed and extract requested pages
        extracted_pages = []
        for page_num in page_numbers:
            if 1 <= page_num <= len(pages):
                extracted_pages.append(pages[page_num - 1])
            else:
                print(
                    f"Warning: Page {page_num} out of range (total pages: {len(pages)})"
                )

    # Write to output file
    mode = "a" if append else "w"
    with open(output_file, mode, encoding="utf-8") as f:
        for i, page in enumerate(extracted_pages):
            if i > 0:
                f.write("\f")  # Add form feed between pages
            f.write(page)

    return output_file


def extract_pages_with_content(
    input_file: str, output_file: str, search_content: str, append: bool = True
) -> str:
    """Extract pages that contain specific content.

    Args:
        input_file: Path to the input text file
        output_file: Path to the output file where extracted pages will be written
        search_content: Content to search for in pages
        append: If True, append to output file. If False, overwrite.

    Returns:
        Path to the output file
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Delete output file if it exists and not appending
    if not append and os.path.exists(output_file):
        os.remove(output_file)
        print(f"Deleted existing output file: {output_file}")

    # Read the input file
    with open(input_file, encoding="utf-8") as f:
        content = f.read()

    # Split content by form feed character
    pages = content.split("\f")

    # Find pages containing the search content
    matching_pages = []
    matching_page_numbers = []
    for i, page in enumerate(pages):
        if search_content.lower() in page.lower():
            matching_pages.append(page)
            matching_page_numbers.append(i + 1)

    if not matching_pages:
        print(f"No pages found containing: {search_content}")
        return output_file

    print(
        f"Found {len(matching_pages)} pages containing the search content (pages: {matching_page_numbers})"
    )

    # Write to output file
    mode = "a" if append else "w"
    with open(output_file, mode, encoding="utf-8") as f:
        for i, page in enumerate(matching_pages):
            if i > 0:
                f.write("\f")  # Add form feed between pages
            f.write(page)

    return output_file
