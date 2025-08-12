class ExceptionHelper:
    @staticmethod
    def extract_byte_exception(e: Exception) -> str:
        """Extract error details from byte_exception.
        Used by mssql and mysql connectors.

        Args:
            e (Exception): Database exception to extract details from

        Returns:
            str: Extracted and stripped error details as string
        """
        error_message = str(e)
        error_code, error_details = eval(error_message)
        if isinstance(error_details, bytes):
            error_details = error_details.decode("utf-8")

        # Ensure we return a stripped string regardless of original type
        return str(error_details).strip()
