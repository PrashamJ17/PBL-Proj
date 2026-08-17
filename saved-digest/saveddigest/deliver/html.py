"""Rendering the digest as HTML (and a plain-text alternative).

Email-client constraints drive the style choices: everything is inline-styled
because Gmail and Outlook strip or partially honour `<style>` blocks, and the
layout is a single column because float and flex support is unreliable. No
external CSS, fonts or images, so the email renders identically offline.

Every string that reaches the page goes through `escape`. Titles come from
YouTube and summaries come from a language model; neither is trusted markup.
"""

from __future__ import annotations

from html import escape

from saveddigest.deliver.rank import Digest, DigestEntry, summarise_counts
from saveddigest.store import Verdict

# --- palette -------------------------------------------------------------
_INK = "#1a1a1a"
_MUTED = "#6b7280"
_RULE = "#e5e7eb"
_LINK = "#1d4ed8"
_CARD = "#ffffff"
_PAGE = "#f6f7f9"

#: Verdict badge: label, text colour, background. The wording is deliberately
#: plain — "not checked" rather than a euphemism.
_BADGES: dict[str, tuple[str, str, str]] = {
    Verdict.STILL_VALID.value: ("Still valid", "#065f46", "#d1fae5"),
    Verdict.PARTLY_OUTDATED.value: ("Partly outdated", "#92400e", "#fef3c7"),
    Verdict.SUPERSEDED.value: ("Superseded", "#9a3412", "#ffedd5"),
    Verdict.EXPIRED.value: ("Expired", "#991b1b", "#fee2e2"),
    Verdict.UNVERIFIED.value: ("Not checked", "#3730a3", "#e0e7ff"),
    Verdict.NOT_APPLICABLE.value: ("Evergreen", "#1f2937", "#f3f4f6"),
}

_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
)


def _age_phrase(days: int) -> str:
    """Human phrasing for how long something has been waiting."""
    if days <= 0:
        return "saved today"
    if days == 1:
        return "saved yesterday"
    if days < 30:
        return f"saved {days} days ago"
    if days < 365:
        months = max(1, round(days / 30))
        return f"saved {months} month{'s' if months != 1 else ''} ago"
    years = days / 365
    if years < 2:
        return "saved over a year ago"
    return f"saved over {int(years)} years ago"


def _badge(verdict_value: str | None) -> str:
    label, fg, bg = _BADGES.get(
        verdict_value or Verdict.UNVERIFIED.value, _BADGES[Verdict.UNVERIFIED.value]
    )
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
        f'font-size:11px;font-weight:600;letter-spacing:.02em;color:{fg};'
        f'background:{bg};">{escape(label)}</span>'
    )


def _bullets(values: list[str], *, limit: int = 8) -> str:
    if not values:
        return ""
    shown = values[:limit]
    items = "".join(
        f'<li style="margin:0 0 4px 0;">{escape(v)}</li>' for v in shown
    )
    extra = ""
    if len(values) > limit:
        extra = (
            f'<li style="margin:0;color:{_MUTED};list-style:none;">'
            f"+{len(values) - limit} more</li>"
        )
    return (
        f'<ul style="margin:6px 0 0 0;padding-left:20px;font-size:14px;'
        f'line-height:1.55;color:{_INK};">{items}{extra}</ul>'
    )


def _paragraphs(text: str) -> str:
    """Render the detailed summary, preserving its paragraph breaks."""
    chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
    if not chunks:
        return ""
    return "".join(
        f'<p style="margin:0 0 10px 0;font-size:14px;line-height:1.6;color:{_INK};">'
        f"{escape(chunk)}</p>"
        for chunk in chunks
    )


def _section_label(text: str) -> str:
    return (
        f'<div style="margin:14px 0 0 0;font-size:11px;font-weight:700;'
        f'letter-spacing:.06em;text-transform:uppercase;color:{_MUTED};">'
        f"{escape(text)}</div>"
    )


