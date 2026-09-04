"""What a tool says about itself to a machine: JSON-LD, /llms.txt, robots.txt.

Every tool published the same three things and built them the same way, from a
private `_TOOL` dict holding its name, URL, tagline, blurb, audience, duration
and the numbered steps of a session — roughly 560 lines across the eight, plus
nine robots handlers written out by hand.

Two of those seven fields, `name` and `url`, were never presentation: they are
identity, and they live in `phronon_common.registry`. The other five are
`ToolPresentation`. These builders take both and are otherwise PURE — they read
no request, no environment and no database, so a test can compare their output
with what a tool used to emit, byte for byte.

WHAT IS DELIBERATELY NOT SHARED
The robots policy is per tool, because the paths are: Drawbridge keeps its
participant flow out of the index step by step, Layoff has an `/admin` area
where the others have `/backoffice`. `robots_txt()` takes the prefixes as
arguments and only guarantees the SHAPE — including that the private area is in
the list, which is how the missing `/backoffice` line in one tool was found.

No pytest, no FastAPI: this is imported by nine applications at start-up.
"""
from __future__ import annotations

import json

from phronon_common.registry import ToolIdentity, ToolPresentation

#: The publisher every tool names in its structured data.
PUBLISHER: dict = {"@type": "Organization", "name": "Phronon",
                   "url": "https://phronon.org"}

#: The sentence each tool appends to its blurb in /llms.txt. It was written out
#: eight times, once with a stray capital, which is the kind of difference that
#: means nothing and still has to be read twice by anyone comparing two files.
SUITE_NOTE = ("Part of Phronon, a suite of online tools for practical judgment. "
              "hosted in Germany, ad-free; participants need no account and "
              "install nothing.")


def as_script(obj) -> str:
    """JSON-LD ready to drop inside a <script> tag.

    `</` is escaped: without it, a blurb containing "</script>" would end the
    element early. Nothing in the fleet does today — but the escape is the
    reason it cannot start.
    """
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def _website(t: ToolIdentity, p: ToolPresentation) -> dict:
    return {"@type": "WebSite", "name": t.display_name, "url": t.public_url,
            "description": p.blurb, "publisher": PUBLISHER}


def _software(t: ToolIdentity, p: ToolPresentation) -> dict:
    return {"@type": "SoftwareApplication", "name": t.display_name,
            "url": t.public_url, "applicationCategory": "EducationalApplication",
            "operatingSystem": "Web browser", "description": p.blurb,
            "publisher": PUBLISHER}


def jsonld_site(t: ToolIdentity, p: ToolPresentation) -> str:
    """For every page: the site and who publishes it."""
    return as_script({"@context": "https://schema.org",
                      "@graph": [_website(t, p), PUBLISHER]})


def jsonld_about(t: ToolIdentity, p: ToolPresentation) -> str:
    """For /about: the site, the application, and who publishes it."""
    return as_script({"@context": "https://schema.org",
                      "@graph": [_website(t, p), _software(t, p), PUBLISHER]})


def llms_txt(t: ToolIdentity, p: ToolPresentation) -> str:
    """The machine-readable summary at /llms.txt."""
    lines = [f"# {t.display_name} — {p.tagline}", "",
             f"> {p.blurb} {SUITE_NOTE}", "",
             "## How it works", ""]
    lines += [f"{i}. {s}" for i, s in enumerate(p.how, 1)]
    lines += ["", f"Audience: {p.audience}. Typical time: {p.duration}.", "",
              "## Links", "",
              f"- [About]({t.public_url}/about): what this tool is and how a session works",
              f"- [Legal]({t.public_url}/legal): Impressum, privacy, cookies, terms",
              "- [Phronon suite](https://phronon.org/llms.txt): the other online tools", ""]
    return "\n".join(lines)


def robots_txt(t: ToolIdentity, rules) -> str:
    """The crawl policy. The RULES are the tool's; the shape is the fleet's.

    `rules` is an ordered sequence of ("Allow" | "Disallow", path). Ordered,
    and not two lists, because the fleet's files genuinely differ: six tools
    and the hub put `Allow: /` first and the exclusions after it, Drawbridge
    and Layoff list their exclusions first. The original robots standard is
    first-match-wins, so that order is not decoration — and reshuffling nine
    live files to make one function tidier would be changing what they say in
    order to share how they are built.

    What this DOES guarantee is the shape: one User-agent line, and a footer
    naming the tool's canonical domain. Whether the private area is excluded at
    all is asserted by `missing_private_prefixes` — which is how Layoff was
    found disallowing `/admin/` while its backoffice lived at `/backoffice/`.
    """
    lines = ["User-agent: *"]
    lines += [f"{verb}: {path}" for verb, path in rules]
    lines += ["", f"# AI/LLM summary: {t.public_url}/llms.txt", ""]
    return "\n".join(lines)


def missing_private_prefixes(rules, prefixes) -> list:
    """Which of `prefixes` no Disallow rule covers.

    A tool that forgets one hands its educator sign-in to the index. The page
    is behind a login either way, so nothing leaks — what goes wrong is that
    one property behaves unlike the other eight, and nobody notices because
    robots.txt is read by crawlers and not by people.
    """
    excluded = [p for verb, p in rules if verb == "Disallow"]
    return [want for want in prefixes
            if not any(want.startswith(e) or e.startswith(want) for e in excluded)]


def about_context(t: ToolIdentity, p: ToolPresentation) -> dict:
    """The `tool` mapping about.html reads.

    Still a mapping rather than the dataclasses, so the templates did not have
    to change in the same step that the applications did.
    """
    return {"name": t.display_name, "url": t.public_url, "tagline": p.tagline,
            "blurb": p.blurb, "audience": p.audience, "duration": p.duration,
            "how": list(p.how)}
