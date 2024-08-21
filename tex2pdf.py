# Template rendering and LaTeX -> PDF conversion system for serial-pdf

import logging, os, re
from subprocess import Popen, PIPE, TimeoutExpired
from tempfile import TemporaryDirectory
from uuid import uuid4
from time import time
from shutil import copyfile
from glob import glob
from itertools import chain as list_merger

import config, errors, util

log = logging.getLogger('serial-pdf')

class TexTemplate():
    """
    Represents a template folder with TeX entry file for compilation.
    Allows to render placeholders in the folder's files.
    """

    def __init__(self, template_id: str, entry_file: str, commit: str = 'HEAD') -> None:
        """
        Create a new template from a template ID.

        Arguments:
        - `template_id`: An ID that can be resolved using `config.template_id_to_path`
        - `entry_file`: Path to compilation entry file within template folder
        - `commit`: Optional commit hash to check out for template folder
        
        Exposes the following class variables:
        - `template_id`: As provided above
        - `entry_file`: As provided above, but converted to an absolute path if required
        - `commit`: As provided above
        - `template_folder`: Path of template folder as resolved from `template_id`
        """
        self.template_id: str = template_id
        self.entry_file: str = entry_file
        self.commit: str = commit
        # Process paths
        self.template_folder: str = os.path.abspath(config.template_id_to_path(self.template_id))
        if not os.path.isabs(self.entry_file):
            self.entry_file = os.path.join(self.template_folder, entry_file)

    def __repr__(self) -> str:
        return f"TexTemplate({ self.template_id } @ { os.path.relpath(self.entry_file, self.template_folder) } ({ self.commit }))"
    
    def folder_exists(self) -> bool:
        """
        Checks if the template's root folder currently exists.
        """
        exists: bool = util.git_file_exists(config.template_root, os.path.relpath(self.template_folder, config.template_root), self.commit)
        if not exists:
            log.error(f"Could not find template folder for ID '{ self.template_id }' at '{ self.template_folder }' (@{ self.commit })")
        return exists
    
    def entry_exists(self) -> bool:
        """
        Checks if the template's entry file currently exists.
        """
        exists: bool = util.git_file_exists(config.template_root, os.path.relpath(self.template_folder, config.template_root), self.commit)
        if not exists:
            log.error(f"Could not find template folder for ID '{ self.template_id }' at '{ self.template_folder }' (@{ self.commit })")
        return exists
    
    def _render_file(self, path: str | os.PathLike, data: dict[str, str | list[str]], check_unmatched=True) -> tuple[str, list[str]]:
        """
        Renders (i.e. fills in the placeholders of) a given file using the provided data dict.
        The rendered content is returned as a string. Optionally checks for missing placeholder data.

        Arguments:
        - `path`: Path to the file to be rendered
        - `data`: Dict of mappings `placeholder ID -> value(s) to fill in` for simple and list placeholders
        - `check_unmatched`: After rendering, check if any strings remain that look like placeholders with
                             a key we don't have any data for
            - When enabled, returns a list of possibly unmatched placeholder strings
            - When disabled, an empty list is returned

        Returns a tuple containing the rendered file contents and a list of unmatched strings that look like placeholders
        that we do not have values for (or an empty list if `check_unmatched` is falsy).
        """
        # Output rendering keys with list items marked using [] brackets
        available_keys = ', '.join([ f"[{ key }]" if type(data[key]) is list else key for key in data.keys() ])
        log.debug(f"Rendering file '{ path }' with available placeholder keys: { available_keys }")

        # Create a dictionary mapping complete placeholder patterns to replacement strings
        placeholder_data = {}
        for key in data:
            # Select simple or list placeholder format
            format_key = config.placeholder_list_format if type(data[key]) is list else config.placeholder_format
            # Create the placeholder string to search for and the replacement string
            pattern, replacement = format_key(key, data[key])
            placeholder_data[pattern] = replacement

        with open(path) as template_tex:
            content = template_tex.read()

        for placeholder in placeholder_data:
            content = content.replace(placeholder, placeholder_data[placeholder])

        # Check for strings that look like unmatched placeholders if enabled
        if check_unmatched and (unmatched := list(re.finditer(config.placeholder_regex, content))):
            # Extract each full regex match from our list of matches ignoring individual capture groups
            return content, list(map(lambda match: match.group(), unmatched))

        return content, []
    
    def render_all(self, target_dir: str | os.PathLike, data: dict[str, str | list[str]], check_unmatched=True) -> tuple[dict[str, list[str]], str]:
        """
        Renders (i.e. fills in the placeholders of) all files within this template's folder, recusively.
        The file tree will be rendered to the `target_dir` using the template files from version `commit`.

        Arguments:
        - `target_dir`: A directory to render the template files into
            - Should adhere to the constraints specified in `util.git_checkout` like no colliding paths
            - Any files already present in `target_dir` will also be rendered
        - `data`: Dict of mappings `placeholder ID -> value(s) to fill in` for simple and list placeholders
        - `check_unmatched`: After rendering, check if any strings remain that look like placeholders with
                             a key we don't have any data for
            - When enabled, returns a dict mapping `rel. file path -> list of unmatched placeholder strings`
            - When disabled, an empty dict is returned
        
        Returns a tuple containing a dict of unmatched placeholder strings sorted by relative file paths and the
        absolute path of the compilation entry file within the `target_dir`.
        """
        log.debug(f"Rendering template { self }")

        # Check out the template folder to our target_dir using the version set by self.commit
        template_subpath = os.path.relpath(self.template_folder, config.template_root)
        util.git_checkout(target_dir, config.template_root, template_subpath, self.commit)

        # Collect all file paths in target_dir which may contain placeholders
        matched_files = []
        for path in glob(f"{ target_dir }**/*.*", recursive=True):
            with open(path) as f:
                try:
                    if re.search(config.placeholder_regex, f.read()):
                        matched_files.append(path)
                except UnicodeDecodeError as e:
                    if os.path.splitext(path)[1] in [ 'tex', 'latex', 'sty' ]:
                        raise e
                    log.debug(f"File '{ os.path.relpath(path, target_dir) }' looks like a binary file, skipped rendering")
        
        # Render files and collect unmatched placeholders
        unmatched_placeholders = {}
        for path in matched_files:
            rendered, found_unmatched = self._render_file(path, data, check_unmatched=check_unmatched)
            if found_unmatched and os.path.basename(path) != 'serial-pdf.sty':
                # Store file path relative to target_dir/template_folder
                key = os.path.relpath(path, target_dir)
                unmatched_placeholders[key] = found_unmatched
            with open(path, 'w') as rendered_file:
                rendered_file.write(rendered)

        # Calculate new entry file path
        entry_path = os.path.join(target_dir, os.path.relpath(self.entry_file, self.template_folder))

        return unmatched_placeholders, entry_path

