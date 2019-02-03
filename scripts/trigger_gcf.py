import os
import sys
import pytz
import json
import time
import datetime
import requests
import linecache
import threading
import numpy as np
import urllib.parse as urlparse
from enum import Enum
from google.cloud import logging
from custom_typing import Logger
from urllib.parse import urlencode
from typing import Generator, List, Union
from requests.exceptions import ChunkedEncodingError
from google.auth.exceptions import DefaultCredentialsError

LOGGER = None
URLS = ["http://stream.meetup.com/2/event_comments",
        "http://stream.meetup.com/2/open_events",
        "http://stream.meetup.com/2/open_venues?trickle",
        "http://stream.meetup.com/2/photos",
        "http://stream.meetup.com/2/rsvps"]


class ReqConfigs(Enum):
    stream_gcf = 'stream_gcf'
    gcs_bucket = 'stream_gcs_bucket'
    member_gcf = 'member_gcf'
    member_collection = 'member_fs_collection'
    group_gcf = 'group_gcf'
    group_collection = 'group_fs_collection'
    meetup_key = 'meetup_api_key'


class MeetupStream(object):
    """
    A class for streaming meetup data and triggering a google cloud
    function for storing the data in GCS.
    """

    def __init__(self,
                 url: str,
                 configs: dict):
        """
        Initializes an instant of class *HttpStream*.

        :param stream_url: The URL to stream.
        :param http_url: The URL of the google cloud function to trigger.
        :param bucket_name: The name of the google cloud storage bucket
            for storing stream data.
        :param prefix: A label for describing the type of data
            that is being streamed.
        """
        self._required_configs = \
            np.array([c.value for c in ReqConfigs.__members__.values()])
        self.url = url
        self.prefix = url.split('/')[-1].split('?')[0]  # Set the prefix to be
        # the last path in the URL.
        self.configs = configs
        is_config_not_provided = np.array(
            [key not in configs for key in self._required_configs])
        if any(is_config_not_provided):
            raise KeyError('Missing one or more config parameters:'
                           f'{self._required_configs[is_config_not_provided]}.')
        self.mtime = None  # Stores the timestamp of the last data streamed.

    def __read_stream(self) -> Generator[dict, None, None]:
        """
        Reads the stream with URL self.url.

        :returns: The last data streamed from self.url.
        """
        pprint(f"Reading {self.prefix} stream: {self.url}")
        while True:
            url = self.url
            if self.mtime:  # self.mtime is not None if the stream has been
                # interrupted by an exception, after starting.
                new_params = {'since_mtime': self.mtime}
                url = add_url_params(url, new_params)
            try:
                with requests.get(url, stream=True) as r:
                    for line in r.iter_lines():
                        if line:
                            # The data is coming in JSON format.
                            json_data = json.loads(line.decode('utf-8'))
                            if 'mtime' in json_data:  # Save timestamp of data.
                                self.mtime = json_data['mtime']
                            yield json_data
            except ChunkedEncodingError:
                # Log exceptions to Stackdriver-Logging.
                log_struct = {'desc': 'Chunked error while reading stream.',
                              'stream_url': url}
                log_struct.update(get_exc_info_struct())
                # noinspection PyTypeChecker
                LOGGER.log_struct(log_struct, severity='NOTICE')
                time.sleep(1)
                continue
            except Exception:
                log_struct = {'desc': 'Error while reading stream.',
                              'stream_url': url}
                log_struct.update(get_exc_info_struct())
                pprint(f"Error while reading stream:\n"
                       f"{json.dumps(log_struct, indent=4)}",
                       pformat=BColors.FAIL)
                # noinspection PyTypeChecker
                LOGGER.log_struct(log_struct, severity='EMERGENCY')
                time.sleep(1)
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
            for data_item in stream:
                try:
                    self.trigger_save_stream_data(data_item)
                    if 'member' in data_item and \
                            'member_id' in data_item['member']:
                        member_id = data_item['member']['member_id']
                        self.trigger_save_member_data(member_id)
                    if 'group' in data_item and \
                            'id' in data_item['group']:
                        group_id = data_item['group']['id']
                        self.trigger_save_group_data(group_id)
                except Exception:
                    # Log exceptions to Stackdriver-Logging.
                    log_struct = {
                        'desc': 'Error triggering Google Cloud Functions.'}
                    log_struct.update(get_exc_info_struct())
                    pprint(f"Error while triggering gcf.\n"
                           f"{json.dumps(log_struct, indent=4)}",
                           pformat=BColors.FAIL)
                    LOGGER.log_struct(log_struct, severity='EMERGENCY')
                    continue

    def trigger_save_stream_data(self, data):
        params = {
            "label": self.prefix,
            "bucket_name": self.configs[ReqConfigs.gcs_bucket.value]
        }
        http_url = self.configs[ReqConfigs.stream_gcf.value]
        http_url = add_url_params(http_url, params)
        r = requests.post(http_url, json=data)
        if r.status_code != 200:
            raise self.CloudFunctionError(
                f'GCF returned an error {r.status_code}. '
                f'The response is:\n{r.text}')

    def trigger_save_member_data(self, member_id):
        params = {
            "member_id": member_id,
            "meetup_key": self.configs[ReqConfigs.meetup_key.value],
            "collection": self.configs[ReqConfigs.member_collection.value]
        }
        http_url = self.configs[ReqConfigs.member_gcf.value]
        http_url = add_url_params(http_url, params)
        r = requests.post(http_url)
        if r.status_code != 200:
            raise self.CloudFunctionError(
                f'GCF returned an error {r.status_code}. '
                f'The response is:\n{r.text}')

    def trigger_save_group_data(self, group_id):
        params = {
            "group_id": group_id,
            "meetup_key": self.configs[ReqConfigs.meetup_key.value],
            "collection": self.configs[ReqConfigs.group_collection.value]
        }
        http_url = self.configs[ReqConfigs.group_gcf.value]
        http_url = add_url_params(http_url, params)
        r = requests.post(http_url)
        if r.status_code != 200:
            raise self.CloudFunctionError(
                f'GCF returned an error {r.status_code}. '
                f'The response is:\n{r.text}')

    class CloudFunctionError(Exception):
        pass