def _sources_block(sources: list[dict[str, str]], *, limit: int = 5) -> str:
    """Citations, shown so a verdict can be checked instead of trusted."""
    if not sources:
        return ""
    links = "".join(
        f'<li style="margin:0 0 3px 0;">'
        f'<a href="{escape(s["url"])}" style="color:{_LINK};text-decoration:none;">'
        f'{escape(s["title"])}</a></li>'
        for s in sources[:limit]
    )
    return _section_label("Sources") + (
        f'<ul style="margin:6px 0 0 0;padding-left:20px;font-size:12px;'
        f'line-height:1.5;color:{_MUTED};">{links}</ul>'
    )


def _verdict_block(entry: DigestEntry) -> str:
    """What the web check concluded, or an explicit note that it did not run."""
    verdict = entry.verdict
    value = verdict.get("verdict")
    parts: list[str] = []

    if value == Verdict.UNVERIFIED.value:
        reason = verdict.get("unverified_reason") or "the check did not complete"
        parts.append(
            f'<p style="margin:8px 0 0 0;font-size:13px;line-height:1.5;'
            f'color:{_MUTED};"><em>Not fact-checked: {escape(reason)}. '
            f"Treat the summary above as unverified.</em></p>"
        )
        return "".join(parts)

    if value == Verdict.NOT_APPLICABLE.value:
        return ""

    what_changed = verdict.get("what_changed") or ""
    current_state = verdict.get("current_state") or ""
    superseded_by = verdict.get("superseded_by") or ""
    confidence = verdict.get("confidence") or ""

    if what_changed or current_state:
        parts.append(_section_label("What changed"))
        body = " ".join(p for p in (what_changed, current_state) if p)
        parts.append(
            f'<p style="margin:6px 0 0 0;font-size:13px;line-height:1.55;'
            f'color:{_INK};">{escape(body)}</p>'
        )

    if superseded_by:
        parts.append(
            f'<p style="margin:8px 0 0 0;font-size:13px;">'
            f'Current version: <a href="{escape(superseded_by)}" '
            f'style="color:{_LINK};text-decoration:none;">'
            f"{escape(superseded_by)}</a></p>"
        )

    checked = verdict.get("checked_claims") or []
    if checked:
        rows = "".join(
            f'<li style="margin:0 0 4px 0;">'
            f'<strong style="font-weight:600;">{escape(c.get("holds", "?"))}</strong> '
            f'&mdash; {escape(c.get("claim", ""))}'
            + (
                f' <span style="color:{_MUTED};">({escape(c["note"])})</span>'
                if c.get("note")
                else ""
            )
            + "</li>"
            for c in checked[:6]
        )
        parts.append(_section_label("Claims checked"))
        parts.append(
            f'<ul style="margin:6px 0 0 0;padding-left:20px;font-size:13px;'
            f'line-height:1.5;color:{_INK};">{rows}</ul>'
        )

    if confidence:
        parts.append(
            f'<p style="margin:8px 0 0 0;font-size:11px;color:{_MUTED};">'
            f"Confidence in this check: {escape(confidence)}</p>"
        )

    parts.append(_sources_block(verdict.get("sources") or []))
    return "".join(parts)


