import sys
import json
import base64
import requests
import datetime
import linecache
import itertools
from google.cloud import logging


def get_exc_info_struct():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    line_num = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, line_num, f.f_globals)
    exc_struct = {
        'exc_msg': str(exc_obj),
        'filename': filename,
        'line_num': line_num,
        'line': line.strip(),
        'exc_obj': exc_obj
    }

    return exc_struct


def get_fields_from_json(json: dict, root: str = ""):
    fields = []
    for key in json:
        value = json[key]
        if isinstance(value, dict):
            new_root = f"{root}/{key}" if root else key
            fields.append(get_fields_from_json(json=value, root=new_root))
        else:
            value = f"```{json[key]}```"
            new_field = {
                'title': f"{root}/{key}" if root else key,
                'value': value,
                'short': False if len(value) > 40 else True
            }
            fields.append([new_field])
    return list(itertools.chain.from_iterable(fields))


def format_slack_message(content):
    json_data = json.loads(content)
    logger = json_data['logName'].split('/')[-1]
    severity = json_data['severity']
    ts = datetime.datetime.now().timestamp()
    color = 'good'
    if severity in ('WARNING', 'ERROR'):
        color = 'warning'
    elif severity in ('CRITICAL', 'ALERT', 'EMERGENCY'):
        color = 'danger'
    if 'jsonPayload' in json_data:
        json_payload = json_data['jsonPayload']
        fields = get_fields_from_json(json_payload)
        message = {
            "attachments": [
                {
                    "author_name": logger,
                    "text": f"_{json_payload['desc']}_",
                    "color": color,
                    "fields": fields,
                    "footer": severity,
                    "ts": ts,
                    "mrkdwn_in": ["text", "fields"]
                }
            ]
        }
    else:
        message = {
            "attachments": [
                {
                    "author_name": logger,
                    "text": f"_{json_data['textPayload']}_",
                    "color": color,
                    "footer": severity,
                    "ts": ts,
                    "mrkdwn_in": ["text"]
                }
            ]
        }

    return message


def report_slack(content):
    webhook_url = 'https://hooks.slack.com/services/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'
    message = format_slack_message(content)
    response = requests.post(
        webhook_url, data=json.dumps(message),
        headers={'Content-Type': 'application/json'})

    if response.status_code != 200:
        raise ValueError(
            f"Request to slack returned an error {response.status_code}, the response is:\n{response.text}")


def main(event, context):
    """Triggered from a message on a Cloud Pub/Sub topic.
    Args:
         event (dict): Event payload.
         context (google.cloud.functions.Context): Metadata for the event.
    """
    logging_client = logging.Client()
    logger = logging_client.logger("pubsub")
    try:
        if 'data' in event:
            pubsub_message = base64.b64decode(event['data']).decode('utf-8')
            report_slack(pubsub_message)
    except Exception as e:
        log_struct = {'desc': 'Error pubsub.'}
        log_struct.update(get_exc_info_struct())
        logger.log_struct(log_struct)