class BColors(Enum):
    """
    A list of color codes that can be used to format the color of text
    displayed in standard output.
    """
    TITLE = '\033[94m'
    HEADER = '\033[95m'
    OKBLUE = '\033[96m'
    OKWHITE = '\033[98m'
    WARNING = '\033[93m'
    OKGREEN = '\033[92m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def pprint(text: str,
           pformat: Union[BColors, List[BColors], str] = BColors.OKWHITE,
           timestamp: bool = True,
           timezone: pytz.tzfile = pytz.timezone('US/Eastern')) -> None:
    """
    Pretty prints the text in the specified format.

    :param text: the text to be printed.
    :param pformat: the format of the text.
    :param timestamp: Whether to add a timestamp to the beginning of text.
    :param timezone: The timezone of timestamp, if timestamp is True.
    """
    style = output = ""
    if isinstance(pformat, str):
        style = getattr(BColors, pformat.upper())
    elif isinstance(pformat, list):
        for fmt in pformat:
            style += fmt.value
    else:
        style = pformat.value

    if timestamp:
        ref_now = pytz.utc.localize(datetime.datetime.utcnow())
        local_now = ref_now.astimezone(timezone)
        now_str = local_now.strftime('%b %d, %H:%M:%S')
        timestamp_style = BColors.UNDERLINE.value + \
                          BColors.BOLD.value + \
                          BColors.HEADER.value
        output += timestamp_style + now_str + BColors.ENDC.value + " — "
    output += style + text + BColors.ENDC.value

    print(output, flush=True)


def __connect_gcl(logger_name: str = "Trigger_GCF-Logger") -> Logger:
    """
    Sets the ``GOOGLE_APPLICATION_CREDENTIALS`` environmental variable for
    connecting to Stackdriver-Logging and initiates a new logger with name
    **logger_name**.

    :param logger_name: The name of the logger.
    :return: A Stackdriver Logger.

    .. note:: A google credentials file should exist in the current
    directory with the name ``meetup-analysis.json``.
    """
    pprint(f"Initiating {logger_name}...")

    try:
        logging_client = logging.Client()
    except DefaultCredentialsError:
        google_env_var = "GOOGLE_APPLICATION_CREDENTIALS"
        credentials_path = os.path.join(os.getcwd(), 'meetup-analysis.json')
        if os.environ.get(google_env_var) is None:
            if os.path.exists(credentials_path):
                os.environ[google_env_var] = credentials_path
                pprint("Found google credentials.", pformat=BColors.OKGREEN)
            else:
                raise FileNotFoundError(
                    f'Could not find environmental variable [{google_env_var}]'
                    f' or the credentials file [{credentials_path}]')
        logging_client = logging.Client()

    logger = logging_client.logger(logger_name)  # Initiate a new logger.

    return logger


