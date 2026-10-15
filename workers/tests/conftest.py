"""Use Dramatiq's in-memory broker for every worker test."""

import os

os.environ["CIP_BROKER"] = "stub"
