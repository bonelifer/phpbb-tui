"""Expected automation failures with stable machine codes and exit statuses."""


class CommandError(Exception):
    """Carry a public error identifier, safe explanation, and exit status."""

    def __init__(self, code: str, message: str, status: int = 2):
        super().__init__(message)
        self.code = code
        self.status = status
