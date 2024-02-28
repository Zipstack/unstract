import pypdf
from constants import FileType
from enums import CostUnits
from unstract.sdk.cache import ToolCache
from unstract.sdk.constants import LogLevel, ToolEnv
from unstract.sdk.tool.base import BaseTool


class OcrHelper:
    """Helper functions for Ocr tool."""

    def __init__(self, tool: BaseTool, use_cache: bool = False) -> None:
        self.cache: ToolCache = None
        self.use_cache = False
        self.tool = tool

        if use_cache:
            platform_host = self.tool.get_env_or_die(ToolEnv.PLATFORM_HOST)
            platform_port = self.tool.get_env_or_die(ToolEnv.PLATFORM_PORT)
            self.tool.stream_log("Check result in cache")

            self.cache = ToolCache(
                tool=self.tool,
                platform_host=platform_host,
                platform_port=int(platform_port),
            )
            self.use_cache = True

    def stream_error_and_exit(self, message: str) -> None:
        """Stream error log and exit.

        Args:
            message (str): Error message
        """
        self.tool.stream_log(message, level=LogLevel.ERROR)
        exit(1)

    def get_page_count(self, file: bytes, file_type_mime: str) -> int:
        """Count pages for billing purposes.

        Args:
            file (str): The path to the input file
            file_type_mime (str): The MIME type of the file

        Returns:
            int: page count
        """
        page_count = 1
        # Count pages in case of PDF for billing purposes
        if file_type_mime == FileType.APPLICATION_PDF:
            pdf_page_count = 0
            with open(file, mode="rb") as input_file_obj:
                pdf_reader = pypdf.PdfReader(input_file_obj)
                pdf_page_count = len(pdf_reader.pages)
            self.tool.stream_log(f"PDF page count: {pdf_page_count}")
            page_count = pdf_page_count
        return page_count

    def calculate_cost(
        self,
        file: bytes,
        file_type_mime: str,
        cached_result: bool = False,
    ) -> None:
        """Get cost and stream cost.

        Args:
            file (bytes): _description_
            file_type_mime (str): _description_
        """
        if cached_result:
            self.tool.stream_cost(
                cost=0.0,
                cost_units=CostUnits.CACHE.value,
            )
        else:
            page_count = self.get_page_count(
                file=file, file_type_mime=file_type_mime
            )
            self.tool.stream_cost(
                cost=float(page_count),
                cost_units=CostUnits.GOOGLE_PAGES.value,
            )

    def set_result_in_cache(
        self,
        key: str,
        result: str,
        cached_result: bool = False,
    ) -> None:
        """Get result from cache by the help of unstract Cache tool.

        Args:
            key (str): Cache key

        Required env variables:
            PLATFORM_HOST: Host of platform service
            PLATFORM_PORT: Port of platform service
        Returns:
            Optional[str]: result
        """

        if not self.use_cache:
            return None
        if not cached_result:
            self.cache.set(key, result)

    def stream_output_text_log(self, data: str) -> None:
        """Stream document text.

        Args:
            sql (str): _description_
        """
        data_text_for_log = "### OCR Output\n\n"
        if len(data) > 500:
            data_text_for_log = data[:500] + "...(truncated)"
        self.tool.stream_single_step_message(
            f"```json\n{data_text_for_log}\n```"
        )

    def time_taken(self, start_time: float, end_time: float) -> None:
        """Calculate Time difference.

        Args:
            start_time (float): _description_
            end_time (float): _description_
        """
        time_taken = end_time - start_time
        self.tool.stream_log(f"Time taken: {time_taken}")