# def attempt_api_call(api_call: Callable,
#                      num_attempts: int = 5,
#                      sleep_time: float = 1,
#                      ignored_exceptions: Tuple[Exception]=(),
#                      ) -> Tuple[Any, bool]:
#     """
#     Attempts to call the *Callable* object ``api_call``. If the call fails,
#     the function sleeps for ``sleep_time`` milliseconds before attempting to
#     call ``api_call`` again. The function attempts to call ``api_call``
#     ``num_attempts`` times. If ``api_call`` fails because of an exception
#     included in ``ignored_exceptions``, ``api_call`` is not attempted again.
#
#     :param api_call: A Callable object to call.
#     :param num_attempts: The number of attempts for calling api_call.
#     :param sleep_time: The number of seconds to wait before each
#         reattempt.
#     :param ignored_exceptions: A tuple of Exceptions. If these
#         exceptions are thrown, api_call is not reattempted.
#     :return: A Tuple containing the return value of api_call and
#         whether the call was successful. If the call was not successful,
#         None is returned as the return value of api_call.
#     """
#     for attempt in range(num_attempts):
#         try:
#             obj = api_call()
#             if LOGGER and attempt:
#                 log_struct = {
#                     'desc': f'Successfully called API method.',
#                     'attempt': attempt,
#                     'api_call': str(api_call)}
#                 log_struct.update(get_exc_info_struct())
#                 # noinspection PyTypeChecker
#                 LOGGER.log_struct(log_struct, severity='INFO')
#             return obj, True
#         except ignored_exceptions:
#             return None, False
#         except Exception:
#             time.sleep(sleep_time)
#             if LOGGER:
#                 # Log exceptions to Stackdriver-Logging.
#                 log_struct = {
#                     'desc': f'API method call attempt failed!',
#                     'attempt': attempt,
#                     'api_call': str(api_call)}
#                 log_struct.update(get_exc_info_struct())
#                 # noinspection PyTypeChecker
#                 LOGGER.log_struct(log_struct, severity='WARNING')
#             continue
#     if LOGGER:
#         log_struct = {
#             'desc': f'Could not call the API method!',
#             'num_attempts': num_attempts,
#             'api_call': str(api_call)}
#         # noinspection PyTypeChecker
#         LOGGER.log_struct(log_struct, severity='ALERT')
#
#     return None, False


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
        pprint(f'Error while adding URL params.\n'
               f'{json.dumps(log_struct, indent=4)}',
               pformat=BColors.WARNING)
        # noinspection PyTypeChecker
        LOGGER.log_struct(log_struct, severity='ERROR')

    return new_url


def get_exc_info_struct() -> dict:
    """
    Returns a dictionary containing information about the exception that is
    currently being handled.

    :return: A dictionary containing information about the exception that is
        currently being handled.
    """
    exc_struct = {}

    try:
        exc_type, exc_obj, tb = sys.exc_info()
        if not tb:  # This is None if no exception is being handled.
            return exc_struct
        f = tb.tb_frame
        line_num = tb.tb_lineno  # Line number.
        filename = f.f_code.co_filename  # File name.
        linecache.checkcache(filename)
        line = linecache.getline(filename, line_num, f.f_globals)  # Line text.
        exc_struct = {
            'exc_info': {
                'exc_msg': str(exc_obj),
                'filename': filename,
                'line_num': line_num,
                'line': line.strip(),
                'exc_obj': repr(exc_obj)
            }
        }
    except Exception:
        pprint(f'Error while getting exception info.', pformat=BColors.WARNING)
        # Log exceptions to Stackdriver-Logging.
        log_text = 'Error while getting exception info.'
        # noinspection PyTypeChecker
        LOGGER.log_text(log_text, severity='ERROR')
        exc_struct = {'exc_info': 'Error: Could not retrieve exception info.'}

    return exc_struct


def write_stream(stream_url: str,
                 configs: dict):
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
    meetup_stream = MeetupStream(url=stream_url,
                                 configs=configs)
    meetup_stream.trigger_http_function()


def save_data(stream_urls: List[str],
              configs: dict) -> None:
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
    pprint("Connecting to data streams...")
    threads = []
    for url in stream_urls:
        threads.append(threading.Thread(target=write_stream,
                                        args=(url, configs)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def main():
    pprint("——— Starting ———",
           pformat=[BColors.TITLE, BColors.BOLD], timestamp=False)

    global LOGGER
    LOGGER = __connect_gcl()
    with open('../config.json') as json_configs_file:
        configs = json.load(json_configs_file)
    save_data(stream_urls=URLS,
              configs=configs)

    pprint("trigger_gcf.py is exiting!!!", pformat=BColors.WARNING)
    LOGGER.log_text("trigger_gcf.py is exiting!!!", severity='EMERGENCY')


if __name__ == "__main__":
    main()
