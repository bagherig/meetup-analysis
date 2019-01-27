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
from typing import Tuple

LOGGING_CLIENT = LOGGER = None
try:
    LOGGING_CLIENT, _ = logging.Client
    LOGGER = LOGGING_CLIENT.logger('save_member_data-Logger(GCF)')
except Exception:
    pass


def main(request) -> Tuple[str, int]:
    """Responds to any HTTP request.

    :param request: HTTP request object.
    :return: A Tuple with a message and status-code regarding whether the
        request was processed successfully.
    """
    data = request.get_json()  # Parse the data that we want to store.
    if not data:
        LOGGER.log_text('No JSON data provided.', severity='EMERGENCY')
        return "No JSON data provided...", 400

    try:  # Parse data_id:
        data_id = data['id']
    except KeyError:
        data_id = "noID"
        log_struct = {
            'desc': f'Failed to parse data_id.',
            'data': json.dumps(data, indent=4, sort_keys=False)
        }
        # TODO: Make GCF for get_exc_info_struct()
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
