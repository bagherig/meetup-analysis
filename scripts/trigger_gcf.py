import os
import sys
import json
import requests
import linecache
import threading
import urllib.parse as urlparse
from google.cloud import logging
from google.auth.exceptions import DefaultCredentialsError
from urllib.parse import urlencode
from typing import Generator, List
from custom_typing import Logger
from requests.exceptions import ChunkedEncodingError

TEST = False  # Whether we are running in test mode.
BUCKET_NAME = "meetup_stream_data"
if TEST:
    # noinspection PyRedeclaration
    BUCKET_NAME = "meetup_test"
    print("TEST MODE")
MAIN_LOGGER = None
HTTP_URL = \
    'https://us-central1-meetup-analysis.cloudfunctions.net/save_data'
URLS = ["http://stream.meetup.com/2/event_comments",
        "http://stream.meetup.com/2/open_events",
        "http://stream.meetup.com/2/open_venues?trickle",
        "http://stream.meetup.com/2/photos",
        "http://stream.meetup.com/2/rsvps"]


class HttpStream(object):
    """
    A class for streaming meetup data and triggering a google cloud
    function for storing the data in GCS.
    """
    def __init__(self,
                 stream_url: str,
                 http_url: str,
                 bucket_name: str,
                 prefix: str='meetup'):
        """
        initializes an instant of class *HttpStream*.

        :param stream_url: The URL to stream.
        :param http_url: The URL of the google cloud function to trigger.
        :param bucket_name: The name of the google cloud storage bucket
            for storing stream data.
        :param prefix: A label for describing the type of data
            that is being streamed.
        """
        self.url = stream_url
        self.http = http_url
        self.bucket_name = bucket_name
        self.prefix = prefix

    def __read_stream(self) -> Generator[dict, None, None]:
        """
        Reads the stream with URL self.url.

        :returns: The last data streamed from self.url.
        """
        mtime = None  # Variable for storing the timestamp of the last data
        # streamed.
        while True:
            url = self.url
            if mtime:  # This is not None if the stream has been interrupted
                # by an exception, after starting.
                new_params = {'since_mtime': mtime}
                url = add_url_params(url, new_params)
            print(f"Reading {self.prefix} stream... {url}", flush=True)
            try:
                with requests.get(url, stream=True) as r:
                    for line in r.iter_lines():
                        if line:
                            # The data is coming in JSON format.
                            json_data = json.loads(line.decode('utf-8'))
                            if mtime in json_data:  # Save timestamp of data.
                                mtime = json_data['mtime']
                            yield json_data
            except ChunkedEncodingError:
                # Log exceptions to Stackdriver-Logging.
                log_struct = {'desc': 'Chunked error while reading stream.',
                              'stream_url': url}
                log_struct.update(get_exc_info_struct())
                # noinspection PyTypeChecker
                MAIN_LOGGER.log_struct(log_struct, severity='NOTICE')
                print(f"Chunked error while reading stream: {log_struct}", flush=True)
            except Exception:
                log_struct = {'desc': 'Error while reading stream.',
                              'stream_url': url}
                log_struct.update(get_exc_info_struct())
                # noinspection PyTypeChecker
                MAIN_LOGGER.log_struct(log_struct, severity='EMERGENCY')
                print(f"Error while reading stream: {log_struct}", flush=True)
                continue

    # noinspection PyTypeChecker
    def trigger_http_function(self):
        """
        Triggers the GCF with url self.http with a POST request. Each POST
        request contains the last data streamed, as well as the GCS bucket
        name.
        """
        while True:
            stream = self.__read_stream()  # The stream generator.
            for item in stream:
                http_url = None
                try:
                    params = {"label": self.prefix,
                              "bucket_name": self.bucket_name}
                    http_url = add_url_params(self.http, params)
                    requests.post(http_url, json=item)
                except Exception:
                    # Log exceptions to Stackdriver-Logging.
                    log_struct = {'desc': 'Error while triggering GCF.',
                                  'gcf_url': http_url}
                    log_struct.update(get_exc_info_struct())
                    MAIN_LOGGER.log_struct(log_struct, severity='EMERGENCY')
                    print(f"Error while triggering gcf. {log_struct}",
                          flush=True)
                    continue


