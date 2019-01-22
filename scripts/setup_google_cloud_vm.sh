#!/bin/bash
# THE FOLLOWING COMMAND WILL CHANGE PERMISSION OF THIS FILE SO IT CAN BE RAN.
# chmod 755 setup_google_cloud_vm.sh

# SETUP THE REPOSITORY
# sudo apt-get install git
# git clone https://github.com/bagherig/meetup-analysis.git

sudo apt-get update
sudo apt-get upgrade

sudo apt-get install tmux

# SETUP ANACONDA
sudo apt-get install bzip2
cd /tmp
curl -O https://repo.continuum.io/archive/Anaconda3-2018.12-Linux-x86_64.sh
bash Anaconda3-2018.12-Linux-x86_64.sh

tmux new-session -s meetup # Create a new tmux session called meetup
# USE ctrl-b + d to detach from a session
# tmux attach -t meetup # Attach to meetup session
# tmux kill-session -t meetup # kills meetup session.
pip install -r requirements.txt
pip install -e code/ccxt/python

# RUN YOUR CODE!