class PDFResult():
    """
    Represents a finished job, i.e. a compiled PDF from a rendered template sitting in the staging directory.
    Provides means of exporting the file to the export directory.
    """

    def __init__(self, id: str, path: str | os.PathLike, commit: str = 'HEAD', unmatched: dict[str, list[str]] | None = None,
                 processing_time: float = 0.) -> None:
        """
        Store a finished job for exporting.

        Arguments:
        - `id`: ID of the finished job
        - `path`: Path of the PDF in the staging directory, must be absolute
        - `commit`: Version of the template that was used
        - `unmatched`: Unmatched placeholders in the rendered template as provided by TexTemplate.render_all
        - `processing_time`: Time in seconds the job took to finish
        """
        self.id: str = id
        self.pdf_path: str = path
        self.commit: str = commit
        self.unmatched_placeholders: dict[str, list[str]] = unmatched or {}
        self.processing_time: float = processing_time
    
    def __repr__(self) -> str:
        warnings = ' with warnings' if self.unmatched_placeholders else ''
        return f"PDFResult({ self.id } @ { self.pdf_path } ({ self.commit }){ warnings }))"

    def export(self) -> dict[str, str | list[str] | float]:
        """
        Exports the compiled PDF from the staging directory to the export directory.
        
        Returns a dictionary with file information:
        - `export_file`: Path to the exported PDF relative to the export directory
        - `commit`: Version of the template that was used
        - `unmatched_placeholders`: Unmatched placeholders in the rendered template as provided by TexTemplate.render_all
        - `processing_time`: Time in seconds the job took to finish

        Raises an error if exporting fails.
        """
        export_path = os.path.join(config.export_root, f"{ self.id }.pdf")
        try: copyfile(self.pdf_path, export_path)
        except:
            raise errors.PDFExportFailure(f"Could not find or copy generated PDF file for { self }")

        return {
            # Return relative path to export root as an internal volume path isn't very useful outside a container
            'export_file': f"{ self.id }.pdf", 'commit': self.commit, 'unmatched_placeholders': self.unmatched_placeholders,
            'processing_time': self.processing_time
        }

