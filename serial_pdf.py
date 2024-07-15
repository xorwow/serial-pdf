#!/usr/bin/env python3

# Job management for serial-pdf

import logging, atexit
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor, Future
from threading import current_thread
from multiprocessing import Manager

import config
from tex2pdf import TexTemplate, PDFJob, PDFResult

log = logging.getLogger('serial-pdf')

class SerialPDF():
    """
    Job management / main interface for PDF templating & conversion.
    """

    def __init__(self, register_cleanup: bool = True, global_tracking: bool = True) -> None:
        """
        Initializes the job manager for serial-pdf, including a concurrent worker pool.

        Arguments:
        - `register_cleanup`: If truthy, the cleanup method will automatically be called on program exit
            - Uses atexit.register
        - `global_tracking`: Use multiprocessing.Manager to create global instances of job tracking lists/dicts
            - See class variables below for more info on tracking jobs
            - This is useful when queueing jobs from multiple threads, e.g. when using flask with multiple workers
        
        Exposes the following class variables:
        - `staging_root`: Path to the directory where finished PDFs are stored before being exported
        - `queued_jobs`: Tracks queued jobs as a list of job IDs
        - `finished_jobs`: Tracks jobs marked as done (but not yet exported) as an `id -> PDFResult` mapping
        - `failed_jobs`: Tracks jobs marked as failed as a list of job IDs
            - If an error compilation log has been saved, its path will be <PDF error log root>/<job ID>.log
        """
        # Generated PDFs are kept in a temporary staging dir until collected/exported
        self._staging_dir: TemporaryDirectory = TemporaryDirectory(prefix='staging_')
        self.staging_root: str = self._staging_dir.name
        log.debug(f"Using PDF staging dir '{ self.staging_root }' and PDF export dir '{ config.export_root }'")

        # Initialize worker pool for templating & conversion jobs
        self._worker_pool: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=config.pdf_concurrency)
        log.debug(f"Worker pool initialized with { config.pdf_concurrency } worker(s)")

        # Track queued, finished and failed jobs for easier querying of job states
        self.queued_jobs: list[str] = Manager().list() if global_tracking else []
        self.finished_jobs: dict[str, PDFResult] = Manager().dict() if global_tracking else {}
        self.failed_jobs: list[str] = Manager().list() if global_tracking else []
        
        # Register cleanup method for program exit
        if register_cleanup:
            log.debug(f"Registering { self } for cleanup on exit")
            atexit.register(self.cleanup)
    
    def __repr__(self) -> str:
        return f"SerialPDF({ self.staging_root })"

    def run_job(self, job: PDFJob) -> None:
        """
        Runs a job and stores the result in finished_jobs.
        Will be removed from queued_jobs after being stored in finished_jobs.
        If the job fails, the ID will be stored in failed_jobs and a logfile named <ID>.log
        might be created in the PDF error log root depending on the error type.
        """
        current_thread().name = job.id
        log.debug(f"Running job { job }")
        try:
            self.finished_jobs[job.id] = job.create_pdf(staging_dir=self.staging_root)
            log.debug(f"Finished job { job }")
        except Exception as e:
            log.exception(e)
            log.error(f"Could not finish job '{ job.id }' due to an error")
            self.failed_jobs.append(job.id)
        finally:
            try: self.queued_jobs.remove(job.id)
            except: pass

    def queue_job(self, template: TexTemplate, data: dict[str | list[str]]) -> str:
        """
        Queues a new PDFJob in the worker pool after building it from the given template and render data.
        A mapping of `id` to a worker pool Future object will be tracked in queued_jobs.
        """
        job = PDFJob(template, data)
        log.debug(f"Queueing job { job }")
        self._worker_pool.submit(self.run_job, job=job)
        self.queued_jobs.append(job.id)
        return job.id

    def cleanup(self) -> None:
        """
        This function should run at exit/shutdown to release resources and delete temporary directories.
        It is safe to call this function multiple times.
        """
        log.debug(f"Cleaning up { self }")
        self._staging_dir.cleanup()
        self._worker_pool.shutdown(wait=False, cancel_futures=True)
