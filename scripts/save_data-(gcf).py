# -*- coding: utf-8 -*-
"""
Created on Fri Jan 11 18:09:12 2019

@author: moeen
"""
import time
import datetime
import firebase_admin
from typing import Callable
from google.cloud import storage
from google.cloud import logging
from collections import namedtuple
from firebase_admin import firestore


class Success(object):
    i = 0
    e = []

    def __init__(self):
        self.value = True

    def __setattr__(self, attr: str, new_val):
        if attr == 'value' and self.__dict__.__contains__(attr):
            self.__dict__[attr] = self.__dict__[attr] and new_val
            if not new_val:
                Success.e.append(Success.i)
            Success.i += 1
        else:
            self.__dict__[attr] = new_val


def attempt_api_call(api_call: Callable, num_attempts: int = 1, sleep_time: int = 1, report: bool = False,
                     ignored_exceptions=()) -> object:
    results = namedtuple("results", ["return_value", "was_successful"])
    for attempt in range(num_attempts):
        try:
            return results(api_call(), True)
        except ignored_exceptions:
            break
        except Exception as e:
            time.sleep(sleep_time)
            # TODO: Report to slack.
            continue

    return results(None, False)


def save_data(data, data_id, bucket_name: str, label: str = 'meetup'):
    success = Success()
    logging_client, success.value = attempt_api_call(logging.Client)
    logger, success.value = attempt_api_call(lambda: logging_client.logger('http_stream'))
    storage_client, success.value = attempt_api_call(storage.Client)
    gcs_bucket, success.value = attempt_api_call(lambda: storage_client.get_bucket(bucket_name))

    current_time = datetime.datetime.now().timestamp()
    filename = f'{label}/{data_id}_{current_time}.json'
    gcs_file, success.value = attempt_api_call(lambda: gcs_bucket.blob(filename))
    _, success.value = attempt_api_call(lambda: gcs_file.upload_from_string(str(data)))

    return success.value


def main(request):
    bucket_name = label = data = ""
    label_par = 'label'
    bucket_name_par = 'bucket_name'
    if request.args:
        if label_par in request.args:
            label = request.args.get(label_par)
        if bucket_name_par in request.args:
            bucket_name = request.args.get(bucket_name_par)
    if label == "": label = "meetup"
    if bucket_name == "":
        bucket_name = "meetup_stream_data"
        # return "Could not find argument 'bucket_name'...", 400

    data = request.get_json()
    if not data:
        return "No json data provided...", 400

    try:
        if label == 'rsvps':
            data_id = data['rsvp_id']
        elif label == 'photos':
            data_id = data['photo_id']
        else:
            data_id = data['id']
    except KeyError:
        data_id = "noID"
        # TODO: Report Slack

    success = save_data(data, data_id, bucket_name, label)

    if success:
        return "Success!", 200
    else:
        return f"Something went wrong... {Success.e}", 500
        # TODO: Report Slack
