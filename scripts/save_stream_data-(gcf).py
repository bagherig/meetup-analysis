# -*- coding: utf-8 -*-
"""
Created on Fri Jan 11 18:09:12 2019
@author: moeen
"""
import sys
import datetime
import traceback
from typing import Tuple, Union
from google.cloud import storage
from google.api_core import exceptions
from urllib3.exceptions import ProtocolError

GS = storage.Client()


def save_stream_data(data: object,
                     data_id: Union[str, int],
                     bucket_name: str,
                     label: str = 'meetup') -> Tuple[str, int]:
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

    try:
        gcs_bucket = GS.get_bucket(bucket_name)
        gcs_file = gcs_bucket.blob(filename)
        gcs_file.upload_from_string(str(data))
    except exceptions.ServiceUnavailable as e:
        return traceback.format_exc(), int(e.code)
    except (ConnectionResetError, ConnectionError, ProtocolError):
        return traceback.format_exc(), 500
    except Exception:
        return f'Unknown Exception: {traceback.format_exc()}', 599
    else:
        return 'Success!', 200


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
        return "HTTP Parameter 'bucket_name' is not provided...", 400

    data = request.get_json()  # Parse the data that we want to store.
    if not data:
        return "No JSON data provided...", 400

    # Parse data_id:
    if label == 'rsvps':
        data_id = data['rsvp_id']
    elif label == 'photos':
        data_id = data['photo_id']
    else:
        data_id = data['id']

    response = save_stream_data(data=data,
                                data_id=data_id,
                                bucket_name=bucket_name,
                                label=label)

    return response
