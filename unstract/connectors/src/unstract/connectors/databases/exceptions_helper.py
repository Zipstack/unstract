import ast
from typing import Any


class ExceptionHelper:
    @staticmethod
    def extract_byte_exception(e: Exception) -> Any:
        """_summary_
        Extract error details from byte_exception.
        Used by mssql
        Args:
            e (Exception): _description_

        Returns:
            Any: _description_
        """
        error_message = str(e)
        error_code, error_details = ast.literal_eval(error_message)
        if isinstance(error_details, bytes):
            error_details = error_details.decode("utf-8")
        return error_details
