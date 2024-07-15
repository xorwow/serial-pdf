# Utility helpers for serial-pdf

import os, re, logging, logging.handlers
from shlex import quote as shell_escape
from shutil import move as move_path
from subprocess import run as proc_run, check_output, PIPE
from tempfile import TemporaryDirectory
from multiprocessing import Lock

import errors, config

log = logging.getLogger('serial-pdf')

## Logging helpers

def setup_logging() -> None:
    """
    Sets up a console logger (INFO+) and a rotating file logger (DEBUG+ with datetime).
    """
    # Create sysout handler (INFO+)
    sysout_handler = logging.StreamHandler()
    sysout_handler.setLevel(logging.INFO)
    sysout_handler.setFormatter(logging.Formatter('[%(levelname)s] (@%(threadName)s) %(message)s'))
    log.addHandler(sysout_handler)

    # Create rotating logfile handler (DEBUG+ with datetime)
    file_handler = logging.handlers.RotatingFileHandler(
        config.log_file, maxBytes=config.log_file_max_bytes,
        backupCount=config.log_file_max_rotations, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] (@%(threadName)s) %(message)s', datefmt='%d.%m.%Y %H:%M:%S %Z%z')
    file_handler.setFormatter(file_formatter)
    log.addHandler(file_handler)

    log.setLevel(logging.DEBUG)

def filter_tex_log(log_content: str) -> str | None:
    """
    Extracts all warnings and errors from a LaTeX compilation log file.
    Returns original content if extraction fails.
    """
    if config.texlogfilter_path:
        try:
            # Use texlogfilter to extract errors and warnings
            filtered = check_output([ config.texlogfilter_path ], input=log_content, encoding='utf-8').strip().strip('\n')
            # Remove color sequences created by filtering
            filtered = re.sub(r'(?i)\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', filtered)
            return filtered
        except Exception as e:
            log.exception(e)
            log.error(f"Could not extract errors from LaTeX log")

    return log_content

## File & Git helpers

def prune_dir(path: str | os.PathLike, max_files: int, delete_extra: int = 0) -> None:
    """
    If more files are present in the given directory than specified, delete the oldest ones.
    Warning: Only files in the directory's root are considered (non-recursive).

    Arguments:
    - `path`: The directory root.
    - `max_files`: Maximum files allowed in the directory before pruning.
    - `delete_extra` (0 <= delete_extra <= max_files): If max_files is exceeded and delete_extra is >0,
       an additional delete_extra files will be removed.
    """
    log.debug(f"Pruning directory '{ path }', allowing { max_files } file(s)")
    # Get all children of specified directory and filter for files
    child_paths = map(lambda name: os.path.abspath(os.path.join(path, name)), os.listdir(path))
    child_files = list(filter(lambda x: os.path.isfile(x), child_paths))
    # Remove oldest files (+ delete_extra) if exceeding max_files
    if len(child_files) <= max_files:
        log.debug('File limit not exceeded, skipping')
        return
    to_remove = sorted(child_files, key=os.path.getctime, reverse=True)[(max_files - delete_extra):]
    log.debug(f"Removing { len(to_remove) } file(s): { ', '.join(to_remove) }")
    for file in to_remove:
        try: os.unlink(file)
        except: pass

def current_head(repo_dir: str) -> str:
    """
    Returns commit hash of HEAD ref for given repository root.
    """
    return check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=repo_dir, text=True).strip().strip('\n')

# Git checkout requires a lock as checking out creates a git lock file, causing parallel checkouts to fail
git_index_lock = Lock()

def git_checkout(target_dir: str, repo_path: str, subpath: str = '.', commit: str = 'HEAD') -> None:
    """
    Checks out a directory or file within a git repository to a different directory. Can retrieve a specific commit.

    Arguments:
    - `target_dir`: The directory to check out the file(s) into. If subpath is a file, it will appear within the target_dir.
                    If subpath is a directory (or '.'), its contents will appear within the target_dir. The target_dir may
                    not contain any colliding filenames.
    - `repo_path`: Root path of the repository to check out from.
    - `subpath`: Must be a path within the repository. Will be checked out into the target_dir.
    - `commit`: Repository version to check out, instead of using HEAD.
    """
    # Convert subpath to a relative path within the repository
    if os.path.isabs(subpath):
        subpath = os.path.relpath(subpath, repo_path)
    
    # Due to git creating a parent folder structure, we need a temporary buffer dir
    with TemporaryDirectory(prefix='git_checkout_') as workdir:

        # Run a git checkout command that clones a subpath of the repo to a different directory
        git_command = [ 'git', f"--work-tree={ workdir }", 'checkout', shell_escape(commit), '--', shell_escape(subpath) ]
        with git_index_lock:
            proc_result = proc_run(git_command, cwd=repo_path, stdout=PIPE, stderr=PIPE)
        if proc_result.returncode != 0:
            raise errors.CommandError(
                f"git checkout command failed (subpath '{ subpath }', commit '{ commit }')",
                stdout=proc_result.stdout,
                stderr=proc_result.stderr
            )

        # git will have created the entire parent tree within the temporary dir
        # So we move the head of the structure to our target dir
        # We don't just rename the head to the target dir because any previous files in it would be lost
        # => <tmpdir>/<subpath>/<files> -> <target_dir>/<files>
        head = os.path.join(workdir, os.path.dirname(subpath) if os.path.isfile(subpath) else subpath)
        for child in os.listdir(head):
            move_path(os.path.join(head, child), os.path.join(target_dir, child))
