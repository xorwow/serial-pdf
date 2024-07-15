# Custom exceptions for serial-pdf

## Error base classes

class CommandError(Exception):
    """Generic error for failed commands which may have had an out and/or err stream."""

    def __init__(self, message, stdout: str | None = None, stderr: str | None = None) -> None:
        """
        Creates a new CommandError with given message and optional stdout and stderr stream contents.
        """
        super().__init__(message)
        self.stdout: str = str(stdout or '')
        self.stderr: str = str(stderr or '')

    def __str__(self) -> str:
        """
        Outputs the error's message and captured stderr if available.
        """
        desc = super().__str__()
        if self.stderr:
            desc += f"\n-- BEGIN CAPTURED STDERR --\n{ self.stderr }\n-- END CAPTURED STDERR --\n"
        return desc

## LaTeX -> PDF conversion errors

class PDFConversionTimeout(CommandError):
    """The PDF conversion exceeded the configured timeout."""
    pass

class PDFConversionFailure(CommandError):
    """The PDF conversion encountered an error and failed."""
    pass

class PDFExportFailure(Exception):
    """Exporting the finished PDF from the staging directory failed."""
    pass
