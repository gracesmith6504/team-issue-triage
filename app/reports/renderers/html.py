from __future__ import annotations

from dataclasses import asdict
from enum import Enum

from app.reports.models import BirdsEyeReport


def _convert_value(obj):
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _convert_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_convert_value(i) for i in obj]
    return obj


def _report_to_dict(report: BirdsEyeReport) -> dict:
    raw = asdict(report)
    return _convert_value(raw)
