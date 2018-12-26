import json
import requests
import os
import datetime

from google.cloud import storage
from google.cloud import logging


class FailedToSaveError(Exception):
    """Filed to save HTTP stream file to GCS"""
    pass


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
        r = requests.get(self.url, stream=True)
        for line in r.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                yield json.loads(decoded_line)

    def write_to_bucket(self, gcs_bucket, prefix=None):
        bucket = self.storage_client.get_bucket(gcs_bucket)

        if self.storage_client is not None:
            stream = self.__read_stream()

            for items in stream:
                current_time = datetime.datetime.now().timestamp()

                if prefix is None:
                    file_name = "file-{}.json".format(str(current_time))
                else:
                    file_name = "{}/file-{}.json".format(prefix, str(current_time))

                try:
                    gcs_file = bucket.blob(file_name)
                    gcs_file.upload_from_string(json.dumps(items))
                except FailedToSaveError:
                    self.logger.log_text("Failed to save {} in {} at {}. ".format(file_name, gcs_bucket, datetime\
                                                                                  .datetime.now()\
                                                                                  .strftime('%Y-%m-%d %H:%M:%S')))
                    pass
                else:
                    self.logger.log_text("{} saved to {} at {}.".format(file_name, gcs_bucket, datetime.datetime.now()\
                                                                        .strftime('%Y-%m-%d %H:%M:%S')))


if __name__ == "__main__":
    with open('config.json') as f:
        conf = json.load(f)

    meetup_data = HttpStream(url=conf["url"])
    meetup_data.write_to_bucket(gcs_bucket=conf["gcs_bucket"], prefix=conf["prefix"])

