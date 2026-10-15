"""Synthetic plants with known answers (public benchmark datasets, ADR-0001).

A YAML config describes a plant; a SimPy flow-line simulation produces its history in the
standard layout plus a generator log of the true lost time per machine and cause.
Requires the ``synthetic`` extra (simpy, pyyaml).
"""
