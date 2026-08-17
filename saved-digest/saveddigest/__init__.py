"""saved-digest — resurface and fact-check the content you saved and forgot.

Pipeline, five idempotent stages over one SQLite table:

    capture  -> enrich -> summarise (Pass A) -> verify (Pass B) -> deliver

Each item carries a `status` naming the furthest stage it has completed, so any
stage can crash halfway and be re-run without duplicating work or re-billing the
Claude API.
"""

__version__ = "0.1.0"
