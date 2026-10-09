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
        # Drivers raise these as (error_code, error_details), sometimes wrapped
        # in a single tuple argument; read the args directly rather than
        # evaluating the server-supplied message.
        args = e.args
        if len(args) == 1 and isinstance(args[0], tuple):
            args = args[0]
        error_details = args[1] if len(args) >= 2 else str(e)
        if isinstance(error_details, bytes):
            error_details = error_details.decode("utf-8")
        return str(error_details).strip()
