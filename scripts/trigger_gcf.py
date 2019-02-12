import os
import sys
import pytz
import json
import time
import http
import codecs
import inspect
import datetime
import requests
import traceback
import threading
import numpy as np
import urllib.parse as urlparse
from enum import Enum
from google.cloud import logging
from custom_typing import Logger
from urllib.parse import urlencode
from requests.exceptions import ChunkedEncodingError
from google.auth.exceptions import DefaultCredentialsError
from typing import Generator, List, Union, Tuple, Any, Callable
import subprocess

LOGGER = None
LOGGER_NAME = "Trigger_GCF-Logger"
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
                LOGGER.log_struct(log_struct, severity='EMERGENCY')
                time.sleep(1)
                continue

    def trigger_cloud_functions(self):
        """
        Triggers the GCF with url self.http with a POST request. Each POST
        request contains the last data streamed, as well as the GCS bucket
        name.
        """
        queue_size = 150
        members_queue = []
        groups_queue = []
        while True:
            stream = self.__read_stream()  # The stream generator.
            for data_item in stream:
                attempt_func_call(
                    self.trigger_save_stream_data, params=[data_item],
                    ignored_exceptions=(self.FatalCloudFunctionError,),
                    tag=self.prefix)
                if 'member' in data_item and \
                        'member_id' in data_item['member']:
                    member_id = data_item['member']['member_id']
                    members_queue.append(member_id)
                if 'group' in data_item and \
                        'id' in data_item['group']:
                    group_id = data_item['group']['id']
                    groups_queue.append(group_id)
            if len(members_queue) >= queue_size:
                _, success = attempt_func_call(
                    self.trigger_save_member_data, params=[members_queue],
                    ignored_exceptions=(self.FatalCloudFunctionError,),
                    tag=self.prefix)
                if success:
                    groups_queue.clear()

            if len(groups_queue) >= queue_size:
                _, success = attempt_func_call(
                    self.trigger_save_group_data, params=[groups_queue],
                    ignored_exceptions=(self.FatalCloudFunctionError,),
                    tag=self.prefix)
                if success:
                    groups_queue.clear()

    def trigger_http_gcf(self,
                         url: str,
                         data: dict = None,
                         params: dict = None):
        name = url.split('/')[-1]
        if params:
            url = add_url_params(url, params)
        with requests.post(url, json=data) as r:
            if r.status_code == http.HTTPStatus.TOO_MANY_REQUESTS or \
                    r.status_code >= 500:
                raise self.RetriableCloudFunctionError(r.status_code, r.text)
            elif r.status_code != http.HTTPStatus.OK:
                raise self.FatalCloudFunctionError(r.status_code, r.text)
            pprint(f'{name} GCF triggered!',
                   pformat=BColors.OKBLUE, title=True)

    def trigger_save_stream_data(self, data):
        params = {
            "label": self.prefix,
            "bucket_name": self.configs[ReqConfigs.gcs_bucket.value]}
        url = self.configs[ReqConfigs.stream_gcf.value]
        self.trigger_http_gcf(url, data=data, params=params)

    def trigger_save_member_data(self, member_id):
        params = {
            "member_id": member_id.strip('[]').replace(' ', ''),
            "meetup_key": self.configs[ReqConfigs.meetup_key.value],
            "collection": self.configs[ReqConfigs.member_collection.value]
        }
        url = self.configs[ReqConfigs.member_gcf.value]
        self.trigger_http_gcf(url, params=params)

    def trigger_save_group_data(self, group_id):
        params = {
            "group_id": group_id.strip('[]').replace(' ', ''),
            "meetup_key": self.configs[ReqConfigs.meetup_key.value],
            "collection": self.configs[ReqConfigs.group_collection.value]
        }
        url = self.configs[ReqConfigs.group_gcf.value]
        self.trigger_http_gcf(url, params=params)

    class CloudFunctionError(Exception):
        def __init__(self, status_code, response):
            self.code = status_code,
            self.response = response

    class FatalCloudFunctionError(CloudFunctionError):
        pass

    class RetriableCloudFunctionError(CloudFunctionError):
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
           title: bool = False,
           timestamp: bool = True,
           timezone: pytz.tzfile = pytz.timezone('US/Eastern')) -> None:
    """
    Pretty prints the text in the specified format.

    :param text: the text to be printed.
    :param pformat: the format of the text.
    :param timestamp: Whether to add a timestamp to the beginning of text.
    :param timezone: The timezone of timestamp, if timestamp is True.
    """
    if not title:
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
    else:
        output = f'\033]2;{text}\007'
        print(output, end='', flush=True)


def __connect_gcl(logger_name: str) -> Logger:
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
        credentials_path = os.path.join(os.getcwd(), '../meetup-analysis.json')
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


