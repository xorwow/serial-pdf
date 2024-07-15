# serial-pdf

*Create dynamic PDF batches from LaTeX templates*

## Introduction

This project was motivated by a need to create many PDF letters with only a small amount of varying information (names, addresses, ...). By typing your template(s) in LaTeX and providing a JSON dict of placeholder data for each rendering job, PDFs containing the filled-in and rendered templates will be generated. The app can be used standalone or within a webserver to handle many PDF requests.

The app supports live changes to the templates during execution, versioned templates, list placeholders with custom formatting in LaTeX, multi-threaded job processing and provides a flask integration. It does however not come with a built-in authentication layer, which will have to be implemented in the webserver or your custom application.

## Installation

Clone this repository into a directory of your choosing. Then install the python requirements file. You might want to create a [virtual environment](https://docs.python.org/3/library/venv.html) for this. A python version of 3.11+ is recommended.

```sh
# Clone repository
git clone git@github.com:xorwow/serial-pdf.git
cd serial-pdf

# (Optional) Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip3 install -r requirements.txt
```

### texlive

serial-pdf uses `latexmk` to compile LaTeX into PDFs. This binary is provided by packages like `texlive`. A short installation guide can be found [here](https://tug.org/texlive/quickinstall.html).

Make sure `latexmk` is in your `PATH` or that you specify the path to the binary in the `config.py`.

## Quick start

It is recommended to read the setup and usage instructions carefully. However, if you just need a quick PDF compiled from a LaTeX file, here is a quick start:

```sh
# Setup template folder
mkdir -p templates/my_template
cd templates/my_template

# Create your LaTeX template
# Put a \placeholder{my_key} in it
edit main.tex

# Commit your changes (required)
git init
git commit -am 'first template'

# Edit your config and fill in all values marked by '...'
cd <repository folder>
cp project-files/config.py .
edit config.py

# Run flask development server
python3 app.py

# In another terminal:
curl --json '{"my_key": "my_string"}' 'http://localhost:5000/job/?template_id=my_template'
# Returns '{ "id": <some UUID> }'
curl 'http://localhost:5000/job/?id=<id from above>'
# Returns '{ "id": <given ID>, "state": <PENDING|READY|FAILED|NOT_FOUND>, <optional data> }'

# Tada! After the job is done, you should get a READY state and the path to your PDF within the export location you set in the config
# You can also check the app.log in your configured logging directory if something fails
```

## Setup

### Folders

Create a folder for your LaTeX templates. It should contain all of your PDF templates. You can choose how to organize them, as the `config.py` provides a way of changing how templates are found within the template root.

You template folder must be a git repository (root), as serial-pdf uses this to pull certain versions (commits) of templates so PDFs can be restored at a later point and live changes to the template folder do not mess up jobs which are already queued.

Create a second directory that finished PDFs can be exported into.

You might also want to  create a folder for your logs (and give permissions to serial-pdf). serial-pdf creates rotating app logs as well as compilation logs for failed jobs.

```sh
mkdir templates
cd templates

git init
# ... create your template files now ...
# Changes are only seen by serial-pdf after a commit
git commit -am 'init templates'

cd ..
mkdir export

mkdir -p logs/app
mkdir -p logs/failed_jobs
```

### Configuration

First, copy the configuration file template from `project-files/config.py` to the app root. Read the explanation for each option carefully and fill in appropriate values. The minimum set of entries you need to edit are the template path, export path and log paths (marked with `...`).

You can also customize how your placeholders look and in which format they are replaced, as well as how your templates are organized. In the given configuration template, the format provided by the custom LaTeX package `project-files/serial-pdf.sty` is used for placeholders and template IDs are direct subpaths of the template root (more about these features below).

No state is retained across runs.

## Usage

### Overview

In general, serial-pdf is structured around jobs. A job is a combination of a LaTeX template and a given set of placeholder data to be processed and compiled into a PDF. Each job is referenced by a unique job ID and its status can be polled asynchronously after it has been queued. When the job is done, its PDF file will be moved from a temporary staging location into the export directory the next time the job is polled.

### Templates & Placeholders

Each PDF you generate is bound to a LaTeX template it was compiled from. These templates are stored in subdirectories within the template root directory. How they are organized exactly is up to you, but each template must have its own folder containing a compilation entry LaTeX file as configured in `config.py`. Templates are referenced by template IDs, which are supplied to serial-pdf when creating a new job. They will be resolved to a path within the template root directory by a method specified in `config.py`.

In **any** files within these template directories, you may use placeholders in the format specified in `config.py`. These placeholders may either be replaced with simple text or by a list of strings. For example, you might want to insert a set of orders as a list placeholder and a total price below as a simple placeholder. That could look like this within your LaTeX file:

```latex
\placeholderlist{orders}

Sum Total: \placeholder{total-price}
```

While you can just write any string into your template files and treat it as a placeholder (it does not need to be a valid LaTeX command), you might want to make your placeholders a bit smarter: By importing a package like the provided `project-files/serial-pdf.sty` into your LaTeX file, these placeholders won't trigger syntax errors in your LaTeX code when you compile it outside of serial-pdf, but print the placeholders as bold red text within your PDF. The package also allows you to customize the formatting of your list placeholders for each of your LaTeX templates.

You can install `serial-pdf.sty` as a local texlive package, however that will mean that changes to the package will also be applied when rendering a template from an older commit which may have used an older version of `serial-pdf.sty`. Instead, you can also store the file within each of your templates, which will profit from the included git versioning system.

After installing the package or placing the file next to the LaTeX template, you can import and use it like this:

```latex
\usepackage{ifthen}
\usepackage{serial-pdf}

% Now insert \placeholder{key} or \placeholderlist{key} anywhere in your file(s)
% Check serial-pdf.sty for custom list formatting options

Recipe for cooking a \placeholder{MealName}:

% Example of a conditional using placeholders:
\def\ingredients{\placeholderlist{Ingredients}}
\ifthenelse{\equal{\ingredients}{}} % an empty string indicates an empty list
{ There are no ingredients listed for this recipe. }
{
    You need the following ingredients:
    \ingredients
}
```

### Importing from python

Currently, serial-pdf is not available as a python package. This means your code has to import `serial_pdf.py` directly. After doing that, you can instantiate a `SerialPDF` object and start queuing jobs. Check the class and method descriptions and the development notes below for more information.

### Web requests

When directly calling `app.py`, a flask development server will be started and listen on port 5000. Note that this server only serves one HTML worker thread, so parallel requests are not possible. It is recommended to use a real WSGI service and a proxy for production use (see next chapter).

The app serves the following endpoints:

- **/**: Index page, returns 200 if the server is up
- **/job**: Job management endpoint

The job endpoint allows you to query the status of a job by supplying the job's ID in a GET request, as well as create a new job by supplying template and data via a POST request:

#### GET / Query

URL Parameters:
- `id`: Alphanumeric ID of a job as previously returned by a POST request

Returns JSON fields:
- `id`: Job ID from parameter
- `state`: Current job status
    - `NOT_FOUND` indicates that the job is not known to the backend
    - `PENDING` indicates that the job is currently waiting in queue
    - `FAILED` indicates that the job could not be completed
        - Optionally adds JSON field `error_log` indicating the path of a compilation log relative
        to the error log root defined in the config (only available for compilation errors)
    - `READY` indicates that the PDF has just been exported
        - Adds JSON dict `pdf_data` with the following entries:
            - `export_file`: Path of the exported PDF relative to the export root defined in the config
            - `commit`: Commit hash of the template that was used
            - `unmatched_placeholders`: After filling in placeholders with the available keys, a scan for strings that look like remaining unfilled placeholders is started and the resulting mapping of `filename -> list of placeholders` is returned here
            - `processing_time`: How long the job was actively processing, as float measured in seconds

#### POST / Create

URL Parameters:
- `template_id`: The ID of the template to be used
- `commit` (optional): Commit hash of template to check out, defaults to current HEAD commit

Takes JSON request body: Provide a mapping of all placeholder keys to either string or list(string) values

Returns JSON fields:
- `id`: ID of created job, used to query status & results

#### Examples

```sh
# Render a template called 'my_template' which includes a placeholder 'Name' and a placeholder 'Age'
curl --json '{"Name": "Bob"}' 'http://localhost:5000/job/?template_id=my_template'
# Returns '{ "id": "43293bbbf537" }'

curl 'http://localhost:5000/job/?id=43293bbbf537'
# Returns '{ "id": "43293bbbf537", "state": "PENDING" }'
sleep 10
curl 'http://localhost:5000/job/?id=43293bbbf537'
# Returns
# { "id": "43293bbbf537",
#   "state": "READY", 
#   "pdf_data": {
#     "export_file": "43293bbbf537.pdf",
#     "commit": "976fee3",
#     "processing_time": 5.23,
#     "unmatched_placeholders": {
#       "main.tex": [ "\\placeholder{Age}" ]
#     }
#   }
# }
```

## Webserver & Container

In a production environment, you want to use an actual WSGI server and proxy to interact with serial-pdf and possibly implement authentication. These are setup guides for common choices:

### uWSGI

uWSGI is a python package that supplies WSGI/HTTP workers to the flask application. By copying `project-files/uwsgi.ini` to the project's root and running `uwsgi --ini uwsgi.ini`, workers will start listening for requests on the WSGI protocol (used by an external proxy) and/or a small built-in HTTP proxy, depending on your configuration. Note that the given ini file specifies 4 WSGI workers and that the app should be run as the user `serialpdf`.

### nginx

If you want to reach the app from outside your local machine or add a layer of authentication, a web proxy like nginx can provide these features. Copy `project-files/serial-pdf.nginx` to your `sites-available` directory, fill in the missing data and optionally uncomment authentication or LetsEncrypt support. Then link it to `sites-enabled` and reload your nginx service.

### Docker

Running serial-pdf inside a container provides additional security and easy management for restarting and querying the service. Use the provided `project-files/Dockerfile`. It includes comments with example `docker build` and `docker run` commands. The Dockerfile creates a user inside the container with the same ID as a user on the host you specify, to keep permission management simple.

## Performance

The RAM usage of serial-pdf should be fairly low, as most large data is kept on disk. However, as each running job checks out a template's directory to a different temporary location, the I/O load might be higher depending on the amount of active workers (it is difficult to cache these files, as their content is not only dependant on the file commit but also the filled in placeholder values). The CPU load scales with active worker amount as well, with most of it coming from the `latexmk` command, which takes a few seconds for each medium sized template.

## Development notes

### Overview

serial-pdf lives in `serial_pdf.py` and is wrapped by a flask application in `app.py`. `serial_pdf.py` provides a multi-worker job management for the `PDFJob` and `PDFResult` objects defined in `tex2pdf.py`, which handles the actual placeholder rendering and PDF compilation.

The app accesses a git'ed template root directory, which contains all LaTeX templates available to serial-pdf. Live changes to the templates are supported, and will be available after committing them. Workers still queued on an older version will check out the templates by the commit they were queued with.

Templates are rendered (filled in) by searching all files in the template directory for strings that look like placeholders (using a regex defined in the config), then checking out the template into a temporary folder and re-writing all files which contain placeholders.

The template is then compiled into a PDF by calling `latexmk` on the entry file in that template folder. The compiled PDF is held in a global temporary staging directory until the job's status is queried the next time (or `PDFResult.export` is called directly), at which point it will be moved to the permanent export directory.

No state is retained when the app stops or restarts and all temporary files are cleaned up.

### Relevant python files

Note that each class and method in serial-pdf has a docstring with more information.

#### app.py

Contains a flask wrapper around serial-pdf. Calling this file directly will start a development server with one HTTP worker. They are not to be confused with job workers, which render & compile templates, while HTTP workers queue jobs.

When using a WSGI server, `app:flask_app` is the entry point. The job states are held in variables in `pdf_app` available to all HTTP worker threads.

flask listens to unauthenticated HTTP.

#### serial_pdf.py

Holds the class `SerialPDF`, which creates a worker pool and exposes methods for queuing and running jobs. It also holds the variables `queued_jobs`, `finished_jobs` and `failed jobs`, which track job statuses. Note that directly writing to `queued_jobs` does not queue a job. Any failed job will be tracked in `failed_jobs`, and depending on the failure type a `<job ID>.log` compilation log will be copied to the error log directory specified in the config.

`SerialPDF` can be instructed to use a `multiprocessing.Manager` to make the job variables available to all calling threads. When disabled, each calling HTTP worker sharing a `SerialPDF` object will hold a local version of these variables.

When a `SerialPDF` object reaches its end of life, the temporary staging root and worker pool need to be cleaned up. You can either call the `cleanup` method yourself or instruct `SerialPDF` to clean up resources when the python process exits (using `atexit`). You can safely call this method multiple times.

#### tex2pdf.py

Provides classes for rendering a template folder's placeholders as well as compiling a rendered template into a PDF.

`TexTemplate` takes a template ID, a subpath to a compilation entry file i.e. main LaTeX file (you would usually supply the one defined in the config) and a commit controlling which version of the template will be checked out. By calling `render_all` with a target path and a mapping of placeholder data, the template will be checked out into the target directory and a search for placeholders in all contained files will begin. Each placeholder we have data for will be replaced in the checked out files. You can specify if a second search for unmatched placeholders should be performed, which will return a list of strings that look like placeholders we didn't have data for for each file.

`PDFJob` represents a template which can be rendered and compiled. By calling `create_pdf`, the above `render_all` method will be called, after which `latexmk` compiles the template's entry file into a PDF and cleans up the template files. The PDF will be stored in a (usually temporary) staging directory to be collected/exported later. A `PDFResult` is returned.

When a job fails during compilation, the compilation log will be stored as `<job ID>.pdf` in the error log directory specified in the config. The amount of logs in this directory is pruned to a set maximum.

A `PDFResult` contains the path to the compiled PDF in the staging directory, as well as metadata like the template commit and the unmatched placeholders. By calling `export`, the PDF will be moved to the export directory defined in the config and a dictionary of JSON-friendly metadata will be returned. This extra exporting step is used so that never-collected PDFs don't take up permanent disk space.

#### util.py

This util file provides helpers for git, directory pruning and logging.

The method `setup_logging` configures the `serial-pdf` logger to write INFO+ to stdout and DEBUG+ to a rotating file handler. It should only be called once.

`filter_tex_log` takes a LaTeX log as a string and returns a version filtered for warnings and errors. Uses `texlogfilter` as a backend.

`prune_dir` limits the amount of files in a directory by deleting excess files. Note that it only works on a flat directory of files, subdirectories will not be searched and not be counted against the maximum. The parameter `delete_extra` controls if extra files should be deleted once the maximum is exceeded. This allows a threshold system so pruning doesn't need to run for every new file once at capacity.

`current_head` returns the short commit hash of the current HEAD ref of a git repository.

`git_checkout` checks out a subdirectory or file of a certain commit version within a git repository to the supplied target directory. The given target may already exist, but not include any colliding filenames. If a file is checked out, it will be placed into the target directory. If a directory is checked out, its contents will be placed into the target.
