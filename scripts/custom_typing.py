# !/usr/bin/python
# -*- coding: utf-8 -*-
"""Typing information for BCM."""
from typing import List, Dict, Union, NewType
from google.cloud import logging

Logger = NewType('Logger', logging.logger)

