"""
Line Number Prefixer Tool

This tool prefixes each line of a text file with its line number in the format:
0x0000: <line_content>

This is used to add precise line tracking to rent roll documents for better
location reference and debugging.
"""

import os


def prefix_lines_with_numbers(input_file: str, output_file: str) -> str:
    """
    Prefix each line of the input file with its line number.
    
    Args:
        input_file: Path to the input text file
        output_file: Path where the line-numbered output will be saved
        
    Returns:
        Success message with file paths and line count
    """
    try:
        # Check if input file exists
        if not os.path.exists(input_file):
            return f"Error: Input file does not exist: {input_file}"
        
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # Read input file and add line numbers
        with open(input_file, 'r', encoding='utf-8') as infile:
            lines = infile.readlines()
        
        # Write output with line number prefixes
        with open(output_file, 'w', encoding='utf-8') as outfile:
            for line_num, line in enumerate(lines, 1):
                # Remove trailing newline for processing, will add it back
                line_content = line.rstrip('\n\r')
                
                # Format line number as 0x0000 (hexadecimal with padding)
                hex_line_num = f"0x{line_num:04x}"
                
                # Write line with prefix
                outfile.write(f"{hex_line_num}: {line_content}\n")
        
        total_lines = len(lines)
        return f"Successfully processed {total_lines} lines from {input_file} to {output_file}"
        
    except Exception as e:
        return f"Error processing file: {str(e)}"


def remove_line_number_prefixes(input_file: str, output_file: str) -> str:
    """
    Remove line number prefixes from a text file.
    
    This is the reverse operation - removes "0x0000: " prefixes to restore
    the original text format.
    
    Args:
        input_file: Path to the line-numbered text file
        output_file: Path where the clean output will be saved
        
    Returns:
        Success message with file paths and line count
    """
    try:
        # Check if input file exists
        if not os.path.exists(input_file):
            return f"Error: Input file does not exist: {input_file}"
        
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # Read input file and remove line number prefixes
        with open(input_file, 'r', encoding='utf-8') as infile:
            lines = infile.readlines()
        
        # Write output with line number prefixes removed
        with open(output_file, 'w', encoding='utf-8') as outfile:
            for line in lines:
                # Remove trailing newline for processing
                line_content = line.rstrip('\n\r')
                
                # Check if line has the expected prefix format
                if line_content.startswith('0x') and ': ' in line_content:
                    # Find the first occurrence of ': ' and remove everything before it
                    colon_index = line_content.find(': ')
                    if colon_index != -1:
                        clean_line = line_content[colon_index + 2:]  # +2 to skip ': '
                        outfile.write(f"{clean_line}\n")
                    else:
                        # Fallback: write the line as-is if format is unexpected
                        outfile.write(f"{line_content}\n")
                else:
                    # Line doesn't have expected prefix, write as-is
                    outfile.write(f"{line_content}\n")
        
        total_lines = len(lines)
        return f"Successfully cleaned {total_lines} lines from {input_file} to {output_file}"
        
    except Exception as e:
        return f"Error processing file: {str(e)}"


def get_line_count(file_path: str) -> str:
    """
    Get the total number of lines in a file.
    
    Args:
        file_path: Path to the text file
        
    Returns:
        Message with line count or error
    """
    try:
        if not os.path.exists(file_path):
            return f"Error: File does not exist: {file_path}"
        
        with open(file_path, 'r', encoding='utf-8') as file:
            line_count = sum(1 for _ in file)
        
        return f"File {file_path} contains {line_count} lines"
        
    except Exception as e:
        return f"Error counting lines: {str(e)}"


# Test function for development
def test_line_prefixer():
    """Test the line number prefixer functionality."""
    # Create a test input file
    test_input = "test_input.txt"
    test_output = "test_output.txt"
    test_clean = "test_clean.txt"
    
    # Create test content
    test_content = """This is line 1
This is line 2
This is line 3 with special characters: !@#$%^&*()
This is line 4

This is line 6 (line 5 was empty)
Final line"""
    
    with open(test_input, 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    # Test prefixing
    result1 = prefix_lines_with_numbers(test_input, test_output)
    print(f"Prefix result: {result1}")
    
    # Show the prefixed content
    print("\nPrefixed content:")
    with open(test_output, 'r', encoding='utf-8') as f:
        print(f.read())
    
    # Test removing prefixes
    result2 = remove_line_number_prefixes(test_output, test_clean)
    print(f"Clean result: {result2}")
    
    # Show the cleaned content
    print("\nCleaned content:")
    with open(test_clean, 'r', encoding='utf-8') as f:
        print(f.read())
    
    # Clean up test files
    for file in [test_input, test_output, test_clean]:
        if os.path.exists(file):
            os.remove(file)
    
    print("Test completed!")


if __name__ == "__main__":
    test_line_prefixer()