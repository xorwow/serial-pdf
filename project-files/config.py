## Configuration file for serial-pdf

from os.path import join as join_path

#########################
## Templating settings ##
#########################

## Paths

# Directory where PDFs are exported to when they are collected over the REST API
export_root: str = ... # TODO required

# Directory root for templates, must be a git root
template_root: str = ... # TODO required

# This maps the template IDs supplied by the REST caller to actual file paths
# The resulting path must be a folder containing a file like tex_entry_file
# It must also be a subdirectory of the template_root
def template_id_to_path(template_id: str) -> str:
    # Easiest solution is template_id = subpath of template root
    return join_path(template_root, template_id)

# Main file in each template folder which will always be used as compilation entry
tex_entry_file: str = 'main.tex'

## Placeholders

# Formats a simple placeholder from a key, returns pattern to search for and replacement
# The returned pattern is meant for simple string searches and may not be regex-safe
def placeholder_format(key: str, value: str) -> tuple[str, str]:
    # This format requires the serial-pdf.sty latex file to be imported in your templates
    # Backslashes are replaced for a rudimentary command injection protection
    return fr'\placeholder{{{ key }}}', str(value).replace('\\', '/')

# Formats a list placeholder from a key, returns pattern to search for and replacement
# The returned pattern is meant for simple string searches and may not be regex-safe
def placeholder_list_format(key: str, values: list[str]) -> tuple[str, str]:
    # This format requires the serial-pdf.sty latex file to be imported in your templates
    # Replacement string is built from a custom environment and custom items:
    # \begin{placeholders}[<len>] \lfitem[<index>]{<value>} ... \end{placeholders}
    replacement = fr'\begin{{placeholders}}[{ len(values) }]' + '\n'
    for index, entry in enumerate(values):
        # Backslashes are replaced for a rudimentary command injection protection
        entry = str(entry).replace('\\', '/')
        replacement += fr'\lfitem[{ index + 1 }]{{{ entry }}}' + '\n'
    replacement += r'\end{placeholders}' + '\n'
    return fr'\placeholderlist{{{ key }}}', replacement if values else ''

# Regex to search for files containing placeholders
# Should match the simple and list types of placeholders with any key
placeholder_regex: str = r'(\\placeholder(list)?\{[\w-]+\})'

###########################
## LaTeX -> PDF settings ##
###########################

## Conversion settings

# Maximum allowed parallel conversion processes
pdf_concurrency: int = 4

# Timeout for building a PDF, in seconds
latexmk_timeout: int = 60

## latexmk command building

# Path to latexmk binary (or 'latexmk' if in PATH)
# Get latexmk e.g. by installing texlive: https://www.tug.org/texlive/quickinstall.html
latexmk_path: str = 'latexmk'

# Arguments to latexmk
# Built as <latexmk_path> <latexmk_args> --outdir=<some tmpdir> --auxdir=<some tmpdir> --jobname=<some id> <tex source>
# Beware not to use quotation marks within the arguments, as latexmk interprets these literally
latexmk_args: list[str] = [
    '--gg',                      # Clean all output files for this tex file before starting new compilation
    '--cd',                      # Change into directory of provided input tex file
    '--interaction=nonstopmode', # Do not prompt to continue
    '--pdf',                     # PDF mode
    '-f',                        # Force compilation even with warnings
]

# Path to texlogfilter, used to extract errors from compilation logs (or 'texlogfilter' if in PATH)
# Set to None to skip this step
texlogfilter_path: str = 'texlogfilter'

######################
## Logging settings ##
######################

## Main log

# Main application logfile, will be rotated when full
# Rotated versions will have a suffix like '.1', '.2', etc.
log_file: str = ... # TODO required

# How large the log may get before being rotated
log_file_max_bytes: int = 1024 * 1024 * 250 # 250MB

# How many rotations of the log to keep (in addition to the main one)
log_file_max_rotations: int = 3 # (1 log + 3 backups) * 250MB = max. 1GB logs

## Compilation error logs

# Compilation logs of failed latexmk calls are stored here
# Relevant error log paths relative to here will be returned when a failed job is collected
pdf_error_log_root: str = ... # TODO required

# Maximum amount of compilation error logs stored before the oldest gets deleted (soft limit)
pdf_error_log_max_files: int = 50

# If pdf_error_log_max_files is exceeded, superflouos files will be deleted
# By setting this value above 0, additional files will be deleted when the limit is exceeded
# This prevents having to delete a file every time a new one is created by creating a "buffer"
# The value should be at least 0 and may not exceed pdf_error_log_max_files (less is recommended)
pdf_error_log_prune_extra_files: int = 5
