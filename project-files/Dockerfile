## Dockerfile for running serial-pdf through uWSGI
# 
# Expects serial-pdf repo to be a subdirectory of PWD
# Expects a data subdirectory containing a uwsgi.ini and a config.py
# 
# Build example:
# docker build -t serial-pdf --build-arg="USER_ID=<user ID of volume owner>" .
# 
# Run example (with portable texlive installation passed as a volume):
# docker run -p 5000:5000 -p 5001:5001 \
#            -v "$VOLUME_ROOT/logs:/home/serialpdf/log" \
#            -v "$VOLUME_ROOT/export:/home/serialpdf/export" \
#            -v "$VOLUME_ROOT/templates:/home/serialpdf/templates" \
#            -v "$VOLUME_ROOT/texlive:/home/serialpdf/texlive:ro" \
#            --name serial-pdf --rm serial-pdf

# Use python as base image (cannot use slim image because uwsgi needs a C compiler)
FROM python:3.11

# Take UID (= GID) of the user the volumes are owned by on the host
ARG USER_ID

# Create user and home folder for the specified UID/GID
RUN groupadd -fg "$USER_ID" serialpdf
RUN useradd -ms /bin/bash -d /home/serialpdf -u "$USER_ID" -g "$USER_ID" serialpdf
WORKDIR /home/serialpdf

# Main log directory (error logs are stored in subdir error_logs)
VOLUME log
# PDF export directory
VOLUME export
# Template directory root
VOLUME templates
# Texlive installation root
VOLUME texlive

# Copy our serial-pdf folder to the working directory
COPY serial-pdf serial-pdf

# Set the working directory to our PDF converter
WORKDIR serial-pdf

# Copy our config file
COPY data/config.py .

# Copy our uWSGI config
COPY data/uwsgi.ini .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir uWSGI

# Ensure proper file permissions
RUN chown -R "$USER_ID:$USER_ID" /home/serialpdf

# Add texlive to PATH
ENV PATH="${PATH}:/home/serialpdf/texlive/bin/x86_64-linux/"

# Expose our (unauthenticated) HTTP listening port
EXPOSE 5000
# Expose our uwsgi socket (for proxies like nginx)
EXPOSE 5001

# Command to run the Flask application (must be run as root)
CMD [ "uwsgi", "--ini", "uwsgi.ini" ]
