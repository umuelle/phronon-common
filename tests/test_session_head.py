"""The head of a session page is one template for every tool (21 November 2026).

account_templates/session_head.html draws it: the code in a box that opens the
join sheet, the session's name as the headline, its states, then the tool's
own lines. These tests render it the way a tool does, through the loader that
account_kit.install_templates adds.
"""
import re

import jinja2

from phronon_common import account_kit as kit_mod

PAGE = """{% from "account_kit/session_head.html" import session_head %}
{% call session_head(code=code, name=name, join_url=join_url, badges=badges, join_label=join_label) %}
<p class="bo-detail-meta">{{ facts }}</p>
{% endcall %}"""
BARE = """{% from "account_kit/session_head.html" import session_head %}{{ session_head(code="ABC123") }}"""


def render(source=PAGE, **values) -> str:
    env = jinja2.Environment(loader=jinja2.DictLoader({"page.html": source}),
                             autoescape=jinja2.select_autoescape(["html"]))
    kit_mod.install_templates(env)
    given = {"code": "WHT4KD", "name": "Executive MBA, Module 3", "join_url": "/share/WHT4KD",
             "badges": [("Open", "state-badge--open")], "join_label": "Join sheet", "facts": "28 joined"}
    return env.get_template("page.html").render(**{**given, **values})


def test_the_code_is_one_link_that_opens_the_join_sheet_in_a_new_tab():
    html = render()
    link = re.search(r'<a class="bo-session-code"[^>]*>(.*?)</a>', html, re.S)
    assert link, html
    assert 'href="/share/WHT4KD"' in link.group(0) and 'target="_blank"' in link.group(0)
    assert 'rel="noopener"' in link.group(0)
    assert "WHT4KD" in link.group(1) and "Join sheet" in link.group(1), "the box says what it opens"


def test_the_sessions_name_is_the_headline_and_its_states_follow_it():
    html = render(badges=[("Group ranking", "state-group"), ("Test", "badge-test")])
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1)
    assert "Executive MBA, Module 3" in h1
    assert '<span class="state-badge state-group">Group ranking</span>' in h1
    assert '<span class="state-badge badge-test">Test</span>' in h1
    assert h1.index("Executive MBA") < h1.index("Group ranking")


def test_the_tools_own_facts_stand_under_the_name():
    html = render(facts="2026-11-21 · 28 joined")
    main = html.split('class="bo-session-head__main"', 1)[1]
    assert '<p class="bo-detail-meta">2026-11-21 · 28 joined</p>' in main


def test_a_session_without_a_name_says_so():
    assert "Untitled session" in render(name=None)
    assert "Untitled session" in render(name="")


def test_without_a_join_sheet_the_code_is_plain_text():
    html = render(join_url=None)
    assert "<a " not in html.split("bo-session-head__main")[0], "no link without an address"
    assert "WHT4KD" in html and "Join sheet" not in html


def test_a_tool_can_name_the_sheet_the_box_opens():
    assert "Join sheet, Round 1" in render(join_label="Join sheet, Round 1")


def test_a_name_typed_by_an_educator_is_escaped():
    html = render(name='<script>alert(1)</script>')
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_the_head_can_stand_without_states_or_facts():
    html = render(BARE)
    assert "ABC123" in html and "Untitled session" in html and "state-badge" not in html


def test_a_state_can_carry_a_hover_text():
    html = render(badges=[("Test", "state-badge--test", "Left out of the comparison across sessions"), ("Open", "state-badge--open")])
    assert '<span class="state-badge state-badge--test" title="Left out of the comparison across sessions">Test</span>' in html
    assert '<span class="state-badge state-badge--open">Open</span>' in html
