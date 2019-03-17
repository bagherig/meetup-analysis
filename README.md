# Meetup Analysis

Meetup-Analysis is a project with the goal of predicting and finding patterns in `meetup.com` members' and groups' interests in certain products and activities. 

# Part 1 — Data Collection

The data used in this project included [_open events_](http://stream.meetup.com/2/open_events), [_open venues_](http://stream.meetup.com/2/open_venues?trickle), [_event comments_](http://stream.meetup.com/2/event_comments), [_photos_](http://stream.meetup.com/2/photos), and [_RSVP's_](http://stream.meetup.com/2/rsvps) obtained from `stream.meetup.com`, as well as Meetup [_member profiles_](https://api.meetup.com/2/members/) and [_group profiles_](https://api.meetup.com/2/groups) data from `api.meetup.com`. 

## Flow Chart

The following is an overall flowchart for collecting `meetup.com` data:

<img src="https://www.lucidchart.com/publicSegments/view/555cb8c6-c02a-4f9d-a767-c9834a4bb38d/image.jpeg" width="500"/>


## Storage
Raw open events, open venues, event comments, photos, and RSVP's data were stored in [_Google Cloud Storage_](https://console.cloud.google.com/storage/browser/meetup_stream_data?project=meetup-analysis). The member profiles and group profiles data were stored in a [_Google Cloud Firestore_](https://console.cloud.google.com/firestore) database.

## Cloud Functions
Processes in the flowchart were assigned to [Cloud Functions](https://cloud.google.com/functions/docs/). Three cloud functions were responsible for storing the data inside GCS or Firestore; Another GCF was responsible for reporting all errors that occured in other cloud functions and scripts to Slack.

### GCF: save_stream_data
* **Trigger:** HTTP
* Responsible for storing data obtained from [_open events_](http://stream.meetup.com/2/open_events), [_open venues_](http://stream.meetup.com/2/open_venues?trickle), [_event comments_](http://stream.meetup.com/2/event_comments), [_photos_](http://stream.meetup.com/2/photos), and [_RSVP's_](http://stream.meetup.com/2/rsvps) meetup streams, inside a GCS bucket.
* Recieves the `data` as a request JSON, as well as the name of a GCS `bucket` and a `label` (for describing what the data represents) as request arguments. 
* Stores the data in a file named `{data_id}_{unix_epoch_time}.json` in a folder named `label`. The cloud function is responsible for parsing `data_id` from the data it recieves.

### GCF: save_member_data
* **Trigger:** HTTP
* Responsible for storing a meetup member's data obtained from [_members_](https://api.meetup.com/2/members/) meetup api endpoint, inside Firestore.
* Recieves a meetup `member_id`, a meetup `api_key`, and the name of a Firestore `collection` as request arguments.
* Calls [_members_](https://api.meetup.com/2/members/) API endpoint using `member_id` and `api_key`. Stores the data in a Firestore document named `m{member_id}` in a collection named `{collection}`.

### GCF: save_group_data
* **Trigger:** HTTP
* Responsible for storing a meetup group's data obtained from [_groups_](https://api.meetup.com/2/groups) meetup api endpoint, inside Firestore.
* Recieves a meetup `group_id`, a meetup `api_key`, and the name of a Firestore `collection` as request arguments.
* Calls [_groups_](https://api.meetup.com/2/groups) API endpoint using `group_id` and `api_key`. Stores the data in a Firestore document named `m{group_id}` in a collection named `{collection}`.

### GCF: report_slack
* **Trigger:** Pub/Sub
* Responsible for storing a meetup group's data obtained from [_groups_](https://api.meetup.com/2/groups) meetup api endpoint, inside Firestore.  
* Recieves a meetup `group_id`, a meetup `api_key`, and the name of a Firestore `collection` as request arguments.
* Calls [_groups_](https://api.meetup.com/2/groups) API endpoint using `group_id` and `api_key`. Stores the data in a Firestore document named `m{group_id}` in a collection named `{collection}`.


## Maintenance and Error Handling

Several parts were responsible for monitoring the status of the data collection script:

1. All errors and exceptions were logged to `Stackdrive Logging`. Each log was assigned a [severity](https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry#logseverity), which represents the seriousness of the error. The list of
1. All API calls were reattempted on failure using [Truncated exponential backoff](https://cloud.google.com/storage/docs/exponential-backoff).
2. Errors and exceptions with a severity greater than **`ERROR`** were stored in a GCS bucket, using a `log export`.
```bash
TODO
```

## Usage

```python
"TODO: Explain how to set up VM and that cloud functions are necessary."
"TODO: Explain what trigger_gcf.py inputs to the GCF's (i.e. what parameters should the GCf's take)"
"TODO: Explain that a config.json file is necessary."
```

# Contributing
```bash
TODO
```
