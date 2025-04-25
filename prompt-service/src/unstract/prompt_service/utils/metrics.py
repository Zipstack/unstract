import datetime


class Metrics:
    @staticmethod
    def elapsed_time(start_time) -> float:
        """Returns the elapsed time since the process was started."""
        return (datetime.datetime.now() - start_time).total_seconds()
