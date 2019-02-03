import os
import json
import base64
import requests
import datetime
import itertools

SPAMS = []
LAST_REPORT = None
LAST_TIME = 0


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
    logger = json_data['logName'].split('/')[-1].split('%2F')[-1]
    severity = json_data['severity']
    ts = datetime.datetime.now().timestamp()
    color = 'good'
    if severity in ('WARNING', 'ERROR'):
        color = 'warning'
    elif severity in ('CRITICAL', 'ALERT', 'EMERGENCY'):
        color = 'danger'

    report_text = ''
    payload = {}
    if 'jsonPayload' in json_data:
        payload = json_data['jsonPayload']
        if 'desc' in payload:
            report_text = payload['desc']
    elif 'protoPayload' in json_data:
        payload = json_data['protoPayload']
    elif 'textPayload' in json_data:
        report_text = json_data['textPayload']
        payload = json_data['resource']['labels']

    fields = get_fields_from_json(payload)
    message = {
        "attachments": [
            {
                "author_name": logger,
                "text": f"```{report_text}```" if report_text else "",
                "color": color,
                "fields": fields,
                "footer": severity,
                "ts": ts,
                "mrkdwn_in": ["text", "fields"]
            }
        ]
    }

    # Prevent from spamming the channel with same error.
    global LAST_REPORT, LAST_TIME
    spam_wait_time = 60  # how many seconds to block messages received that are
    # the same as the last message received.
    now = int(datetime.datetime.now().timestamp())
    message_json = json.dumps(message)
    if message_json == LAST_REPORT and \
            now - LAST_TIME < spam_wait_time:
        return

    LAST_REPORT = message_json
    LAST_TIME = now

    return message


def report_slack(content):
    webhook_url = 'https://hooks.slack.com/services/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'
    message = format_slack_message(content)
    if message:
        response = requests.post(
            webhook_url, data=json.dumps(message),
            headers={'Content-Type': 'application/json'})

        if response.status_code != 200:
            raise ValueError(
                f"Request to slack returned an error {response.status_code}. "
                f"The response is:\n{response.text}")


def main(event, context):
    """
    Triggered from a message on a Cloud Pub/Sub topic.
    Args:
         event (dict): Event payload.
         context (google.cloud.functions.Context): Metadata for the event.
    """
    spam_num = int(os.environ.get('spam_limit_number'))
    spam_time = int(os.environ.get('spam_limit_mintes'))

    if 'data' in event:
        now = int(datetime.datetime.now().timestamp())
        global SPAMS
        SPAMS = [rtime for rtime in SPAMS if now - rtime < spam_time * 60]
        if len(SPAMS) <= spam_num:
            pubsub_message = \
                base64.b64decode(event['data']).decode('utf-8')
            report_slack(pubsub_message)
            SPAMS.append(now)