def _entry_card(entry: DigestEntry) -> str:
    item = entry.item
    summary = entry.summary
    title = item.title or summary.get("tldr") or item.url

    meta_bits = [_age_phrase(item.days_since_saved()), str(item.platform)]
    if item.author:
        meta_bits.append(item.author)
    quality = summary.get("content_quality")
    if quality in {"thin", "promotional"}:
        meta_bits.append(f"flagged {quality}")

    # Escape each part first, then join with the entity, so the separator is not
    # itself escaped. (Escaping the joined string would emit a literal
    # "&amp;middot;".)
    meta = " &middot; ".join(escape(bit) for bit in meta_bits)

    header = (
        f'<div style="margin:0 0 2px 0;">{_badge(entry.verdict.get("verdict"))}</div>'
        f'<h2 style="margin:6px 0 2px 0;font-size:17px;line-height:1.35;'
        f'font-weight:650;color:{_INK};">'
        f'<a href="{escape(item.url)}" style="color:{_INK};text-decoration:none;">'
        f"{escape(title)}</a></h2>"
        f'<div style="font-size:12px;color:{_MUTED};margin:0 0 10px 0;">'
        f"{meta}</div>"
    )

    body = ""
    tldr = summary.get("tldr")
    if tldr:
        body += (
            f'<p style="margin:0 0 10px 0;font-size:15px;line-height:1.5;'
            f'font-weight:600;color:{_INK};">{escape(tldr)}</p>'
        )

    detailed = summary.get("detailed_summary") or ""
    if detailed:
        body += _paragraphs(detailed)

    if summary.get("key_points"):
        body += _section_label("Key points") + _bullets(summary["key_points"])
    if summary.get("actionable_steps"):
        body += _section_label("What you could do") + _bullets(
            summary["actionable_steps"]
        )
    if summary.get("tools_mentioned"):
        body += (
            _section_label("Mentioned")
            + f'<p style="margin:6px 0 0 0;font-size:13px;color:{_INK};">'
            + escape(", ".join(summary["tools_mentioned"][:12]))
            + "</p>"
        )

    body += _verdict_block(entry)

    return (
        f'<div style="background:{_CARD};border:1px solid {_RULE};border-radius:10px;'
        f'padding:18px 20px;margin:0 0 14px 0;">{header}{body}</div>'
    )


def _footer_list(title: str, entries: list[DigestEntry], note: str) -> str:
    if not entries:
        return ""
    rows = "".join(
        f'<li style="margin:0 0 5px 0;">'
        f'<a href="{escape(e.item.url)}" style="color:{_MUTED};'
        f'text-decoration:underline;">'
        f"{escape(e.item.title or e.item.url)}</a>"
        + (f' <span style="color:{_MUTED};">&mdash; {escape(e.reason)}</span>' if e.reason else "")
        + "</li>"
        for e in entries
    )
    return (
        f'<div style="margin:0 0 16px 0;">'
        f'<div style="font-size:12px;font-weight:700;letter-spacing:.05em;'
        f'text-transform:uppercase;color:{_MUTED};margin:0 0 6px 0;">'
        f"{escape(title)} ({len(entries)})</div>"
        f'<div style="font-size:12px;color:{_MUTED};margin:0 0 6px 0;">{escape(note)}</div>'
        f'<ul style="margin:0;padding-left:20px;font-size:13px;line-height:1.5;">'
        f"{rows}</ul></div>"
    )


def render_html(digest: Digest) -> str:
    """The full digest as a single self-contained HTML document."""
    counts = summarise_counts(digest)

    if digest.is_empty:
        inner = (
            f'<p style="font-size:15px;color:{_INK};">Nothing to resurface this time. '
            f"Everything you have saved has already been through a digest.</p>"
        )
    else:
        intro_bits = [f"{counts['shown']} item{'s' if counts['shown'] != 1 else ''} below"]
        if counts["held_back"]:
            intro_bits.append(f"{counts['held_back']} waiting for next time")
        if counts["unchecked"]:
            intro_bits.append(f"{counts['unchecked']} could not be fact-checked")

        # Describe the actual ordering. It is not purely by age: a still-valid
        # save outranks a superseded one of the same vintage, and a promotional
        # roundup sinks regardless of how long it has sat there. Claiming
        # "oldest first" here would be untrue of the list underneath it.
        inner = (
            f'<p style="font-size:13px;color:{_MUTED};margin:0 0 18px 0;">'
            f"{escape(', '.join(intro_bits))}. Longest-waiting first, adjusted for "
            f"whether it is still worth your time.</p>"
        )
        inner += "".join(_entry_card(e) for e in digest.entries)
        inner += _footer_list(
            "No longer available",
            digest.gone,
            "These were deleted or made private since you saved them.",
        )
        inner += _footer_list(
            "Expired",
            digest.expired,
            "The deadline or event these referred to has passed.",
        )
        inner += _footer_list(
            "Nothing readable",
            digest.no_content,
            "No transcript or caption could be retrieved, so these were not summarised.",
        )

    generated = (
        f'<p style="font-size:11px;color:{_MUTED};margin:22px 0 0 0;">'
        f"Generated {escape(digest.generated_at)} by saved-digest. "
        f"Fact-check verdicts come from a language model with web search and are "
        f"shown with their sources &mdash; check anything you plan to act on.</p>"
        if digest.generated_at
        else ""
    )

    return (
        f'<div style="margin:0;padding:24px 12px;background:{_PAGE};'
        f'font-family:{_FONT};">'
        f'<div style="max-width:680px;margin:0 auto;">'
        f'<h1 style="margin:0 0 4px 0;font-size:20px;font-weight:700;color:{_INK};">'
        f"Things you saved and never went back to</h1>"
        f"{inner}{generated}"
        f"</div></div>"
    )