def connect_gcl(logger_name: str = "Trigger_GCF-Logger") -> Logger:
    """
    Sets the ``GOOGLE_APPLICATION_CREDENTIALS`` environmental variable for
    connecting to Stackdriver-Logging and initiates a new logger with name
    **logger_name**.

    :param logger_name: The name of the logger.
    :return: A Stackdriver Logger.

    .. note:: A google credentials file should exist in the current
    directory with the name ``meetup-analysis.json``.
    """
    print(f"Connecting {logger_name}...", flush=True)

    try:
        logging_client = logging.Client()
    except DefaultCredentialsError:
        google_env_var = "GOOGLE_APPLICATION_CREDENTIALS"
        credentials_path = os.path.join(os.getcwd(), 'meetup-analysis.json')
        if os.environ.get(google_env_var) is None:
            if os.path.exists(credentials_path):
                os.environ[google_env_var] = credentials_path
                print("Found google credentials.", flush=True)
            else:
                raise FileNotFoundError(
                    f'Could not find environmental variable [{google_env_var}]'
                    f' or the credentials file [{credentials_path}]')
        logging_client = logging.Client()

    logger = logging_client.logger(logger_name)  # Initiate a new logger.

    return logger


def add_url_params(url: str,
                   params: dict) -> str:
    """
    Returns a new URL from **url** containing the URL parameters **params**.

    :param url: The url to add parameters to.
    :param params: The URL parameters to add. This should be a dictionary.
    :return: A string representing the new URL containing the URL parameters
        param.

    .. note:: The parameter **url** can have existing URL parameters.
    """
    new_url = url

    try:
        # Add the new parameters to the URL.
        url_parts = urlparse.urlparse(url)
        query = dict(urlparse.parse_qsl(url_parts.query))
        query.update(params)
        url_parts = url_parts._replace(query=urlencode(query))
        new_url = urlparse.urlunparse(url_parts)
    except Exception:
        # Log exceptions to Stackdriver-Logging.
        log_struct = {
            'desc': 'Error while adding URL params.',
            'url': url,
            'params': params}
        log_struct.update(get_exc_info_struct())
        # noinspection PyTypeChecker
        MAIN_LOGGER.log_struct(log_struct, severity='ERROR')
        print(f'Error while adding URL params.', flush=True)

    return new_url


def write_stream(stream_url: str,
                 http_url: str,
                 bucket_name: str,
                 prefix: str):
    """
    Creates an instance of *HttpStream* and triggers its GCF.

    :param stream_url: The URL to stream.
    :param http_url: The URL of the google cloud function to
        trigger.
    :param bucket_name: The name of the google cloud storage
        bucket for storing stream data.
    :param prefix: A label for describing the type of data
        that is being streamed.
    """
    meetup_stream = HttpStream(stream_url=stream_url,
                               http_url=http_url,
                               bucket_name=bucket_name,
                               prefix=prefix)
    meetup_stream.trigger_http_function()


def save_data(stream_urls: List[str],
              http_url: str,
              bucket_name: str):
    """
    Creates a thread for each url in **stream_urls** and calls the
    ``write_stream`` function to save stream data in a GCS bucket named
    **bucket_name**, by triggering an http-triggered GCF with url
    **http_url**. The function waits for all threads to finish before
    exiting.

    :param stream_urls: The URLs to stream.
    :param http_url: The URL of the google cloud function to
        trigger.
    :param bucket_name: The name of the google cloud storage
        bucket for storing stream data.
    """
    print("Connecting to data streams...", flush=True)
    threads = []
    for url in stream_urls:
        prefix = url.split('/')[-1].split('?')[0]  # Set the prefix to be
        # the last path in the URL.
        threads.append(
            threading.Thread(
                target=write_stream,
                args=(url, http_url, bucket_name, prefix))
        )
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def get_exc_info_struct() -> dict:
    """
    Returns a dictionary containing information about the exception that is
    currently being handled.

    :return: A dictionary containing information about the exception that is
        currently being handled.
    """
    exc_struct = {}
    exc_type, exc_obj, tb = sys.exc_info()
    if not tb:  # This is None if no exception is being handled.
        return exc_struct
    f = tb.tb_frame
    line_num = tb.tb_lineno  # Line number.
    filename = f.f_code.co_filename  # File name.
    linecache.checkcache(filename)
    line = linecache.getline(filename, line_num, f.f_globals)  # Line content.
    exc_struct = {
        'exc_info': {
            'exc_msg': str(exc_obj),
            'filename': filename,
            'line_num': line_num,
            'line': line.strip(),
            'exc_obj': repr(exc_obj)
        }
    }

    return exc_struct


if __name__ == "__main__":
    MAIN_LOGGER = connect_gcl()  # Connect to google-cloud stackdriver logging.
    save_data(stream_urls=URLS,
              http_url=HTTP_URL,
              bucket_name=BUCKET_NAME)

    print("trigger_gcf.py is exiting!!!", flush=True)
    # noinspection PyTypeChecker
    MAIN_LOGGER.log_text("trigger_gcf.py is exiting!!!", severity='EMERGENCY')
