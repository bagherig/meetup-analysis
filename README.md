# Meetup Analysis

A serverless data-collection pipeline on Google Cloud that streamed live `meetup.com` activity (events, venues, comments, photos, RSVPs) and enriched it with member and group profiles, as the data foundation for studying member and group interests.

![Python](https://img.shields.io/badge/Python-3.7-blue) ![Google Cloud](https://img.shields.io/badge/Google%20Cloud-Functions%20%7C%20GCS%20%7C%20Firestore%20%7C%20Pub%2FSub-4285F4)

**Highlights**

- Long-running stream consumer that batches records and fans them out to HTTP-triggered Cloud Functions.
- Raw stream data in Cloud Storage, member and group profiles in Firestore, BigQuery schemas for analysis.
- Production-style operations: structured logging with severities, truncated exponential backoff on every API call, log exports, a Pub/Sub alert path to Slack with spam limiting, and a 6-hour heartbeat to catch silent failures.

> Built in 2019 against Meetup's v2 REST and streaming APIs, which Meetup has since replaced. The code is kept as a reference implementation of the pipeline design.

## Architecture

<img src="https://www.lucidchart.com/publicSegments/view/555cb8c6-c02a-4f9d-a767-c9834a4bb38d/image.jpeg" width="500" alt="Data collection flowchart"/>

1. `scripts/trigger_gcf.py` connects to each Meetup stream ([open events](http://stream.meetup.com/2/open_events), [open venues](http://stream.meetup.com/2/open_venues?trickle), [event comments](http://stream.meetup.com/2/event_comments), [photos](http://stream.meetup.com/2/photos), [RSVPs](http://stream.meetup.com/2/rsvps)).
2. Each record is queued and sent in batches to the `save_stream_data` Cloud Function, which writes it to a Cloud Storage bucket.
3. When a record references a member or group, the script calls `save_member_data` or `save_group_data`, which fetch the profile from `api.meetup.com` and store it in Firestore.
4. Errors from the script and the functions flow through Cloud Logging to Pub/Sub, where `report_slack` posts them to a Slack channel.

## Cloud Functions

| Function | Trigger | What it does |
|---|---|---|
| `save_stream_data` | HTTP | Receives a batch of stream records plus a GCS `bucket` and a `label`. Writes each record to `{label}/{data_id}_{unix_epoch_time}.json`. |
| `save_member_data` | HTTP | Receives a `member_id`, a Meetup API key, and a Firestore `collection`. Fetches the [member profile](https://api.meetup.com/2/members/) and stores it as document `m{member_id}`. |
| `save_group_data` | HTTP | Receives a `group_id`, a Meetup API key, and a Firestore `collection`. Fetches the [group profile](https://api.meetup.com/2/groups) and stores it as document `m{group_id}`. |
| `report_slack` | Pub/Sub | Decodes an error log entry, formats it as a Slack message, and posts it to the webhook in `SLACK_WEBHOOK_URL`. Rate-limited by `spam_limit_number` per `spam_limit_mintes` minutes. |

## Monitoring and error handling

1. Every error and exception is written to [Cloud Logging](https://cloud.google.com/logging/) with a [severity](https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry#logseverity).
2. Every API call is retried with [truncated exponential backoff](https://cloud.google.com/storage/docs/exponential-backoff).
3. A log export stores everything at `ERROR` or above in a Cloud Storage bucket:
   ```
   resource.type="cloud_function" OR resource.type="global"
   severity >= ERROR
   ```
4. A second log export sends the same entries, plus a heartbeat the script logs every 6 hours, to Pub/Sub, which triggers `report_slack`. A missing heartbeat means the script stopped without logging an error.
   ```
   resource.type="cloud_function" OR resource.type="global"
   severity >= ERROR OR logName="projects/meetup-analysis/logs/Script-Monitor"
   ```

## Repository layout

```
bq_table_schema/   BigQuery schemas for each stream (events, venues, comments, photos, RSVPs)
scripts/
  trigger_gcf.py               stream consumer and orchestrator
  save_stream_data-(gcf).py    Cloud Function: stream records to GCS
  save_member_data-(gcf).py    Cloud Function: member profiles to Firestore
  save_group_data-(gcf).py     Cloud Function: group profiles to Firestore
  report_slack-(gcf).py        Cloud Function: error alerts to Slack
  setup_google_cloud_vm.sh     VM bootstrap (tmux, Anaconda)
requirements.txt
```

## Running it

1. Deploy the four Cloud Functions from `scripts/`, create the GCS bucket and Firestore collections, and set `SLACK_WEBHOOK_URL`, `spam_limit_number`, and `spam_limit_mintes` on `report_slack`.
2. Create `config.json` in the project root (it is gitignored):
   ```json
   {
     "stream_gcf": "<URL of save_stream_data>",
     "stream_gcs_bucket": "<GCS bucket for stream data>",
     "member_gcf": "<URL of save_member_data>",
     "member_fs_collection": "<Firestore collection for members>",
     "group_gcf": "<URL of save_group_data>",
     "group_fs_collection": "<Firestore collection for groups>",
     "meetup_api_key": "<Meetup API key>"
   }
   ```
3. On a [Compute Engine](https://cloud.google.com/compute/) VM, clone the repo, then from `scripts/` run `chmod 755 setup_google_cloud_vm.sh && ./setup_google_cloud_vm.sh`. It installs tmux and Anaconda and creates a tmux session named `meetup`.
4. `tmux attach -t meetup`, then `pip install -r requirements.txt` and `python trigger_gcf.py`. Detach with `Ctrl-b d` before closing SSH.

## Tech stack

Python, Google Cloud Functions, Cloud Storage, Firestore, Pub/Sub, Cloud Logging, BigQuery, Compute Engine, Slack webhooks.

## Author

[Moeen Bagheri](https://moeenbagheri.com)
