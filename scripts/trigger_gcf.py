import requests
import json
import os
import datetime
import threading
from requests.exceptions import ChunkedEncodingError, ConnectionError, ConnectTimeout
from google.cloud import logging
import urllib.parse as urlparse
from urllib.parse import urlencode


class HttpStream(object):
    def __init__(self, stream_url, http_url, prefix='meetup'):
        self.url = stream_url
        self.http = http_url
        self.logging_client = None
        self.logger = None
        self.prefix = prefix

        #self.__connect_gcs()

    def __connect_gcs(self):
        google_env_var = 'GOOGLE_APPLICATION_CREDENTIALS'
        credentials_path = os.path.join(os.getcwd(), 'meetup-analysis.json')

        print("Connecting to GCS...")
        if os.environ.get(google_env_var) is None:
            if os.path.exists(credentials_path):
                os.environ[google_env_var] = credentials_path
            else:
                raise FileNotFoundError(f'Could not find the environmental variable [{google_env_var}] or the \
                                          credentials file [{credentials_path}]')

        self.logging_client = logging.Client()
        self.logger = self.logging_client.logger('http_stream')

    def __read_stream(self):
        mtime = None
        while True:
            url = self.url
            if mtime:
                new_params = {'since_mtime': mtime}
                add_url_params(url, mtime)
            try:
                dt = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                with requests.get(url, stream=True) as r:
                    for line in r.iter_lines():
                        if line:
                            json_data = json.loads(line.decode('utf-8'))
                            mtime = json_data['mtime']
                            yield json_data
            except Exception as e:
                self.logger.log_text(f"{dt}: Error while reading stream. {str(e)}")
                continue

    def trigger_http_function(self):
        #if self.logging_client is None or self.logger is None:
            #self.__connect_gcs()

        stream = self.__read_stream()

        for item in stream:
            # print(item)
            params = {"label": self.prefix,
                      "bucket_name": "meetup_stream_data"}
            http_url = add_url_params(self.http, params)
            response = requests.post(http_url, json=item)

            print(f'HTTP triggered: label={self.prefix} - {response.text}')


def add_url_params(url: str, params: dict):
    url_parts = urlparse.urlparse(url)
    query = dict(urlparse.parse_qsl(url_parts.query))
    query.update(params)
    url_parts = url_parts._replace(query=urlencode(query))
    new_url = urlparse.urlunparse(url_parts)

    return new_url


def write_stream(stream_url, http_url, prefix):
    meetup_stream = HttpStream(stream_url=stream_url,
                                 http_url=http_url,
                                 prefix=prefix)
    meetup_stream.trigger_http_function()


def save_data(stream_urls, http_url):
    for url in stream_urls:
        prefix = url.split('/')[-1].split('?')[0]
        threading.Thread(target=write_stream,
                         args=(url, http_url, prefix)).start()


if __name__ == "__main__":
    HTTP_URL = 'https://us-central1-meetup-analysis.cloudfunctions.net/save_data'
    URLS = ["http://stream.meetup.com/2/event_comments",
            "http://stream.meetup.com/2/open_events",
            "http://stream.meetup.com/2/open_venues?trickle",
            "http://stream.meetup.com/2/photos",
            "http://stream.meetup.com/2/rsvps"]
    save_data(stream_urls=URLS, http_url=HTTP_URL)
