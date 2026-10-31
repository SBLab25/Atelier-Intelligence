"""
Safe deterministic reports (Spec 10).

parse_input(dict) -> ReportInput   validated, cleaned and limited input (raises ReportInputError)
render(ReportInput) -> str         self-contained HTML, same input -> same bytes
report_filename(ReportInput)       cji_report_{slug}_{run id or input hash}.html
write_report(html, dir, name)      atomic write inside the reports directory (raises ReportOutputError)
"""
from .model import ReportInput, ReportInputError, parse_input
from .output import (
    MAX_REPORT_BYTES,
    ReportOutputError,
    ReportPathError,
    ReportTooLarge,
    ReportWriteError,
    report_filename,
    write_report,
)
from .render import CSP, RENDERER, SCHEMA, render

__all__ = [
    "CSP",
    "MAX_REPORT_BYTES",
    "RENDERER",
    "SCHEMA",
    "ReportInput",
    "ReportInputError",
    "ReportOutputError",
    "ReportPathError",
    "ReportTooLarge",
    "ReportWriteError",
    "parse_input",
    "render",
    "report_filename",
    "write_report",
]