def render_text(digest: Digest) -> str:
    """Plain-text alternative, for the multipart email and for `--dry-run`."""
    lines: list[str] = ["THINGS YOU SAVED AND NEVER WENT BACK TO", ""]

    if digest.is_empty:
        lines.append("Nothing to resurface this time.")
        return "\n".join(lines)

    counts = summarise_counts(digest)
    lines.append(
        f"{counts['shown']} shown, {counts['held_back']} waiting, "
        f"{counts['gone']} gone, {counts['expired']} expired, "
        f"{counts['unchecked']} unchecked."
    )
    lines.append("Longest-waiting first, adjusted for whether it is still worth your time.")
    lines.append("")

    for n, entry in enumerate(digest.entries, start=1):
        item, summary = entry.item, entry.summary
        label = _BADGES.get(
            entry.verdict.get("verdict") or Verdict.UNVERIFIED.value,
            _BADGES[Verdict.UNVERIFIED.value],
        )[0]
        lines.append(f"{n}. [{label}] {item.title or item.url}")
        lines.append(f"   {_age_phrase(item.days_since_saved())} - {item.url}")
        if summary.get("tldr"):
            lines.append(f"   {summary['tldr']}")
        if summary.get("detailed_summary"):
            paragraphs = [p.strip() for p in summary["detailed_summary"].split("\n\n") if p.strip()]
            for para in paragraphs:
                lines.append("")
                lines.append(f"   {para}")
            if paragraphs:
                lines.append("")
        for point in (summary.get("key_points") or [])[:8]:
            lines.append(f"   - {point}")
        for step in (summary.get("actionable_steps") or [])[:8]:
            lines.append(f"   > {step}")

        verdict = entry.verdict
        if verdict.get("verdict") == Verdict.UNVERIFIED.value:
            reason = verdict.get("unverified_reason") or "check did not complete"
            lines.append(f"   ! NOT fact-checked: {reason}")
        else:
            if verdict.get("what_changed"):
                lines.append(f"   Changed: {verdict['what_changed']}")
            if verdict.get("superseded_by"):
                lines.append(f"   Current version: {verdict['superseded_by']}")
            for source in (verdict.get("sources") or [])[:5]:
                lines.append(f"   src: {source['url']}")
        lines.append("")

    for title, entries, note in (
        ("NO LONGER AVAILABLE", digest.gone, "deleted or made private"),
        ("EXPIRED", digest.expired, "deadline passed"),
        ("NOTHING READABLE", digest.no_content, "no transcript or caption"),
    ):
        if not entries:
            continue
        lines.append(f"{title} ({len(entries)}) - {note}")
        for entry in entries:
            suffix = f" - {entry.reason}" if entry.reason else ""
            lines.append(f"  - {entry.item.title or entry.item.url}{suffix}")
        lines.append("")

    if digest.generated_at:
        lines.append(f"Generated {digest.generated_at} by saved-digest.")
    return "\n".join(lines)
