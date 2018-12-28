#!/bin/bash


bq --location=US mk -d meetup_stream_data

bq mkdef --noautodetect --source_format=NEWLINE_DELIMITED_JSON "gs://meetup_data/rsvp/*.json" rsvp.json > rsvp_tdf.json
bq mkdef --noautodetect --source_format=NEWLINE_DELIMITED_JSON "gs://meetup_data/photos/*.json" photos.json > photos_tdf.json
bq mkdef --noautodetect --source_format=NEWLINE_DELIMITED_JSON "gs://meetup_data/open_venues/*.json" open_venues.json > open_venues_tdf.json
bq mkdef --noautodetect --source_format=NEWLINE_DELIMITED_JSON "gs://meetup_data/open_events/*.json" open_events.json > open_events_tdf.json
bq mkdef --noautodetect --source_format=NEWLINE_DELIMITED_JSON "gs://meetup_data/event_comments/*.json" event_comments.json > event_comments_tdf.json

jq '.+{ignoreUnknownValues:true}' rsvp_tdf.json > rsvp_tdf.json.tmp && cp rsvp_tdf.json.tmp rsvp_tdf.json
jq '.+{ignoreUnknownValues:true}' photos_tdf.json > photos_tdf.json.tmp && cp photos_tdf.json.tmp photos_tdf.json
jq '.+{ignoreUnknownValues:true}' open_venues_tdf.json > open_venues_tdf.json.tmp && cp open_venues_tdf.json.tmp open_venues_tdf.json
jq '.+{ignoreUnknownValues:true}' open_events_tdf.json > open_events_tdf.json.tmp && cp open_events_tdf.json.tmp open_events_tdf.json
jq '.+{ignoreUnknownValues:true}' event_comments_tdf.json > event_comments_tdf.json.tmp && cp event_comments_tdf.json.tmp event_comments_tdf.json

rm *json.tmp

bq mk --external_table_definition=rsvp_tdf.json meetup_stream_data.rsvp_stream_raw
bq mk --external_table_definition=photos_tdf.json meetup_stream_data.photos_stream_raw
bq mk --external_table_definition=open_venues_tdf.json meetup_stream_data.open_venues_stream_raw
bq mk --external_table_definition=open_events_tdf.json meetup_stream_data.open_events_stream_raw
bq mk --external_table_definition=event_comments_tdf.json meetup_stream_data.comments_stream_raw





