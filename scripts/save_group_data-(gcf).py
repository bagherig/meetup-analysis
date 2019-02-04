# -*- coding: utf-8 -*-
"""
Created on Fri Jan 11 18:09:12 2019
@author: moeen
"""
import json
from typing import Tuple
from google.cloud import firestore
from urllib.request import urlopen
from urllib.error import HTTPError
from google.api_core import exceptions
from json.decoder import JSONDecodeError

DB = firestore.Client()


def save_group_data(group_id: str,
                    meetup_key: str,
                    collection_name: str) -> int:
    """
    Stores ``data`` in a Firestore repository named ``rep_name``. The
    data is stored in a folder named ``label``. ``data_id`` and the
    current timestamp is used to name the data file.

    :param member_id: The data to be stored on Firestore in JSON format.
    :param data_id: A unique ID for this data for naming purposes.
    :param bucket_name: The name of the GCS bucket to store the data in.
    :param label: The name of the folder within the GCS bucket in which the
        data is stored.
    :return: Returns type Success, representing whether all methods were
        successful or not.
    """
    doc_name = f'g{group_id}'
    meetup_url = 'https://api.meetup.com/2/groups'
    meetup_url += f'?group_id={group_id}&key={meetup_key}'

    try:
        with urlopen(meetup_url) as r:
            data = json.loads(r.read().decode('utf-8'))
    except (JSONDecodeError, HTTPError):
        return 500

    try:
        DB.collection(collection_name).document(doc_name).set(data, merge=True)
    except exceptions.ServiceUnavailable as e:
        return int(e.code)

    return 200


def main(request) -> Tuple[str, int]:
    """Responds to any HTTP request.

    :param request: HTTP request object.
    :return: A Tuple with a message and status-code regarding whether the
        request was processed successfully.
    """
    group_id = meetup_key = collection_name = None
    group_id_par = 'group_id'
    meetup_key_par = 'meetup_key'
    collection_par = 'collection'
    if request.args:
        if group_id_par in request.args:
            group_id = request.args.get(group_id_par)
        if meetup_key_par in request.args:
            meetup_key = request.args.get(meetup_key_par)
        if collection_par in request.args:
            collection_name = request.args.get(collection_par)
    if not all([group_id, meetup_key, collection_name]):
        return f'A parameter was not provided!', 400

    status_code = save_group_data(group_id=group_id,
                                  meetup_key=meetup_key,
                                  collection_name=collection_name)

    return "Finished!", status_code
