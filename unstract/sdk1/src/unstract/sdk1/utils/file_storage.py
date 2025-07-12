import logging

from unstract.sdk1.file_storage.impl import FileStorage

logger = logging.getLogger(__name__)


class FileStorageUtils:
    @staticmethod
    def copy_file_to_destination(
        source_storage: FileStorage,
        destination_storage: FileStorage,
        source_path: str,
        destination_paths: list[str],
        chunk_size: int = 4096,
    ) -> None:
        """Copy a file from a source storage to one or more paths in a
        destination storage.

        This function reads the source file in chunks and writes each chunk to
        the specified destination paths. The function will continue until the
        entire source file is copied.

        Args:
            source_storage (FileStorage): The storage object from which
                the file is read.
            destination_storage (FileStorage): The storage object to which
                the file is written.
            source_path (str): The path of the file in the source storage.
            destination_paths (list[str]): A list of paths where the file will be
                copied in the destination storage.
            chunk_size (int, optional): The number of bytes to read per chunk.
                Default is 4096 bytes.
        """
        seek_position = 0  # Start from the beginning
        end_of_file = False

        # Loop to read and write in chunks until the end of the file
        while not end_of_file:
            # Read a chunk from the source file
            chunk = source_storage.read(
                path=source_path,
                mode="rb",
                seek_position=seek_position,
                length=chunk_size,
            )
            # Check if the end of the file has been reached
            if not chunk:
                end_of_file = True
            else:
                # Write the chunk to each destination path
                for destination_file in destination_paths:
                    destination_storage.write(
                        path=destination_file,
                        mode="ab",
                        seek_position=seek_position,
                        data=chunk,
                    )

                # Update the seek position
                seek_position += len(chunk)
