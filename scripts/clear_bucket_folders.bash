#!/bin/bash

gsutil -m rm -r gs://meetup_data/rsvp
gsutil -m rm -r gs://meetup_data/photos
gsutil -m rm -r gs://meetup_data/open_venues
gsutil -m rm -r gs://meetup_data/open_events
gsutil -m rm -r gs://meetup_data/event_comments