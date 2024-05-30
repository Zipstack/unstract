class ExceptionHelper:
    @staticmethod
    def extract_byte_exception(e: Exception) -> tuple[str, str]:
        error_message = str(e)
        error_code, error_details = eval(error_message)
        if isinstance(error_details, bytes):
            error_details = error_details.decode("utf-8")
        return error_code, error_message
