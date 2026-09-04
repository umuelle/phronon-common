"""One place that says what a tool IS: the canonical fleet registry.

WHY THIS EXISTS
A tool is identified by at least six different strings, and code kept picking
whichever was nearest to hand:

  fleet key            `lsr`                    server-ops/fleet.conf, legal_conf
  workspace directory  `polarity-profiler`      the Mac, server-ops gates
  GitHub repository    `lsr-profiler`           CI checks out under THIS name
  systemd unit / path  `lsr-profiler`           /var/www/lsr-profiler
  entitlement key      `lsr_profiler`           the hub, PROVISION_SECRET_<KEY>
  display name         `Polarity Profiler`      notices, e-mail, page titles

On 4 September 2026 a fleet test derived a tool's identity from its checkout
directory and turned CI red on every repository, because GitHub checks
`ControversyGenerator` out as `controversy-generator`. The same week the hub
was found linking Polarity Profiler at its LEGACY domain in `app.py` while its
own `fleet_client.py` used the canonical one — the hub disagreeing with itself,
in two files, about one tool.

WHAT IS HERE, AND WHAT IS NOT
`ToolIdentity` holds the stable operational facts, owned centrally. It does NOT
own deployment mechanics: `fleet.conf` stays the map deploy.sh reads, and
`server-ops/tool_registry_check.py` compares the two so they cannot disagree in
silence.

`ToolPresentation` — the tagline, the description, who it is for, how long it
takes — is deliberately a separate object. It is marketing copy that changes on
its own schedule, and nothing operational should ever read it.

Standard library only: this is imported by tools, by the hub, by ops scripts
and by tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolIdentity:
    """The stable facts. Every field is a name something else already uses."""

    key: str                      #: fleet key — fleet.conf column 1, legal_conf key
    repo_dir: str                 #: the workspace directory on the Mac
    github_repo: str              #: the GitHub repository; CI checks out under this
    service: str                  #: systemd unit, and the leaf of the server path
    server_path: str              #: where the deploy puts it
    port: int                     #: the localhost port its service listens on
    entitlement_key: str          #: the hub's key, and PROVISION_SECRET_<KEY>
    display_name: str             #: the brand, as it reaches a person
    canonical_domain: str         #: the one address that serves the tool
    locales: tuple[str, ...]      #: the participant languages it publishes
    legacy_domains: tuple[str, ...] = ()   #: 301 to canonical_domain, never served
    short_name: str = ""          #: where a card needs fewer words; defaults to display_name

    def __post_init__(self):
        if not self.short_name:
            object.__setattr__(self, "short_name", self.display_name)

    @property
    def public_url(self) -> str:
        return f"https://{self.canonical_domain}"

    @property
    def default_sender(self) -> str:
        """The From: address, unless the environment overrides it.

        Derived rather than stored: every tool in the fleet sends as info@ its
        own canonical domain, and a stored copy would be one more string to
        disagree with the domain beside it.
        """
        return f"info@{self.canonical_domain}"

    @property
    def all_domains(self) -> tuple[str, ...]:
        return (self.canonical_domain,) + self.legacy_domains


@dataclass(frozen=True)
class ToolPresentation:
    """What the hub says about a tool. Copy, not configuration."""

    key: str
    lede: str
    blurb: str
    audience: str
    duration: str


#: Every tool, keyed by fleet key. The hub is in here too: it is deployed,
#: monitored and gated like the rest, and leaving it out is how a fleet-wide
#: rule quietly stops covering nine.
TOOLS: dict[str, ToolIdentity] = {
    t.key: t for t in (
        ToolIdentity(
            key="controversy", repo_dir="ControversyGenerator",
            github_repo="controversy-generator", service="controversygenerator",
            server_path="/var/www/controversygenerator", port=8001,
            entitlement_key="controversy_generator",
            display_name="Controversy Generator",
            canonical_domain="controversygenerator.org", locales=("en",),
        ),
        ToolIdentity(
            key="drawbridge", repo_dir="Drawbridge-Drama",
            github_repo="drawbridge-drama", service="drawbridge-drama",
            server_path="/var/www/drawbridge-drama", port=8004,
            entitlement_key="drawbridge_drama", display_name="Drawbridge Drama",
            canonical_domain="drawbridge-drama.org", locales=("en",),
        ),
        ToolIdentity(
            key="inequality", repo_dir="Inequality",
            github_repo="inequality", service="inequality-explorer",
            server_path="/var/www/inequality-explorer", port=8005,
            entitlement_key="inequality_explorer",
            display_name="Inequality Explorer",
            canonical_domain="inequality-explorer.org", locales=("en",),
        ),
        ToolIdentity(
            key="layoff", repo_dir="Layoff-Exercise",
            github_repo="layoff-exercise", service="layoff-exercise",
            server_path="/var/www/layoff-exercise", port=8000,
            entitlement_key="layoff_exercise", display_name="Layoff Exercise",
            canonical_domain="layoff-exercise.org", locales=("en", "de"),
        ),
        ToolIdentity(
            key="lsr", repo_dir="polarity-profiler",
            github_repo="lsr-profiler", service="lsr-profiler",
            server_path="/var/www/lsr-profiler", port=8003,
            entitlement_key="lsr_profiler", display_name="Polarity Profiler",
            canonical_domain="polarity-profiler.org",
            # The old brand. nginx serves it only to 301 everything to the
            # canonical domain — classroom posters with QR codes do not get
            # reprinted because a product was renamed. Anything that BUILDS a
            # URL must use canonical_domain; this tuple exists so a check can
            # tell a legacy address from a wrong one.
            legacy_domains=("lsr-profiler.org",),
            locales=("en", "de"),
        ),
        ToolIdentity(
            key="moralmirror", repo_dir="Moral-mirror",
            github_repo="moral-mirror", service="moral-mirror",
            server_path="/var/www/moral-mirror", port=8010,
            entitlement_key="moral_mirror", display_name="Moral Mirror",
            canonical_domain="moral-mirror.org", locales=("en",),
        ),
        ToolIdentity(
            key="orgsim", repo_dir="Orgdesignsim",
            github_repo="orgdesignsim", service="orgdesignsim",
            server_path="/var/www/orgdesignsim", port=8002,
            entitlement_key="orgdesignsim", display_name="OrgDesignSim",
            canonical_domain="orgdesignsim.org", locales=("en",),
        ),
        ToolIdentity(
            key="whiteout", repo_dir="Whiteout",
            github_repo="whiteout", service="whiteout-exercise",
            server_path="/var/www/whiteout-exercise", port=8006,
            entitlement_key="whiteout", display_name="Whiteout Exercise",
            # The hub's card has said just "Whiteout" since it was written;
            # the notice, the e-mail and the page titles say "Whiteout
            # Exercise". Both are deliberate, which is why there are two fields
            # rather than one argument about which is right.
            short_name="Whiteout",
            canonical_domain="whiteout-exercise.org", locales=("en", "de"),
        ),
        ToolIdentity(
            key="phronon", repo_dir="Phronon",
            github_repo="phronon", service="phronon",
            server_path="/var/www/phronon", port=8007,
            entitlement_key="phronon", display_name="Phronon",
            canonical_domain="phronon.org", locales=("en",),
        ),
    )
}

#: The eight teaching tools — everything except the hub. The distinction is
#: load-bearing in a dozen places (participant flows, share cards, the fleet
#: brand list), and each of them used to spell it out for itself.
TEACHING_TOOLS: tuple[str, ...] = tuple(k for k in TOOLS if k != "phronon")


def by_repo_dir(name: str) -> ToolIdentity:
    for t in TOOLS.values():
        if t.repo_dir == name:
            return t
    raise KeyError(f"no tool has repository directory {name!r}")


def by_github_repo(name: str) -> ToolIdentity:
    for t in TOOLS.values():
        if t.github_repo == name:
            return t
    raise KeyError(f"no tool has GitHub repository {name!r}")


def by_entitlement(key: str) -> ToolIdentity:
    for t in TOOLS.values():
        if t.entitlement_key == key:
            return t
    raise KeyError(f"no tool has entitlement key {key!r}")


def by_domain(domain: str) -> ToolIdentity:
    """Canonical or legacy — whichever address arrived."""
    d = domain.lower().removeprefix("www.")
    for t in TOOLS.values():
        if d in t.all_domains:
            return t
    raise KeyError(f"no tool serves {domain!r}")


def display_names() -> tuple[str, ...]:
    """Every brand in the fleet, teaching tools only.

    This is the list the e-mail leak check uses: a message for one tool must
    carry its own name and no other. It lived as eight private copies, five of
    which had dropped a name; `phronon_common.testing.mail_harness` holds the
    canonical tuple and now derives it from here.
    """
    return tuple(TOOLS[k].display_name for k in TEACHING_TOOLS)
