import json
import requests
import os
import datetime
import threading
from requests.exceptions import ChunkedEncodingError, ConnectionError, ConnectTimeout

from google.cloud import storage
from google.cloud import logging


class HttpStream(object):

    def __init__(self, url, log_name="http_stream"):
        self.url = url
        self.storage_client = None
        self.logging_client = None

        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") is not None:
            self.storage_client = storage.Client()
            self.logging_client = logging.Client()
            self.logger = self.logging_client.logger(log_name)

    def __read_stream(self):
        while True:
            try:
                with requests.get(self.url, headers={"User-Agent": "Mozilla/5.0"}, stream=True) as r:
                    for line in r.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8')
                            yield json.loads(decoded_line)
            except ChunkedEncodingError:
                self.logger.log_text("Chunked Error at {}".format(str( datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))))
                continue

    def write_to_bucket(self, gcs_bucket, prefix=None):
        bucket = self.storage_client.get_bucket(gcs_bucket)

        if self.storage_client is not None:
            stream = self.__read_stream()

            for items in stream:
                current_time = datetime.datetime.now().timestamp()
                mtime = items["mtime"]

                if prefix is None:
                    file_name = "file-{}.json".format(str(current_time))
                else:
                    file_name = "{}/file-{}.json".format(prefix, str(current_time))

                try:
                    gcs_file = bucket.blob(file_name)
                    gcs_file.upload_from_string(json.dumps(items))
                except (ConnectionError, ConnectTimeout):
                    self.logger.log_text("Failed to save {} in {} at {}. ".format(file_name, gcs_bucket, datetime\
                                                                                  .datetime.now()\
                                                                                  .strftime('%Y-%m-%d %H:%M:%S')))
                    url = self.url.split("?")[0]
                    if url == "http://stream.meetup.com/2/open_venues":
                        self.url = url + "?trickle&since_mtime={}".format(str(mtime))
                    else:
                        self.url = url + "?since_mtime={}".format(str(mtime))
                    stream = self.__read_stream()
                    continue
                else:
                    self.logger.log_text("{} saved to {} at {}.".format(file_name, gcs_bucket, datetime.datetime.now()\
                                                                        .strftime('%Y-%m-%d %H:%M:%S')))


def write_stream(url, gcs_bucket, prefix):
    stream_data = HttpStream(url=url)
    stream_data.write_to_bucket(gcs_bucket=gcs_bucket
                                , prefix=prefix)


if __name__ == "__main__":
    t1 = threading.Thread(target=write_stream, args=("http://stream.meetup.com/2/event_comments","meetup_data",
                                                     "event_comments"))
    t2 = threading.Thread(target=write_stream, args=("http://stream.meetup.com/2/open_events","meetup_data",
                                                     "open_events"))
    t3 = threading.Thread(target=write_stream, args=("http://stream.meetup.com/2/open_venues?trickle","meetup_data",
                                                     "open_venues"))
    t4 = threading.Thread(target=write_stream, args=("http://stream.meetup.com/2/photos","meetup_data",
                                                     "photos"))
    t5 = threading.Thread(target=write_stream, args=("http://stream.meetup.com/2/rsvps","meetup_data",
                                                     "rsvp"))

    # starting thread 1
    t1.start()
    t2.start()
    t3.start()
    t4.start()
    t5.start()


