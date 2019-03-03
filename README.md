# Meetup Analysis

Meetup-Analysis is a project with the goal of predicting and finding patterns in `meetup.com` members' and groups' interests in certain products and activities. 

# Part 1 — Data Collection

The data used in this project included [_open events_](http://stream.meetup.com/2/open_events), [_open venues_](http://stream.meetup.com/2/open_venues?trickle), [_event comments_](http://stream.meetup.com/2/event_comments), [_photos_](http://stream.meetup.com/2/photos), and [_RSVP's_](http://stream.meetup.com/2/rsvps) obtained from `stream.meetup.com`, as well as Meetup [_member profiles_](https://api.meetup.com/2/members/) and [_group profiles_](https://api.meetup.com/2/groups) data from `api.meetup.com`. 

## Flow Chart

The following is an overall flowchart for collecting `meetup.com` data:

<img src="https://www.lucidchart.com/publicSegments/view/555cb8c6-c02a-4f9d-a767-c9834a4bb38d/image.jpeg" width="500"/>


## Cloud Functions
Each Process in the flowchart was assigned to a [Cloud Functions](https://cloud.google.com/functions/docs/). Three cloud functions were responsible for storing the data inside GCS and Firestore; Another GCF was responsible for reporting all errors that occured in other cloud functions and scripts to Slack.

### GCF: Save_stream_data
```python
"TODO: Explain what input it takes and what it does.
```
### GCF: Save_member_data
```python
"TODO: Explain what input it takes and what it does.
```
### GCF: Save_group_data
```python
"TODO: Explain what input it takes and what it does.
```

## Storage

Raw open events, open venues, event comments, photos, and RSVP's data were stored in [_Google Cloud Storage_](https://console.cloud.google.com/storage/browser/meetup_stream_data?project=meetup-analysis). The member profiles and group profiles data were stored in a [_Google Cloud Firestore_](https://console.cloud.google.com/firestore) database.

## Maintenance and Error Handling

Several parts were responsible for monitoring the status of the data collection script:

1. All API calls were reattempted on failure using [Truncated exponential backoff](https://cloud.google.com/storage/docs/exponential-backoff).
2. 
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
