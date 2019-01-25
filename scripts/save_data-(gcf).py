# -*- coding: utf-8 -*-
"""
Created on Fri Jan 11 18:09:12 2019
@author: moeen
"""
import sys
import time
import json
import datetime
import linecache
import firebase_admin
from typing import Callable, List, Tuple, Any, Union
from google.cloud import storage
from google.cloud import logging
from firebase_admin import firestore

LOGGING_CLIENT = LOGGER = None
try:
    LOGGING_CLIENT, _ = logging.Client
    LOGGER = LOGGING_CLIENT.logger('save_data-Logger(GCF)')
except Exception:
    pass


class Success(object):
    """
    A class to store the success value of an operation that is consisted
    of multiple smaller sub-operations. The operation is successful if all
    sub-operations are successful.

    .. note:: ``self._iterator`` counts the number of sub-operations.
    ``self._exceptions`` stores the value of self.iterator for
    unsuccessful sub-operations.
    """
    def __init__(self) -> None:
        """
        Initiates an instance of ``Success``.
        """
        self.value: bool = True
        self._iterator: int = 0  # Counts the number of sub-operations.
        self.exceptions: List[int] = []  # Stores the value of self.iterator
        #  for unsuccessful sub-operations.

    def __str__(self):
        return str(self.value)

    def __setattr__(self,
                    attr: str,
                    new_val: object):
        if attr == 'value' and self.__dict__.__contains__(attr):
            # The overall operation is successful if all sub-operations are
            # successful.
            self.__dict__[attr] = self.__dict__[attr] and new_val
            self._iterator += 1
            if not new_val:  # Store iteration of failed sub-operations.
                self.exceptions.append(self._iterator)
        else:
            self.__dict__[attr] = new_val


def get_exc_info_struct() -> dict:
    """
    Returns a dictionary containing information about the exception that is
    currently being handled.

    :return: A dictionary containing information about the exception that is
        currently being handled.
    """
    exc_type, exc_obj, tb = sys.exc_info()
    if not tb:  # This is None if no exception is being handled.
        return {}
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


def attempt_api_call(api_call: Callable,
                     num_attempts: int = 5,
                     sleep_time: float = 1,
                     ignored_exceptions: Tuple[Exception]=(),
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
    for attempt in range(num_attempts):
        try:
            obj = api_call()
            if LOGGER and attempt:
                log_struct = {
                    'desc': f'Successfully called API method.',
                    'attempt': attempt,
                    'api_call': str(api_call)}
                log_struct.update(get_exc_info_struct())
                # noinspection PyTypeChecker
                LOGGER.log_struct(log_struct, severity='INFO')
            return obj, True
        except ignored_exceptions:
            return None, False
        except Exception:
            time.sleep(sleep_time)
            if LOGGER:
                # Log exceptions to Stackdriver-Logging.
                log_struct = {
                    'desc': f'API method call attempt failed!',
                    'attempt': attempt,
                    'api_call': str(api_call)}
                log_struct.update(get_exc_info_struct())
                # noinspection PyTypeChecker
                LOGGER.log_struct(log_struct, severity='WARNING')
            continue
    if LOGGER:
        log_struct = {
            'desc': f'Could not call the API method!',
            'num_attempts': num_attempts,
            'api_call': str(api_call)}
        # noinspection PyTypeChecker
        LOGGER.log_struct(log_struct, severity='ALERT')

    return None, False


def save_data(data: object,
              data_id: Union[str, int],
              bucket_name: str,
              label: str = 'meetup') -> Success:
    """
    Stores ``data`` in a GCS bucket named ``bucket_name``. The data is
    stored in a folder named ``label``. ``data_id`` and the current
    timestamp is used to name the data file.

    :param data: The data to be stored in GCS.
    :param data_id: A unique ID for this data for naming purposes.
    :param bucket_name: The name of the GCS bucket to store the data in.
    :param label: The name of the folder within the GCS bucket in which the
        data is stored.
    :return: Returns type Success, representing whether all methods were
        successful or not.
    """
    current_time = datetime.datetime.now().timestamp()
    filename = f'{label}/{data_id}_{current_time}.json'
    success = Success()

    storage_client, success.value = \
        attempt_api_call(storage.Client)
    gcs_bucket, success.value = \
        attempt_api_call(lambda: storage_client.get_bucket(bucket_name))
    gcs_file, success.value = \
        attempt_api_call(lambda: gcs_bucket.blob(filename))
    _, success.value = \
        attempt_api_call(lambda: gcs_file.upload_from_string(str(data)))

    return success


def main(request) -> Tuple[str, int]:
    """Responds to any HTTP request.

    :param request: HTTP request object.
    :return: A Tuple with a message and status-code regarding whether the
        request was processed successfully.
    """
    bucket_name = label = ""
    label_par = 'label'
    bucket_name_par = 'bucket_name'
    if request.args:  # Parse GCS folder name (label) and bucket name.:
        if label_par in request.args:
            label = request.args.get(label_par)
        if bucket_name_par in request.args:
            bucket_name = request.args.get(bucket_name_par)
    if not label:
        label = "meetup"
    if not bucket_name:
        # noinspection PyTypeChecker
        LOGGER.log_text("HTTP Parameter 'bucket_name' is not provided.",
                        severity='EMERGENCY')
        return "HTTP Parameter 'bucket_name' is not provided...", 400

    data = request.get_json()  # Parse the data that we want to store.
    if not data:
        LOGGER.log_text('No JSON data provided.', severity='EMERGENCY')
        return "No JSON data provided...", 400

    try:  # Parse data_id:
        if label == 'rsvps':
            data_id = data['rsvp_id']
        elif label == 'photos':
            data_id = data['photo_id']
        else:
            data_id = data['id']
    except KeyError:
        data_id = "noID"
        log_struct = {
            'desc': f'Failed to parse data_id.',
            'label': label,
            'data': json.dumps(data, indent=4, sort_keys=False)
        }
        log_struct.update(get_exc_info_struct())
        # noinspection PyTypeChecker
        LOGGER.log_struct(log_struct, severity='WARNING')

    success: Success = \
        save_data(data=data,
                  data_id=data_id,
                  bucket_name=bucket_name,
                  label=label)
    # Check whether data was successfully stored or not:
    if success.value:
        return "Success!", 200
    else:
        log_struct = {
            'desc': f'Error in save_data GCF.',
            'failed_iters': success.exceptions}
        # noinspection PyTypeChecker
        LOGGER.log_struct(log_struct, severity='EMERGENCY')
        return f"Something went wrong... {success.exceptions}", 500