class PDFJob():
    """
    Represents a job to be processed, i.e. a template and rendering data to be rendered & compiled into a PDF.
    """

    def __init__(self, template: TexTemplate, data: dict[str, list[str]], id: str | None = None) -> None:
        """
        Create a new rendering & compilation job.

        Arguments:
        - `template`: A TexTemplate to create the PDF from
        - `data`: A dictionary of rendering data mapping `placeholder ID -> value(s) to fill in`
                  for simple and list placeholders
        - `id`: Unique ID of the job, will be set to a 12-char UUID if left empty
        """
        self.template = template
        self.render_data = data
        self.id = id
        
        if id is None:
            self.id = str(uuid4())[-12:].upper()

    def __repr__(self) -> str:
        return f"PDFJob({ self.id } from { self.template })"

    def create_pdf(self, staging_dir: str | os.PathLike) -> PDFResult:
        """
        Renders the template using the given render data and compiles it into a PDF.

        Arguments:
        - `staging_dir`: Directory to store the compiled PDF in (flat, named <job ID>.pdf)

        Returns a PDFResult object containing the PDF path and compilation metadata.
        Raises an error if rendering or compilation fails.
        """
        log.debug(f"Building PDF '{ self.id }' from { self.template }")
        begin_time = time()

        # Create a temporary build directory holding the rendered template and auxiliary compilation files
        with TemporaryDirectory(prefix='build_') as build_dir:

            # Render all files in the template's directory and store the result in the build_dir
            # Returns unmatched placeholders and the path of the compilation entry file in our build_dir
            unmatched, entry_file = self.template.render_all(build_dir, self.render_data, check_unmatched=True)
            
            if unmatched:
                # unmatched is of format { <path>: list(<placeholder>, ...), ... }
                unique_placeholders = set(list_merger.from_iterable(unmatched.values()))
                log.warn(f"Found possibly unmatched placeholder(s) during template rendering:\n" +
                         f"File(s): { ', '.join(unmatched.keys()) }\n" +
                         f"Placeholder(s): { ', '.join(unique_placeholders) }")

            # Build latexmk args (each arg is quoted by Popen, no need to quote after the =; quotes are interpreted as literals)
            # The PDF is created as <outdir>/<jobname>.pdf with <auxdir> holding temporary build files
            args = config.latexmk_args.copy()
            args.extend([ f"--auxdir={ build_dir }", f"--outdir={ staging_dir }", f"--jobname={ self.id }", entry_file ])

            # Invoke latexmk to convert our rendered LaTeX to PDF
            log.debug(f"Running '{ config.latexmk_path }' with args: { ' '.join(args) }")
            proc = Popen(args, executable=config.latexmk_path, stdout=PIPE, stderr=PIPE, text=True, cwd=os.path.dirname(entry_file))

            def _copy_error_log():
                # Copy an error-filtered compilation log if it exists
                log_name = f"{ self.id }.log"
                log_path = os.path.join(build_dir, log_name)
                if os.path.exists(log_path):
                    # Extract error messages and write to error log directory
                    with open(log_path) as log_source, \
                         open(os.path.join(config.pdf_error_log_root, log_name), 'w') as log_target:
                        log_content = log_source.read()
                        log_target.write(util.filter_tex_log(log_content))
                    log.debug(f"Wrote compilation error log '{ log_name }' to the log directory")
                # Make sure the log directory does not contain too many files
                util.prune_dir(config.pdf_error_log_root, config.pdf_error_log_max_files, delete_extra=config.pdf_error_log_prune_extra_files)

            # Collect stdout/stderr and wait for completion or timeout
            try:
                stdout, stderr = proc.communicate(input=None, timeout=config.latexmk_timeout)
            # Check if the command timed out
            except TimeoutExpired:
                log.debug(f"Killing timed out latexmk process with pid { proc.pid }")
                proc.kill()
                _copy_error_log()
                raise errors.PDFConversionTimeout(f"PDF conversion failed: Timed out ({ config.latexmk_timeout }s)", proc.stdout.read(), proc.stderr.read())
            
            # Check if the command failed
            if proc.returncode != 0:
                _copy_error_log()
                raise errors.PDFConversionFailure(f"PDF conversion failed: latexmk return code was { proc.returncode }", stdout, stderr)
            
            # Check that a PDF file has been created
            pdf_path = os.path.join(staging_dir, f"{ self.id }.pdf")
            if not os.path.isfile(pdf_path) or not os.access(pdf_path, os.R_OK):
                raise errors.PDFConversionFailure(f"PDF conversion failed: output PDF not found/readable: '{ pdf_path }'", stdout, stderr)
            
            processing_time = round(time() - begin_time, 2)
            log.debug(f"Successfully built '{ pdf_path }' (took { processing_time }s)")

            return PDFResult(self.id, pdf_path, commit=self.template.commit, unmatched=unmatched, processing_time=processing_time)