def attempt_func_call(api_call: Callable,
                      params: list = None,
                      num_attempts: int = 50,
                      base_sleep_time: float = 1,
                      added_sleep_time: float = 1,
                      max_sleep: float = 10,
                      ignored_exceptions: tuple = (),
                      tag: str = None
                      ) -> Tuple[Any, bool]:
    """
    Attempts to call the *Callable* object ``api_call``. If the call fails,
    the function sleeps for ``sleep_time`` milliseconds before attempting to
    call ``api_call`` again. The function attempts to call ``api_call``
    ``num_attempts`` times. If ``api_call`` fails because of an exception
    included in ``ignored_exceptions``, ``api_call`` is not attempted again.

    :param api_call: A Callable object to call.
    :param num_attempts: The number of attempts for calling api_call.
    :param sleep_time: The number of seconds to wait before each
        reattempt.
    :param ignored_exceptions: A tuple of Exceptions. If these
        exceptions are thrown, api_call is not reattempted.
    :return: A Tuple containing the return value of api_call and
        whether the call was successful. If the call was not successful,
        None is returned as the return value of api_call.
    """
    try:
        func_params = ', '.join(list(api_call.__annotations__.keys())[0:-1])
        func_str = f'{api_call.__name__}({func_params})'
    except Exception:
        func_str = str(api_call)

    for attempt in range(num_attempts):
        try:
            obj = api_call(*params)
            if attempt:
                log_struct = {
                    'desc': f'Successfully called the function.',
                    'attempts': attempt + 1,
                    'api_call': func_str,
                    'tag': tag or str(params)}
                pprint(f'{log_struct["desc"]}\n%s' % pretty_json(log_struct),
                       pformat=BColors.OKGREEN)
                if LOGGER:
                    LOGGER.log_struct(log_struct, severity='INFO')
            return obj, True
        except ignored_exceptions:
            log_struct = {
                'desc': f'Function call failed and was ignored!',
                'api_call': func_str,
                'tag': tag or str(params)}
            log_struct.update(get_exc_info_struct())
            pprint(f'{log_struct["desc"]}\n%s' % pretty_json(log_struct),
                   pformat=BColors.FAIL)
            if LOGGER:  # Log exceptions to Stackdriver-Logging.
                LOGGER.log_struct(log_struct, severity='WARNING')
            return None, False
        except Exception:
            if not attempt:
                log_struct = {
                    'desc': f'API method call attempt was unsuccessful!',
                    'api_call': func_str,
                    'tag': tag or 'N/A'}
                log_struct.update(get_exc_info_struct())
                pprint(f'{log_struct["desc"]}\n%s' % pretty_json(log_struct),
                       pformat=BColors.WARNING)
                if LOGGER:
                    LOGGER.log_struct(log_struct, severity='WARNING')
                time.sleep(min(base_sleep_time + added_sleep_time * attempt,
                               max_sleep))
            continue

    log_struct = {
        'desc': f'Failed to call API method!',
        'attempts': num_attempts,
        'api_call': func_str,
        'tag': tag or str(params)}
    if LOGGER:
        LOGGER.log_struct(log_struct, severity='ALERT')
    pprint(f'{log_struct["desc"]}\n%s' % pretty_json(log_struct),
           pformat=BColors.FAIL)
    return None, False


def get_exc_info_struct() -> dict:
    """
    Returns a dictionary containing information about the exception that is
    currently being handled.

    :return: A dictionary containing information about the exception that is
        currently being handled.
    """
    try:
        exc_type, exc_obj, tb = sys.exc_info()
        args = exc_obj.args
        params = inspect.signature(exc_obj.__init__).parameters
        trace = traceback.format_exc()

        exc_struct = {
            'exc_info': {
                'exc_type': str(exc_type),
                'exc_args': {
                    str(key):
                        (
                            (
                                f'\{{\n{str(args[i])}\n}}'
                                if '\n' in str(args[i])
                                else str(args[i])
                            )
                            if i <= len(args) - 1 else None
                        )
                    for i, key in enumerate(params)
                },
                'traceback': f'{{\n{trace}\n}}'
            }
        }
    except Exception as e:
        pprint(f'Error while getting exception info: {str(e)}',
               pformat=BColors.WARNING)
        # Log exceptions to Stackdriver-Logging.
        log_text = f'Error while getting exception info: {str(e)}'
        LOGGER.log_text(log_text, severity='ERROR')
        exc_struct = {'exc_info': 'Error: Could not retrieve exception info.'}

    return exc_struct


def pretty_json(json_str):
    return codecs.decode(json.dumps(json_str, indent=4), 'unicode_escape')


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
        pprint("Error while adding URL params.\n%s" %
               json.dumps(log_struct, indent=4).replace('\\n', '\n'),
               pformat=BColors.WARNING)
        LOGGER.log_struct(log_struct, severity='ERROR')

    return new_url


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
    meetup_stream.trigger_cloud_functions()


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
    LOGGER = __connect_gcl(LOGGER_NAME)
    with open('../config.json') as json_configs_file:
        configs = json.load(json_configs_file)
    save_data(stream_urls=URLS,
              configs=configs)

    pprint("trigger_gcf.py is exiting!!!", pformat=BColors.WARNING)
    LOGGER.log_text("trigger_gcf.py is exiting!!!", severity='EMERGENCY')


if __name__ == "__main__":
    subprocess.run('', shell=True)
    main()
