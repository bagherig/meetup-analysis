# Meetup Analysis
Meetup-Analysis is a project with the goal of predicting and finding patterns in `meetup.com` members' and groups' interests in certain products and activities. 

# Part 1 — Data Collection
The data used in this project included [_open events_](http://stream.meetup.com/2/open_events), [_open venues_](http://stream.meetup.com/2/open_venues?trickle), [_event comments_](http://stream.meetup.com/2/event_comments), [_photos_](http://stream.meetup.com/2/photos), and [_RSVP's_](http://stream.meetup.com/2/rsvps) obtained from `stream.meetup.com`, as well as Meetup [_member profiles_](https://api.meetup.com/2/members/) and [_group profiles_](https://api.meetup.com/2/groups) data from `api.meetup.com`. 

## Flow Chart
The following is an overall flowchart for collecting `meetup.com` data:

<img src="https://www.lucidchart.com/publicSegments/view/555cb8c6-c02a-4f9d-a767-c9834a4bb38d/image.jpeg" width="500"/>

## Storage
Raw open events, open venues, event comments, photos, and RSVP's data were stored in [_Google Cloud Storage_](https://console.cloud.google.com/storage/browser/meetup_stream_data?project=meetup-analysis). The member profiles and group profiles data were stored in a [_Google Cloud Firestore_](https://console.cloud.google.com/firestore) database.

## Main Script
The main script, `trigger_gcf.py`, is responsible for connecting to each `meetup.com` stream and triggering a Cloud Function to store the data inside a GCS bucket. Additionally, the script checks whether each piece of data contains members or groups, and retrieves the data for that member/group from `api.meetup.com`.

## Cloud Functions
Processes in the flowchart were assigned to [Cloud Functions](https://cloud.google.com/functions/docs/). Three cloud functions were responsible for storing the data inside GCS or Firestore; Another GCF was responsible for reporting all errors that occured in other cloud functions and scripts to Slack.

### GCF: save_stream_data
* **Trigger:**`HTTP`
* **Responsibility:** Stores data obtained from [_open events_](http://stream.meetup.com/2/open_events), [_open venues_](http://stream.meetup.com/2/open_venues?trickle), [_event comments_](http://stream.meetup.com/2/event_comments), [_photos_](http://stream.meetup.com/2/photos), and [_RSVP's_](http://stream.meetup.com/2/rsvps) meetup streams, inside a GCS bucket.
* **Parameters:** Recieves the `data` as a request JSON, as well as the name of a GCS `bucket` and a `label` (for describing what the data represents) as request arguments. 
* Stores the data in a file named `{data_id}_{unix_epoch_time}.json` in a folder named `label`. The cloud function is responsible for parsing `data_id` from the data it recieves.

### GCF: save_member_data
* **Trigger:** `HTTP`
* **Responsibility:** Stores a meetup member's data obtained from [_members_](https://api.meetup.com/2/members/) meetup api endpoint, inside Firestore.
* **Parameters:** Recieves a meetup `member_id`, a meetup `api_key`, and the name of a Firestore `collection` as request arguments.
* Calls [_members_](https://api.meetup.com/2/members/) API endpoint using `member_id` and `api_key`. Stores the data in a Firestore document named `m{member_id}` in a collection named `{collection}`.

### GCF: save_group_data
* **Trigger:** `HTTP`
* **Responsibility:** Stores a meetup group's data obtained from [_groups_](https://api.meetup.com/2/groups) meetup api endpoint, inside Firestore.
* **Parameters:** Recieves a meetup `group_id`, a meetup `api_key`, and the name of a Firestore `collection` as request arguments.
* Calls [_groups_](https://api.meetup.com/2/groups) API endpoint using `group_id` and `api_key`. Stores the data in a Firestore document named `m{group_id}` in a collection named `{collection}`.

### GCF: report_slack
* **Trigger:** `Pub/Sub`
* **Responsibility:** Stores a meetup group's data obtained from [_groups_](https://api.meetup.com/2/groups) meetup api endpoint, inside Firestore.  
* **Parameters:** Recieves a meetup `group_id`, a meetup `api_key`, and the name of a Firestore `collection` as request arguments.
* Calls [_groups_](https://api.meetup.com/2/groups) API endpoint using `group_id` and `api_key`. Stores the data in a Firestore document named `m{group_id}` in a collection named `{collection}`.

## Maintenance and Error Handling
Several parts were responsible for monitoring the status of the data collection script:

1. All errors and exceptions were logged to `Stackdrive Logging`. Each log was assigned a [severity](https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry#logseverity), which represents the seriousness of the error.
2. All API calls were reattempted on failure using [Truncated exponential backoff](https://cloud.google.com/storage/docs/exponential-backoff).
3. A Stackdriver `log export` was responsible for storing all errors and exceptions with a severity greater than **`ERROR`** in a GCS bucket. Below is the code used for the `log export`:
```python
resource.type="cloud_function" OR resource.type="global"
severity >= ERROR
```
4. A Stackdriver `log export` was responsible for sending all errors and exceptions with a severity greater than **`ERROR`** to a `Pub/Sub`, which in turn notified Slack by triggering the cloud function, `report_slack`. Additionally, the `Pub/Sub` was notified of a logger with the `logName` `projects/meetup-analysis/logs/Script-Monitor`, which sent a log every 6 hours, to ensure that the script was running (In case the script stopped working for an unknown reason without logging the error). Below is the code used for the `log export`:
```python
resource.type="cloud_function" OR resource.type="global"
severity >= ERROR OR logName="projects/meetup-analysis/logs/Script-Monitor"```
```

## Usage
First, set up the cloud functions, GCS buckets, and Firestore databases. The code for the cloud functions can be found under the folder, `scripts`. Next, run `trigger_gcf.py` script in order to start storing data from `meetup.com` streams. The script requires a `config.json` file. The required fields for this file are explained below:
```
TODO: config requirements
```
### Setting up Google Compute Engine
It is recommended to run this script on a Google [Compute Engine](https://cloud.google.com/compute/). These virtual machines provide consistent perfomance, along with other benefits. The steps for setting up the Google VM are described below:
1. Create a [VM instance](https://console.cloud.google.com/projectselector/compute/instances?supportedpurview=project).
2. SSH into the VM instance.
3. Clone the repository and change to the `scripts` directory.
4. Run the following command, which gives `setup_google_cloud_vm.sh` shell script permission to run.
```bash
chmod 755 setup_google_cloud_vm.sh
```
5. Run `setup_google_cloud_vm.sh` using the command:
```bash
./setup_google_cloud_vm.sh
```
The shell script, `setup_google_cloud_vm.sh`, has a list of commands to set up the VM. These commands include installing `tmux` and `Anaconda`. The shell script also creates a new tmux session named `meetup`.

### Running the Python script
Once the VM is set up, attach to the newly created tmux session named `meetup`, by executing the command:
```bash
tmux attach -t meetup
```
Then, simply excute the script, `trigger_gcf.py`, using the command: 
```bash
python trigger_gcf.py
```
Remember to detach from the tmux session before closing your SSH connection. To detach from a tmux session, simply press ```ctrl-b``` followed by the letter ```d```.

# Part 2 — Data Preprocessing
```python
TODO
```
# Contributing
```bash
Moeen Bagheri

```
