# !/usr/bin/python
# -*- coding: utf-8 -*-
"""Typing information for BCM."""
from typing import NewType
from google.cloud import logging

Logger = NewType('Logger', logging.logger)
