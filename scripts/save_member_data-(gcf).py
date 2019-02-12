# -*- coding: utf-8 -*-
"""
Created on Fri Jan 11 18:09:12 2019
@author: moeen
"""
import json
import traceback
from typing import Tuple
from urllib.request import urlopen
from google.cloud import firestore
from json.decoder import JSONDecodeError
from urllib.error import HTTPError, URLError
from google.api_core.exceptions import ServiceUnavailable, DeadlineExceeded

DB = firestore.Client()


def save_member_data(member_id: str,
                     meetup_key: str,
                     collection_name: str) -> Tuple[str, int]:
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
    meetup_url = 'https://api.meetup.com/2/members/'
    meetup_url += f'?member_id={member_id}&key={meetup_key}'

    try:
        with urlopen(meetup_url) as r:
            data = json.loads(r.read().decode('utf-8'))
    except (JSONDecodeError, URLError):
        return traceback.format_exc(), 500
    except HTTPError as e:
        return traceback.format_exc(), int(e.code)

    if 'results' not in data:
        return f"Unexpected response: {data}", 500
    results = data['results']
    for result in results:
        try:
            member_data = results[result]
            doc_name = f"m{member_data['id']}"
            DB.collection(collection_name).document(doc_name).set(member_data,
                                                                  merge=True)
        except (ServiceUnavailable, DeadlineExceeded) as e:
            return traceback.format_exc(), int(e.code)
        except KeyError:
            return "Unexpected member data! 'id' not found...", 500

    return 'Success!', 200


def main(request) -> Tuple[str, int]:
    """Responds to any HTTP request.

    :param request: HTTP request object.
    :return: A Tuple with a message and status-code regarding whether the
        request was processed successfully.
    """
    member_id = meetup_key = collection_name = None
    member_id_par = 'member_id'
    meetup_key_par = 'meetup_key'
    collection_par = 'collection'
    if request.args:  # Parse GCS folder name (label) and bucket name.:
        if member_id_par in request.args:
            member_id = request.args.get(member_id_par)
        if meetup_key_par in request.args:
            meetup_key = request.args.get(meetup_key_par)
        if collection_par in request.args:
            collection_name = request.args.get(collection_par)
    if not all([member_id, meetup_key, collection_name]):
        return f'A parameter was not provided!', 400

    response = save_member_data(member_id=member_id,
                                meetup_key=meetup_key,
                                collection_name=collection_name)

    return response
