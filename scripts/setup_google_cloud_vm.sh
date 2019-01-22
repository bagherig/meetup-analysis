#!/bin/bash
# SETUP THE REPOSITORY
# sudo apt-get -y install git
# git clone https://github.com/bagherig/meetup-analysis.git
# cd meetup-analysis/scripts

# THE FOLLOWING COMMAND WILL CHANGE PERMISSION OF THE SHELL SCRIPT SO IT CAN BE RUN.
# chmod 755 setup_google_cloud_vm.sh
# THE FOLLOWING COMMAND WILL RUN THE SCRIPT.
# ./setup_google_cloud_vm.sh
sudo apt-get -y update
sudo apt-get -y upgrade

sudo apt-get -y install tmux

# SETUP ANACONDA
sudo apt-get -y install bzip2
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