"""Creating Todoist tasks for the handful of items worth acting on.

The email is for reading; these are for committing to. Only items with concrete
`actionable_steps` and a verdict that survived the check become tasks — turning
every digest entry into a task would rebuild the same unread pile the tool exists
to clear.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from saveddigest.deliver.rank import Digest, DigestEntry
from saveddigest.store import Verdict

log = logging.getLogger(__name__)

_API_ROOT = "https://api.todoist.com/rest/v2"
_TIMEOUT = 30

#: Verdicts whose items may become tasks. `superseded` is excluded on purpose:
#: the useful action there is "read the newer thing", which the digest already
#: links, not "watch the outdated one".
_ACTIONABLE_VERDICTS = frozenset(
    {Verdict.STILL_VALID.value, Verdict.NOT_APPLICABLE.value, Verdict.PARTLY_OUTDATED.value}
)

#: Cap per run. More than a few tasks a week is how a task list stops being read.
DEFAULT_MAX_TASKS = 3


@dataclass(frozen=True)
class PlannedTask:
    """A task about to be created. Built purely so it can be asserted on."""

    content: str
    description: str
    url: str


def select_actionable(digest: Digest, *, limit: int = DEFAULT_MAX_TASKS) -> list[DigestEntry]:
    """The entries worth a task, best first.

    Requires all three: real actionable steps, a verdict that held up, and
    substantive content. Anything thinner stays in the email.
    """
    candidates = [
        entry
        for entry in digest.entries
        if entry.summary.get("actionable_steps")
        and entry.verdict.get("verdict") in _ACTIONABLE_VERDICTS
        and entry.summary.get("content_quality") == "substantive"
    ]
    return candidates[:limit]


def plan_task(entry: DigestEntry) -> PlannedTask:
    """Render one entry as a task. Title is the action, not the video."""
    item, summary = entry.item, entry.summary
    steps = summary.get("actionable_steps") or []
    first = steps[0] if steps else (summary.get("tldr") or item.title or item.url)

    lines: list[str] = []
    if item.title:
        lines.append(f"From: {item.title}")
    lines.append(item.url)
    if summary.get("tldr"):
        lines.append("")
        lines.append(summary["tldr"])
    if len(steps) > 1:
        lines.append("")
        lines.extend(f"- {step}" for step in steps[1:6])

    verdict = entry.verdict
    if verdict.get("verdict") == Verdict.PARTLY_OUTDATED.value and verdict.get("what_changed"):
        lines.append("")
        lines.append(f"Caveat: {verdict['what_changed']}")
    if entry.unchecked:
        lines.append("")
        lines.append("Note: this was not fact-checked against the web.")

    return PlannedTask(
        content=first[:500],
        description="\n".join(lines)[:16_000],
        url=item.url,
    )


class TodoistTaskWriter:
    """Creates the tasks. Network-facing; failures are logged, never fatal."""

    def __init__(self, token: str, *, session: requests.Session | None = None):
        if not token:
            raise ValueError("a Todoist API token is required")
        self._token = token
        self._session = session or requests.Session()

    def create(self, task: PlannedTask, *, project_id: str | None = None) -> str | None:
        payload: dict[str, object] = {
            "content": task.content,
            "description": task.description,
            "due_string": "next week",
        }
        if project_id:
            payload["project_id"] = project_id
        try:
            response = self._session.post(
                f"{_API_ROOT}/tasks",
                headers={"Authorization": f"Bearer {self._token}"},
                json=payload,
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            # The digest email has already gone out; a task failure must not make
            # the run look failed.
            log.warning("could not create Todoist task %r: %s", task.content, exc)
            return None
        return str(response.json().get("id", ""))

    def create_all(
        self, tasks: list[PlannedTask], *, project_id: str | None = None
    ) -> list[str]:
        created: list[str] = []
        for task in tasks:
            task_id = self.create(task, project_id=project_id)
            if task_id:
                created.append(task_id)
        return created
