#!/usr/bin/env python3

# REST API wrapper for serial-pdf

import os, logging
from flask import Flask, jsonify, request, abort, g as flask_global

import config, util
from serial_pdf import SerialPDF
from tex2pdf import TexTemplate

## Logging & Setup

util.setup_logging()

log = logging.getLogger('serial-pdf')
log.info('Initializing serial-pdf')

# Create flask app and shared SerialPDF instance
flask_app: Flask = Flask('serial-pdf')
pdf_app: SerialPDF = SerialPDF(register_cleanup=True, global_tracking=True)

## Flask routes

@flask_app.route('/')
def root():
    """
    Flask route for the index page.
    """
    return f"<h1>serial-pdf is running with up to { config.pdf_concurrency } worker(s)</h1>"

@flask_app.route('/job/', methods=['GET', 'POST'])
def job():
    """
    Flask route for job management (query + create).
    
    GET request
    -----------
    Returns the status of a job & exports it if ready.

    Parameters:
    - `id`: alphanumeric ID of job as previously returned by a POST request

    Returns JSON fields:
    - `id`: job ID from parameters
    - `state`: current job status
        - `NOT_FOUND` indicates that the job is not known to the backend
        - `PENDING` indicates that the job is currently waiting in queue
        - `FAILED` indicates that the job could not be completed
            - optionally adds JSON field `error_log` indicating the path of a compilation log relative
            to the error log root defined in the config (only available for specific errors)
        - `READY` indicates that the PDF has just been exported
            - adds JSON field `pdf_data` with data dict as returned by PDFResult.export

    POST request
    ------------
    Creates & queues a new job.

    Parameters:
    - `template_id`: ID of template to use for rendering
    - `commit` (optional): commit hash of template version to render, defaults to current HEAD
    - JSON body of request: used as data dict for rendering the template

    Returns JSON fields:
    - `id`: ID of created job, used to query status & results
    """
    # Get the status of a job
    if request.method == 'GET':
        # Validate id parameter
        if (job_id := request.args.get('id', None, type=str)) is None or not job_id.isalnum():
            abort(400, 'Missing or bad parameter: id (alphanum)')

        # Build return data with NOT_FOUND as the default
        job_data = { 'id': job_id, 'state': 'NOT_FOUND' }

        # Check if the job is still processing/queued
        if job_id in pdf_app.queued_jobs:
            job_data['state'] = 'PENDING'

        # Check if the job has failed
        elif job_id in pdf_app.failed_jobs:
            job_data['state'] = 'FAILED'
            error_log = os.path.join(config.pdf_error_log_root, f"{ job_id }.log")
            if os.path.exists(error_log):
                # Export as relative path to error log root
                job_data['error_log'] = f"{ job_id }.log"
            try: pdf_app.failed_jobs.remove(job_id)
            except ValueError: pass

        # Check if the job has finished
        elif job_id in pdf_app.finished_jobs:
            try:
                # Export PDF
                job_data['pdf_data'] = pdf_app.finished_jobs[job_id].export()
                job_data['state'] = 'READY'
            except Exception as e:
                log.exception(e)
                log.error(f"Job with ID '{ job_id }' could not be exported! Deleting entry.")
                job_data['state'] = 'FAILED'
            finally:
                # Remove job from finished jobs
                pdf_app.finished_jobs.pop(job_id, None)

        return jsonify(job_data)

    # Create a new job, return ID
    elif request.method == 'POST':
        # Validate template_id parameter
        if (template_id := request.args.get('template_id', None, type=str)) is None:
            abort(400, 'Missing parameter: template_id')

        # Validate commit parameter (if not supplied, use HEAD)
        if (commit := request.args.get('commit', None, type=str)) is None or commit.upper() == 'HEAD':
            commit = util.current_head(config.template_root)
        elif not commit.isalnum():
            abort(400, 'Bad commit hash (should be alphanum)')

        # Create & validate template from template_id
        template = TexTemplate(template_id, config.tex_entry_file, commit=commit)
        if not template.folder_exists():
            abort(400, 'Could not find template associated with given template_id')
        if not template.entry_exists():
            abort(400, 'Could not find TeX main file associated with given template_id')

        # Validate JSON data (used as dict for template rendering)
        if (data := request.get_json(silent=True)) is None:
            abort(400, 'Request does not include valid JSON data for template rendering')

        # Create a new job and return its ID
        try:
            return jsonify({ 'id': pdf_app.queue_job(template, data) })
        except Exception as e:
            log.exception(e)
            log.error(f"Could not create new job for '{ template_id }'!")
            abort(501, 'Failed to create new job')

## Entry point for debug execution (production system should use WSGI entry)

def start_devel_server():
    log.info('Starting development REST server')
    flask_app.run(host='0.0.0.0', debug=True)
    log.info('Shutting down')

if __name__ == '__main__':
    start_devel_server()
