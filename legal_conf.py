"""Per-tool configuration for the shared legal pages — ALL NINE TOOLS IN ONE FILE.

Blueprint: phronon-legal-blueprint.md (rev. 2). The sorting rule is Part 3:
an element is FLEET-CONSTANT if it describes the operator or the
infrastructure — that text lives in phronon_common/legal_templates/ and may
never be duplicated here. An element is PER-TOOL if it describes the data.
Those are the entries below.

One file for all nine on purpose: a single table where the nine retention
periods sit side by side is how you notice one of them is wrong. Nine
separate config files reproduce the drift problem at one remove.

Every retention sentence below was checked against the code that enforces it
on 2026-07-30 (Tier 1 #4: a promised deletion with no job behind it is the
most damaging false statement possible, because the disproving evidence is in
our own database):

  controversy  auto_anonymize_old_surveys()      12 months, daily worker
  inequality   _anonymise_worker()               30 days after close (or last
                                                 response), hourly; 14/7-day
                                                 warnings, 3 x 30-day postponements,
                                                 unused sessions deleted at 90 d
                                                 (converged 2026-09-03)
  lsr          lifecycle.py                      30 days, postponable by educator
                                                 (converged 2026-09-03)
  orgsim       _retention_worker()               hourly; completed runs anonymised
                                                 30 d after close (or last completed
                                                 run); 14/7-day warnings, 3 x 30-day
                                                 postponements, unused sessions
                                                 deleted at 90 d (converged 2026-09-03)
  layoff       auto_anonymize_old_classes()      30 days after last response,
                                                 hourly; 14/7-day warnings and
                                                 3 x 30-day postponements
  moralmirror  NO JOB EXISTS — the text says so honestly (open item)
  drawbridge   no job — retention reviewed periodically (stated as such)
  whiteout     no job — educator-deleted (stated as such)

CORRECTION 2026-07-30 (second pass, after an external review). The first pass
checked retention claims against the code but NOT the "what we collect" claims,
and that is exactly where the false statements were:

  whiteout    the notice said no name/e-mail was collected. /join REQUIRES an
              e-mail, stores it on participants.email, and shows it to the
              educator. Corrected.
  lsr         the notice called the e-mail optional; the form marks it required
              and the handler rejects a submission without it. It also called
              the benchmarking tick-box "optional consent" while the handler
              refuses to continue unless it is ticked. Both corrected.
  inequality  art9 was False; the demographics page asks two political-opinion
              items (pol_redistribution, pol_regulation) and stores them.
              Political opinion is Art. 9(1) data. Corrected to True.
  inequality  the advertised 30-day auto-anonymisation CANNOT RUN: it sets
              responses.student_name = NULL, but that column is NOT NULL and
              the server runs STRICT_TRANS_TABLES. Verified on production:
              "ERROR 1048: Column 'student_name' cannot be null", 0 of 9 rows
              anonymised. The notice now states this instead of promising it.
  phronon     the hub notice said it processes only logs, contact and admin
              credentials; its fleet overview reads class titles, join codes,
              educator e-mail, status and counts from all nine tools. Disclosed.

LESSON: verify every claim against the code that implements it, not just the
ones that look risky. A "we do not collect X" sentence is the easiest kind of
claim to get wrong and the most damaging to publish.

ART9 flags below are the Part 3.3 question-3 determinations. They currently
carry no name/date — that sign-off is an OPEN DECISION for the operator
(blueprint Part 9 #3 recommends one lawyer-hour on exactly this).

The `basis` texts state the CURRENT legal position (legitimate interest /
contract). The blueprint's Part 0.2 decision moves participants to consent —
that flip happens per tool when the consent capture (Stage 4) ships for it,
by editing the tool's `basis` entry here. Do not state consent before the
checkbox exists (Tier 1 #7: recording or claiming consent never given).
"""

import re

# Version stamp shown on every legal document, fleet-wide. Bump the version
# when wording changes substantively; git is the audit trail for the text.
NOTICE_VERSION = "2026-09"
LAST_UPDATED = "2026-09-02"

# nginx logs to /var/log/nginx/access.log, logrotate: daily, rotate 14.
# Verified on the server 2026-07-30. If the rotation policy changes, change it
# THERE and HERE together.
LOG_RETENTION_DAYS = 14

# ── Reading a published lifetime cell ────────────────────────────────────────
# The cookie tables state a lifetime in prose, in whichever language the page is
# in. `server-ops/closing_audit.py` compares those words with the `max_age` the
# app actually sets, and its parser used to live over there and know only
# English — which was fine while the German pages printed the English cells and
# became a hole the day they stopped (19 August 2026).
#
# It lives here instead because this file is where the sentences are. A tool
# gaining a new locale adds its unit words to ONE table, and every reader of the
# published text — the deploy gate and the fleet tests — learns them together.
#
# A unit this table does not know reads as "no number published", which SKIPS
# the row rather than failing it. That is the safe direction for prose like
# "browser session", and the reason both languages are spelled out in full
# rather than matched loosely: a missing word disables a check silently.
LIFETIME_SECONDS = {
    "second": 1, "seconds": 1, "sekunde": 1, "sekunden": 1,
    "minute": 60, "minutes": 60, "minuten": 60,
    "hour": 3600, "hours": 3600, "stunde": 3600, "stunden": 3600,
    "day": 86400, "days": 86400, "tag": 86400, "tage": 86400, "tagen": 86400,
}

#: Longest first, so "stunden" is not matched as "stunde" plus a stray "n".
_UNIT_ALT = "|".join(sorted(LIFETIME_SECONDS, key=len, reverse=True))


def lifetime_seconds(text: str) -> list:
    """Every duration in a published lifetime cell, in seconds.

    "5-15 minutes", "5–15 Minuten" and "browser session / 2 hours" all yield a
    RANGE; a cookie is fine if its real max_age matches any value in it.
    """
    # "5-15 minutes" / "5–15 Minuten": the first number carries no unit of its
    # own, so give it the one that follows before scanning. Both the ASCII
    # hyphen and the en dash appear in the tables.
    text = re.sub(r"(\d+)\s*[-–]\s*(\d+)(\s*)(" + _UNIT_ALT + r")",
                  r"\1 \4 \2\3\4", text, flags=re.I)
    return [int(num) * LIFETIME_SECONDS[unit.lower()]
            for num, unit in re.findall(r"(\d+)\s*(" + _UNIT_ALT + r")", text, re.I)]


TOOLS = {
    # ────────────────────────────────────────────────────────────────────
    "controversy": {
        "domain": "controversygenerator.org",
        "tool_name": "Controversy Generator",
        "languages": ["en"],
        # 2026-09 (2 September): the container is a SESSION fleet-wide (README
        # §9). Every "survey" that named the thing an educator creates and
        # participants join now reads "session"; "survey" survives only for
        # the activity itself. First explicit version for this tool (CG-011):
        # rows stamped 2026-07 resolve to the wording before this change.
        # 2026-09-03-identity: ONE participant identity, resume and
        # withdrawal mechanism fleet-wide (owner's decision, README §11).
        # What changed for a participant: the browser holds a random
        # identifier and nothing else, for 8 hours; a deletion link they can
        # actually use, replaceable if lost; and, where an address exists, a
        # one-time link for continuing on another device.
        # 2026-09-04-identity: the deletion code is no longer held in the database between
        # submitting and the page that shows it — it is created by that
        # page, so no copy of it exists anywhere else, ever.
        "notice_version": "2026-09-04-identity",
        "last_updated": "2026-09-04",
        "art9": True,  # statement bank can probe political/moral positions
        "purpose": {
            "en": "The Controversy Generator collects short survey responses to "
                  "opinion statements and pairs participants with differing "
                  "viewpoints, to support structured discussion in classrooms "
                  "and organisations.",
        },
        "collect": {
            "en": """
<h3>From session participants</h3>
<ul>
  <li><strong>Name or username</strong> — as entered by you; a pseudonym is fine.</li>
  <li><strong>E-mail address</strong> — <strong>optional unless your educator turns it on</strong> for a particular session, in which case it is required to submit. Each session says which applies.</li>
  <li><strong>Session code</strong> — attributes your response to the correct session.</li>
  <li><strong>Survey responses</strong> — your answers to the opinion statements, stored as numerical values. Depending on the statements chosen by your educator, your answers can reveal personal views.</li>
  <li><strong>Submission timestamp.</strong></li>
</ul>
<h3>From educators and administrators</h3>
<ul>
  <li><strong>E-mail address</strong> — for backoffice sign-in.</li>
  <li><strong>Password</strong> — stored only as a bcrypt hash.</li>
  <li><strong>Session data</strong> — titles, items and settings of sessions you create.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the survey and pairing discussion partners</strong> — Art. 6(1)(a) GDPR, your consent, given by ticking the required box before you submit. You can withdraw it at any time until the session is consolidated (see Retention), using the link on your confirmation page; withdrawing does not affect processing that already happened. Every answer here is treated as data about your personal views — including political, religious or philosophical positions — whatever the statements happen to ask, so this is always explicit consent within the meaning of Art. 9(2)(a). We do not judge that statement by statement.</li>
  <li><strong>Research and teaching beyond your session</strong> — Art. 6(1)(a) GDPR, a separate optional consent. Declining changes nothing about your participation, your results or your discussion pairing; it means your answers are deleted at the retention deadline rather than counted into the anonymous totals described under Retention.</li>
  <li><strong>Educator and administrator accounts</strong> — Art. 6(1)(b) GDPR, performance of the arrangement under which the account was created.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR, our legitimate interest in operating the service securely.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see participant names, e-mail addresses (where provided) and individual responses for their own sessions only.</li>
  <li><strong>Anonymous statement statistics are shared between educators.</strong> Once a session is consolidated, what remains is a count of how many people chose each point on the scale for each statement, per half-year. Those totals are pooled across all sessions and are visible to every educator using the same statement from the shared library. They are shown only where at least two different sessions and at least five responses stand behind the figure, so no single session can be read out of them, and they contain nothing that identifies a person, a session or a date.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security purposes only.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>One deadline, set when your session closes.</strong> Thirty days after your educator closes a session, it is <em>consolidated</em>: the individual responses are erased — names, e-mail addresses, submission times and the record of who was paired with whom. Answers from participants who ticked the optional research box are first counted into anonymous per-statement totals; everyone else's are deleted without being counted. A daily job enforces this.</li>
  <li><strong>If a session is never closed</strong>, it is consolidated 30 days after the last response instead, so nothing can stay open indefinitely.</li>
  <li><strong>If a session never receives a response</strong>, it is simply deleted 90 days after it was created.</li>
  <li><strong>Postponement:</strong> the educator is warned 14 days before the date and can push it back by 30 days, at most three times — no later than 120 days after the session closed or the last response, which is 90 days beyond the original deletion date. If you gave an e-mail address, you are warned 7 days before.</li>
  <li><strong>After consolidation</strong> only anonymous totals remain, and they are kept indefinitely. They cannot be traced back to you, to your session or to a date, which is also why a response cannot be withdrawn once that day has passed.</li>
  <li><strong>Manual deletion:</strong> educators and administrators can delete whole sessions or individual submissions at any time before then.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>Until your session is consolidated you can withdraw your
response yourself, using the withdrawal link on your confirmation page, or ask
your educator (who can delete individual submissions) or us. The date is shown
to you before you submit, and if you gave an e-mail address you are reminded
seven days beforehand.</p>
<p><strong>After that date we cannot do it, and neither can anyone else.</strong>
Consolidation erases the individual responses and leaves only anonymous totals,
so there is nothing left that could be identified as yours and removed. This is
a deliberate design: it is what makes the remaining figures genuinely anonymous
rather than merely stripped of a name.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement. A name (which may be a pseudonym) is needed to take part so that
your educator can attribute responses. The e-mail address is optional by
default; an educator can make it required for their own session, and where they
have, you cannot submit without it.</p>""",
        },
        "provenance": {
            "en": """<p>The Controversy Generator concept, pairing algorithm, and
site design are original works. Statement banks configured by educators remain
the responsibility of the educator who writes them.</p>""",
        },
        # NOTE on dismiss_anonymize_until (added to the table 2026-07-30): it is a
        # PREFERENCE cookie, and the blueprint warns that a preference is not
        # automatically covered by the § 25(2) Nr. 2 TDDDG exemption. The position
        # taken here is that it IS covered, because it is written only when the
        # educator clicks "dismiss" — remembering that click is precisely the
        # service they just requested, not a convenience we decided for them. If
        # it ever becomes a default or a silent setting, that reasoning collapses
        # and the no-banner conclusion must be revisited.
        "cookies": [
            ("student_session", "Signed, HTTP-only. Holds a random identifier and nothing else — no name, no address, no answers. It links your browser to the pass you are taking, and lets you reopen your results page afterwards.", "8 hours", "participants"),
            ("quiz_code", "Carries the session code between pages. Your answers and the name you typed are held on our server against the identifier above, not in your browser.", "browser session", "participants"),
            ("norms_&lt;code&gt; / privacy_&lt;code&gt;", "Record that the session's ground-rules and privacy note were shown.", "1 hour", "participants"),
            ("backoffice_user", "Keeps educators and administrators signed in (signed, HTTP-only).", "6 hours (educators) / 3 hours (administrators)", "backoffice"),
            ("cg_pending_totp / cg_pending2fa", "Carries the intermediate step of two-factor sign-in: the pending-login marker (5 minutes) and, while you are enrolling, the not-yet-confirmed TOTP secret (15 minutes).", "5-15 minutes", "backoffice"),
            ("dismiss_anonymize_until", "Remembers that an educator dismissed the \"these sessions need anonymising\" reminder, so it is not shown again for a week. Set only when the educator clicks dismiss.", "7 days", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "drawbridge": {
        "domain": "drawbridge-drama.org",
        "tool_name": "Drawbridge Drama",
        "languages": ["en"],
        # -b, later the same day: Drawbridge stops keeping class responses for
        # ever (FL-001). It was the last tool in the fleet that did. The clock
        # is Controversy Generator's; what happens at the deadline is
        # Whiteout's, because this tool writes no aggregate anywhere and
        # deleting outright would take the research value with it. The
        # erasure section is rewritten around the deletion code, which is new:
        # with no address on file it is the only self-service route there can
        # be, and the old text offered nothing but a cookie-lifetime window.
        # 2026-08 (16 August): the duplicate-prevention hashes are now actually
        # checked before a submission is accepted, and the notice says what the
        # check can and cannot do rather than claiming more than it delivers.
        # The access line records that the raw baseline sample is admin-only —
        # it had been open to every educator account. The free-text box now
        # carries, here and on the page, the one warning no code can enforce.
        # -b, later the same day: the collection list named neither the
        # randomly-assigned question version (which IS the experiment) nor the
        # record that this notice was shown. Both are stored per participant.
        # 2026-09 (2 September): the container is a SESSION fleet-wide (README
        # §9); every "class" that named it now reads "session", and the
        # duplicate-check bullet no longer says "browser session" for a cookie,
        # because the word now has one meaning on the page.
        # 2026-09-03-identity: ONE participant identity, resume and
        # withdrawal mechanism fleet-wide (owner's decision, README §11).
        # What changed for a participant: the browser holds a random
        # identifier and nothing else, for 8 hours; a deletion link they can
        # actually use, replaceable if lost; and, where an address exists, a
        # one-time link for continuing on another device.
        # 2026-09-04-identity: the deletion code is no longer held in the database between
        # submitting and the page that shows it — it is created by that
        # page, so no copy of it exists anywhere else, ever.
        "notice_version": "2026-09-04-identity",
        "last_updated": "2026-09-04",
        "art9": True,  # moral-judgment attributions
        "purpose": {
            "en": "The Drawbridge Drama presents a short illustrated narrative and "
                  "asks participants to attribute responsibility, to support "
                  "classroom discussion of moral judgment and framing effects.",
        },
        "collect": {
            "en": """
<h3>From session participants</h3>
<p>We do not ask for your name, e-mail address, phone number or any account.
The data we store is <strong>pseudonymous</strong>, per submission:</p>
<ul>
  <li><strong>Session code</strong> — attributes the response to the correct session; it is not linked to you personally.</li>
  <li><strong>Story-path code</strong> — which version of the story flow was shown.</li>
  <li><strong>Your responses</strong> — your responsibility attribution, certainty rating and optional follow-ups; a free-text explanation if you choose "Other". Your answers can reveal your moral views. The free-text box is the one field we cannot check for you: please do not type your name or anything that identifies you or another person, and we ask you not to on the page itself.</li>
  <li><strong>Optional demographics</strong> — age bracket, gender, childhood country/region, prior familiarity. All optional.</li>
  <li><strong>Submission timestamp.</strong></li>
  <li><strong>A deletion code</strong> — shown to you once when you submit, and stored so that entering it later finds your response. It is the only thing that can, since no name or address is collected. Keep it if you might want your answers removed; we cannot re-send it.</li>
  <li><strong>Your answer to the optional research question</strong>, with the date and the version of the wording you were shown — this is how we can demonstrate what you agreed to.</li>
  <li><strong>Short one-way hashes of your participant cookie and browser identifier</strong> — checked before a response is accepted, so that one browser cannot submit twice. The original cookie and browser string are not retained in these fields, but the hashes can still single out the same browser; clearing your cookies gives you a fresh cookie, so this prevents accidental double submission rather than a determined one. Because such a key exists, the data is pseudonymous rather than anonymous.</li>
</ul>
<h3>From baseline (Prolific) participants</h3>
<ul>
  <li><strong>Prolific participant ID</strong> — a quasi-identifier used to deduplicate responses and to honour withdrawal via Prolific.</li>
</ul>
<h3>From educators and administrators</h3>
<ul>
  <li><strong>E-mail address, display name</strong> — for backoffice sign-in.</li>
  <li><strong>Password</strong> — stored only as a bcrypt hash.</li>
  <li><strong>Session data</strong> — names, codes and configuration of sessions you create.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the study and aggregate visualisations</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the educational programme in which participants take part.</li>
  <li><strong>Keeping a stripped research row after the session is erased</strong> — Art. 6(1)(a) GDPR, your separate, optional consent. The box is not pre-selected, declining changes nothing about the exercise, and you can withdraw at any time with your deletion code.</li>
  <li><strong>Educator and administrator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see aggregate counts and the pseudonymous response-level data for their own sessions, plus aggregated comparison figures from the baseline sample. No stored field identifies a participant directly.</li>
  <li><strong>The administrator</strong> has technical access for maintenance, backups and security only, and is the only role that can open or export the raw baseline (Prolific) sample.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Session responses</strong> — erased automatically <strong>30 days</strong> after the session is closed, or 30 days after the last response if it is never closed. A session nobody ever joined is removed 90 days after it was created. Erasure removes the whole session: every response, the free-text answers, the optional demographics and the browser hashes. Educators are warned 14 days beforehand and may postpone up to three times by 30 days. The latest possible date is <strong>120 days after</strong> the session closed or the last response — 90 days beyond the original deletion date.</li>
  <li><strong>If you tick the optional research box</strong> — one row of yours is kept after that date: the experimental story version and factor levels, your choice, certainty, optional closed-choice follow-up, and any demographics you gave. <strong>Your free-text explanation is never copied.</strong> The row has no session code or session name and no date finer than the half-year. It does carry a new random cohort key shared by people who answered in the same session, so co-membership can be analysed without retaining which session it was. Those rows are <strong>pseudonymous, not anonymous</strong>: the deletion code you were given still matches yours, which is exactly what lets you withdraw it. If you do not tick it, nothing of yours survives the deadline.</li>
  <li><strong>Baseline (Prolific) responses</strong> — a one-time benchmark sample, collected as research from the outset with consent given through Prolific and retained as part of that dataset. It is not on the session clock above. The Prolific ID is held only for deduplication and for withdrawal through Prolific.</li>
  <li><strong>Educator accounts</strong> — retained until deactivated or deleted by an administrator.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p><strong>Use the deletion code you were shown when you
submitted.</strong> Enter it at <a href="/withdraw">/withdraw</a> and your
response is erased immediately — before or after the 30-day deadline, and
including the research row if you kept one. That code is the only thing that
identifies your response as yours: we store no name and no e-mail address, so
we cannot look it up for you, and we cannot send you another.</p>
<p>If you did not keep it, we cannot identify which response is yours: the
duplicate-prevention hashes are not exposed as a lookup code and sending us a
message from the same browser does not transmit them. Baseline (Prolific)
participants can request deletion via their Prolific ID.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement. No identifying information is required at all; the demographic
questions are optional and skipping them has no consequence.</p>""",
        },
        "provenance": {
            "en": """<p>The Drawbridge Drama retells a public-domain classroom
parable; the illustrated narrative, story-flow design, and site are original
works.</p>""",
        },
        "cookies": [
            ("drawbridge_session", "Signed, HTTP-only participant cookie holding a random identifier and nothing else. Which version of the story you were given, how far you had read and whether you had submitted are held on our server against that identifier.", "8 hours", "participants"),
            ("drawbridge_csrf", "Protects the participant forms against cross-site request forgery (signed, HTTP-only). Separate from the cookie above so the deletion form still works later, when there is no pass left to carry it.", "8 hours", "participants"),
            ("drawbridge_admin", "Keeps educators and administrators signed in (signed, HTTP-only).", "6 hours (educators) / 3 hours (administrators)", "backoffice"),
            ("bo_csrf", "Protects backoffice forms against cross-site request forgery (signed, HTTP-only).", "1 hour", "backoffice"),
            ("bo_flash", "Carries a one-off status message between two backoffice pages.", "10 seconds", "backoffice"),
            ("db_pending_totp / drawbridge_pending2fa", "Carries the intermediate step of two-factor sign-in: the pending-login marker (5 minutes) and, while you are enrolling, the not-yet-confirmed TOTP secret (15 minutes).", "5-15 minutes", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "inequality": {
        "domain": "inequality-explorer.org",
        "tool_name": "Inequality Explorer",
        "languages": ["en"],
        # 2026-09 (2 September): the container is a SESSION fleet-wide (README
        # §9); the four places this notice still said "class" now say session.
        # First explicit version for this tool: rows stamped 2026-07 resolve
        # to the wording before this change.
        # 2026-09-03-retention: the lifecycle converged on the fleet clock —
        # one deadline per session (30 days after close or last response),
        # 14/7-day warnings, 3 x 30-day postponements, unused sessions
        # deleted at 90 days. Previously 30 days after EACH response.
        # 2026-09-03-identity: ONE participant identity, resume and
        # withdrawal mechanism fleet-wide (owner's decision, README §11).
        # What changed for a participant: the browser holds a random
        # identifier and nothing else, for 8 hours; a deletion link they can
        # actually use, replaceable if lost; and, where an address exists, a
        # one-time link for continuing on another device.
        # 2026-09-04-identity: the cookie table now lists the 5-minute `withdraw_once`
        # cookie that carries the deletion link to the results page, and
        # the retention section no longer says a withdrawal must reach us
        # before the deadline — the participant's own link works after it,
        # as the erasure section always said.
        "notice_version": "2026-09-04-ie002",
        "last_updated": "2026-09-04",
        "art9": True,  # 2026-07-30: the demographics page asks two political-opinion
                       # items (pol_redistribution, pol_regulation), stored as enums.
                       # Political opinions are Art. 9(1) data — the earlier False was wrong.
        "purpose": {
            "en": "The Inequality Explorer collects numerical estimates of "
                  "wealth distribution and compares them with real data, to "
                  "support classroom discussion of perceptions of inequality.",
        },
        "collect": {
            "en": """
<h3>From participants</h3>
<ul>
  <li><strong>Name or pseudonym</strong> — identifies your response to the session educator.</li>
  <li><strong>E-mail address</strong> — optional, only if provided.</li>
  <li><strong>Session code</strong> — links your response to a specific session.</li>
  <li><strong>Responses</strong> — your numerical estimates of wealth distribution.</li>
  <li><strong>Optional demographics</strong> — age range, gender, income bracket.</li>
  <li><strong>Two optional political-opinion questions</strong> — your level of agreement with statements on wealth redistribution and on regulating personal lifestyle choices. These reveal a <strong>political opinion</strong>, a special category of data under Art. 9(1) GDPR. They are stored <strong>only if you tick the separate box giving explicit consent</strong>; if you do not, the answers are discarded and never written to the database, even if you filled them in. Skipping them changes nothing else about your participation.</li>
  <li><strong>Reflection answers</strong> — an optional page after your results asks how confident you were beforehand, what surprised you most, whether your view of an ideal distribution changed, and offers a <strong>free-text box</strong>. Only what you type is stored. Please do not put names or anything sensitive in the free-text box: unlike the other fields it can contain anything, so <strong>it is emptied for everyone at the anonymisation deadline</strong>, whatever you chose about research use.</li>
  <li><strong>Your consent choices</strong> — whether you agreed to research use and to the political questions, with the date and the version of the wording you were shown. This is what makes a consent provable, and it is kept for as long as the data it covers.</li>
  <li><strong>Submission timestamp.</strong></li>
</ul>
<h3>From educators</h3>
<ul>
  <li><strong>E-mail address</strong> — for backoffice sign-in.</li>
  <li><strong>Password</strong> — stored only as a bcrypt hash.</li>
  <li><strong>Session data</strong> — names, codes, configuration, responses.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the survey and the session debrief</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the educational programme in which participants take part.</li>
  <li><strong>The two political-opinion questions</strong> — <strong>Art. 9(2)(a) explicit consent</strong>, given by ticking the dedicated box on the demographics page. This is a separate box from the research one on purpose: you can help with research and still decline the political questions. Without that tick the answers are not stored at all.</li>
  <li><strong>Keeping demographics and reflection answers past the 30-day window, and using them outside your own educator's teaching</strong> — your separate consent (Art. 6(1)(a)), also its own unticked box. Within the window and within your educator's own courses, those answers feed the session debrief and your educator's cross-session summary on Art. 6(1)(f); that is the teaching the session is part of. If you decline, they are <strong>deleted</strong> at the 30-day mark instead of being kept.</li>
  <li><strong>Educator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see who responded (names or pseudonyms) but not individual response values linked to a person; responses are shown in aggregate or anonymised form. The session summary does quote <strong>reflection notes</strong> back to the educator, without a name attached — so please write nothing there you would not want the room to read. Educators can delete erroneous entries in their own sessions, and see a summary across their own sessions.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>One deadline per session.</strong> Names and e-mail addresses are anonymised automatically 30 days after your educator closes the session — or, if it is never closed, 30 days after its last response. Reopening a session does not restart that clock. The routine runs hourly.</li>
  <li><strong>What happens at that deadline depends on your consent.</strong> If you did <em>not</em> consent to research use, <strong>your whole response is deleted</strong> — your name and address, your answers, your demographics and your reflection, all of it. Nothing is kept. If you <em>did</em> consent, your name, e-mail address and free-text reflection are removed and the rest is kept, but the record is <strong>cut loose from your session</strong>: the link to it is removed and the timestamp is reduced to the month, so the answers sit in a large cross-session pool instead of a group of twenty where a combination of age, gender and income could point at one person. Your deletion link keeps working on that record for as long as it exists.</li>
  <li><strong>Warnings and postponement:</strong> educators are warned 14 days before the deadline and may postpone it by 30 days, up to three times. Participants who left an e-mail address are warned 7 days before.</li>
  <li><strong>Unused sessions:</strong> a session nobody joins is deleted 90 days after it was created.</li>
  <li><strong>What that means for you:</strong> once the deadline has passed <em>we</em> can no longer find your individual response — nothing then connects it to your name or address — so if you want us to find it for you, write before then. Your own deletion link is not affected: it keeps working afterwards, because the record it points at carries the same one-way fingerprint. See &ldquo;Deleting your response&rdquo; below.</li>
  <li><strong>Manual anonymisation:</strong> educators can anonymise or archive a session at any time before the deadline. Doing so applies exactly the steps described above, immediately — it is the same routine, not a lighter version of it.</li>
</ul>""",
        },
        "erasure": {
            "en": """
<p><strong>You can delete your own response.</strong> Every response gets a personal
deletion link, shown once when you finish. Opening it shows what would be removed and
asks you to type a word to confirm; nothing happens until you do.</p>
<p><strong>If you no longer have your deletion link</strong>, ask for a new one at <a href="/withdrawal-link">/withdrawal-link</a> with the session code and the e-mail address you took part with. We send it to that address and nowhere else, and we answer the same way whether or not we hold it, so the page cannot be used to find out who took part. The new link replaces any earlier one, which stops working at that moment. We keep only a one-way fingerprint of these links, never the link itself, so a copy of our database gives nobody the power to delete your data — which is also why we cannot re-send the one you had.</p>
<p>The link keeps working <strong>after</strong> the session's anonymisation deadline,
for as long as any record of yours exists — either the pseudonymous research record,
if you agreed to that, or the anonymised record still counted in your session's figures.
What we cannot do after the deadline is find your record for you, because nothing then
connects it to your name or address. You can still write to us or to your educator
before that date.</p>
<p><strong>If you gave no e-mail address</strong>, the link shown when you finished is
the only one you will get, and we cannot send you another.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement. A name or pseudonym is needed so your educator can see who has
responded. Everything on the demographics page is voluntary: every field
offers &ldquo;prefer not to say&rdquo;, the whole page can be skipped, and
neither consent box has to be ticked. Declining any of it does not affect your
results, the session debrief, or anything else.</p>""",
        },
        "provenance": {
            "en": """<p>The comparison data on real wealth distributions is drawn
from published public sources; the survey design and site are original works.</p>""",
        },
        "cookies": [
            ("survey_state", "Signed, HTTP-only. Holds a random identifier and nothing else. Which session you joined, which step you are on and your in-progress estimates are held on our server against it, so a reload does not lose them and you can reopen your results page.", "8 hours", "participants"),
            ("withdraw_once", "Signed, HTTP-only. Carries your personal deletion link from the moment you finish to the results page that shows it, once. It is deleted as that page is drawn, and it is the only cookie that ever holds anything more than a random identifier.", "5 minutes", "participants"),
            ("backoffice", "Keeps educators and administrators signed in (signed, HTTP-only).", "6 hours (educators) / 3 hours (administrators)", "backoffice"),
            ("wee_pending_totp / pending2fa", "Carries the intermediate step of two-factor sign-in: the pending-login marker (5 minutes) and, while you are enrolling, the not-yet-confirmed TOTP secret (15 minutes).", "5-15 minutes", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "layoff": {
        "domain": "layoff-exercise.org",
        "tool_name": "Layoff Exercise",
        "languages": ["en", "de"],
        # 2026-08 (16 August): three corrections, each of which had the notice
        # describing something the code did not do. Automatic anonymisation is
        # stated for every class rather than only those that reached round 2 —
        # the query was narrower than the promise. The educator access line now
        # says educators also see cross-class AGGREGATE analytics, which they
        # always could. And the audit trail is database records, not a monthly
        # rotating file; it has been a table since 12 August (FL-002).
        # 2026-09 (2 September): the container is a SESSION fleet-wide (README
        # §9) — "class"/"Klasse"/"Kurs" become session/Session in both
        # languages, and the German educator is "Lehrperson" throughout.
        # 2026-09-02-retention: converged the lifecycle to the fleet clock.
        # 2026-09-03-identity: ONE participant identity, resume and
        # withdrawal mechanism fleet-wide (owner's decision, README §11).
        # What changed for a participant: the browser holds a random
        # identifier and nothing else, for 8 hours; a deletion link they can
        # actually use, replaceable if lost; and, where an address exists, a
        # one-time link for continuing on another device.
        # 2026-09-04-identity: the provision section now says what the required e-mail
        # address is actually for, and that it is used for nothing else
        # (owner's re-ratification, 4 September 2026).
        "notice_version": "2026-09-04-identity",
        "last_updated": "2026-09-04",
        "art9": False,  # ranking/structural decisions
        "purpose": {
            "en": "The Layoff Exercise asks participants to rank candidates in a "
                  "fictional layoff scenario, to support classroom discussion of "
                  "decision-making criteria and fairness.",
            "de": "Die Layoff Exercise bittet Teilnehmende, Kandidatinnen und "
                  "Kandidaten in einem fiktiven Stellenabbau-Szenario zu reihen, "
                  "um die Diskussion über Entscheidungskriterien und Fairness im "
                  "Unterricht zu unterstützen.",
        },
        "collect": {
            "en": """
<h3>From participants</h3>
<ul>
  <li><strong>E-mail address</strong> — required; identifies your submission and prevents duplicates.</li>
  <li><strong>Session code</strong> — groups participants by session.</li>
  <li><strong>Ranking decisions</strong> — your responses to the exercise.</li>
  <li><strong>Optional demographics</strong> — only the fields you choose to answer.</li>
  <li><strong>Submission timestamps.</strong></li>
</ul>
<h3>From educators</h3>
<ul>
  <li><strong>E-mail address</strong> — for backoffice sign-in.</li>
  <li><strong>Password</strong> — stored only as a bcrypt hash.</li>
  <li><strong>Session data</strong> — names, codes, configuration, responses.</li>
  <li><strong>An audit record of backoffice actions</strong> — the educator's e-mail address and the <strong>IP address</strong> an action came from, stored as database records. This is a security record: it is how an account compromise is reconstructed. Records are deleted after <strong>12 months</strong>.</li>
</ul>""",
            "de": """
<h3>Von Teilnehmenden</h3>
<ul>
  <li><strong>E-Mail-Adresse</strong> — erforderlich; identifiziert Ihre Abgabe und verhindert Doppel­abgaben.</li>
  <li><strong>Session-Code</strong> — ordnet Teilnehmende einer Session zu.</li>
  <li><strong>Reihungs­entscheidungen</strong> — Ihre Antworten in der Übung.</li>
  <li><strong>Freiwillige demografische Angaben</strong> — nur die Felder, die Sie ausfüllen.</li>
  <li><strong>Zeitstempel der Abgabe.</strong></li>
</ul>
<h3>Von Lehrpersonen</h3>
<ul>
  <li><strong>E-Mail-Adresse</strong> — für die Anmeldung im Backoffice.</li>
  <li><strong>Passwort</strong> — ausschließlich als bcrypt-Hash gespeichert.</li>
  <li><strong>Session-Daten</strong> — Namen, Codes, Konfiguration, Antworten.</li>
  <li><strong>Protokoll der Backoffice-Aktionen</strong> — die E-Mail-Adresse der Lehrperson und die <strong>IP-Adresse</strong>, von der eine Aktion ausging, als Datenbank­einträge gespeichert. Dies ist eine Sicherheitsaufzeichnung: Damit lässt sich eine Kontokompromittierung nachvollziehen. Die Einträge werden nach <strong>12 Monaten</strong> gelöscht.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the exercise and the session debrief</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the educational programme in which participants take part.</li>
  <li><strong>Educator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Durchführung der Übung und der Auswertung in der Session</strong> — Art. 6 Abs. 1 lit. f DSGVO, unser berechtigtes Interesse an der Unterstützung des Bildungsprogramms, an dem die Teilnehmenden teilnehmen.</li>
  <li><strong>Konten von Lehrpersonen</strong> — Art. 6 Abs. 1 lit. b DSGVO.</li>
  <li><strong>Sicherheit, Rate-Limiting und Missbrauchs­abwehr</strong> — Art. 6 Abs. 1 lit. f DSGVO.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see the participants of their own sessions (e-mail addresses) and the session's responses for the debrief. They can also open <strong>aggregate analytics across all sessions</strong> — combined figures only, with small groups suppressed, never another session's individual responses or addresses.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Lehrpersonen</strong> sehen die Teilnehmenden ihrer eigenen Sessions (E-Mail-Adressen) und die Antworten der Session für die Auswertung. Zusätzlich können sie <strong>aggregierte Auswertungen über alle Sessions hinweg</strong> aufrufen — ausschließlich zusammengefasste Werte, kleine Gruppen unterdrückt, niemals Einzelantworten oder Adressen einer anderen Session.</li>
  <li><strong>Der Administrator</strong> hat ausschließlich technischen Zugriff für Wartung und Sicherheit.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Automatic pseudonymisation:</strong> sessions are pseudonymised automatically 30 days after their last response (hourly check), whichever rounds the session ran. E-mail addresses are replaced by stable per-session labels; rankings, optional demographics, the session link and submission timestamps remain joined for aggregate analysis. These rows are <strong>not anonymous</strong>.</li>
  <li><strong>Warnings and postponement:</strong> educators are warned 14 days before that date and may postpone it by 30 days, up to three times. Participants with an e-mail address are warned 7 days before. A later response moves the last-response anchor and causes fresh warnings for the new date.</li>
  <li><strong>Unused sessions:</strong> a session nobody joins is deleted 90 days after it was created.</li>
  <li><strong>Educator-triggered pseudonymisation:</strong> educators are asked to pseudonymise a session as soon as it is finished, and can do so at any time.</li>
  <li><strong>Backoffice audit log:</strong> kept as database records and deleted after <strong>12 months</strong>.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Automatische Pseudonymisierung:</strong> Sessions werden 30 Tage nach ihrer letzten Antwort automatisch pseudonymisiert (stündliche Prüfung) — unabhängig davon, welche Runden die Session durchlaufen hat. E-Mail-Adressen werden durch stabile, sessionbezogene Kennzeichnungen ersetzt; Reihungen, freiwillige demografische Angaben, Session-Zuordnung und Abgabezeitpunkte bleiben für aggregierte Auswertungen miteinander verknüpft. Diese Datensätze sind <strong>nicht anonym</strong>.</li>
  <li><strong>Warnungen und Aufschub:</strong> Lehrpersonen werden 14 Tage vor diesem Datum gewarnt und können es bis zu dreimal um jeweils 30 Tage aufschieben. Teilnehmende mit E-Mail-Adresse werden 7 Tage vorher gewarnt. Eine spätere Antwort verschiebt den Anker der letzten Antwort und löst neue Warnungen für das neue Datum aus.</li>
  <li><strong>Ungenutzte Sessions:</strong> Eine Session, der niemand beitritt, wird 90 Tage nach ihrer Erstellung gelöscht.</li>
  <li><strong>Pseudonymisierung durch Lehrpersonen:</strong> Lehrpersonen werden gebeten, eine Session unmittelbar nach ihrem Ende zu pseudonymisieren, und können dies jederzeit tun.</li>
  <li><strong>Backoffice-Protokoll:</strong> als Datenbank­einträge gespeichert und nach <strong>12 Monaten</strong> gelöscht.</li>
</ul>""",
        },
        "erasure": {
            "en": """
<p><strong>You can delete your own submission.</strong> The closing page shows a
personal deletion link once. Opening it shows what would be removed and asks you to
type a word to confirm; nothing happens until you do. It removes your rankings and
your optional demographic answers.</p>
<p><strong>If you no longer have your deletion link</strong>, ask for a new one at <a href="/withdrawal-link">/withdrawal-link</a> with the session code and the e-mail address you took part with. We send it to that address and nowhere else, and we answer the same way whether or not we hold it, so the page cannot be used to find out who took part. The new link replaces any earlier one, which stops working at that moment. We keep only a one-way fingerprint of these links, never the link itself, so a copy of our database gives nobody the power to delete your data — which is also why we cannot re-send the one you had.</p>
<p>The link keeps working <strong>after</strong> pseudonymisation, when your address
has been replaced by a stable per-session label: the record is then pseudonymous rather
than anonymous, and the link still deletes it. What we cannot do at that point is find
it for you, because the address that pointed at it is gone. You can also write to us or
to your educator at any time.</p>""",
            "de": """<p>Vor der Pseudonymisierung schreiben Sie uns oder Ihrer Lehrperson
unter Angabe der verwendeten E-Mail-Adresse; die Abgabe kann gefunden und
gelöscht werden. Nach der Pseudonymisierung ist die Adresse gelöscht; daher
können wir in der Regel nicht mehr feststellen, welche stabile,
sessionbezogene Zeile zu Ihnen gehörte. Die gespeicherten Zeilen bleiben
pseudonym und sind nicht anonym.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement, but an e-mail address is <strong>technically required</strong> to
take part; without it a submission cannot be recorded. It does three things and nothing else: it stops the same person submitting twice, it lets you pick up where you left off on a different device, and it is where we send the warning before your answers are deleted and the link that deletes them yourself. We do not use it to contact you for anything else.
Demographic fields are optional.</p>""",
            "de": """<p>Die Bereitstellung von Daten ist weder gesetzlich noch
vertraglich vorgeschrieben; eine E-Mail-Adresse ist jedoch <strong>technisch
erforderlich</strong>, um teilzunehmen — ohne sie kann keine Abgabe gespeichert
werden. Sie erfüllt drei Zwecke und sonst keinen: Sie verhindert doppelte Abgaben, sie erlaubt Ihnen, auf einem anderen Gerät dort weiterzumachen, wo Sie aufgehört haben, und an sie gehen die Warnung vor der Löschung Ihrer Antworten sowie der Link, mit dem Sie sie selbst löschen. Für nichts anderes verwenden wir sie. Demografische Felder sind freiwillig.</p>""",
        },
        "provenance": {
            "en": """<p>The Layoff Exercise scenario, materials and site are
original works created for teaching.</p>""",
        },
        "cookies": [
            ("layoff_participant", "Signed, HTTP-only. Carries a random participant identifier and nothing else — not your address, not the session code. It is how the site knows this browser is the one that joined, so your briefing, rankings, demographics and closing page belong to the same person.", "8 hours", "participants"),
            ("layoff_flash", "Carries a one-off status message between two pages.", "5 minutes", "all"),
            ("layoff_admin", "Keeps educators and administrators signed in (signed, HTTP-only).", "6 hours (educators) / 3 hours (administrators)", "backoffice"),
            ("lo_pending_totp / layoff_pending2fa", "Carries the intermediate step of two-factor sign-in: the pending-login marker (5 minutes) and, while you are enrolling, the not-yet-confirmed TOTP secret (15 minutes).", "5-15 minutes", "backoffice"),
        ],
        # The German page renders THIS list, not the one above — same cookies,
        # same order, same numbers, German words. The pairing is enforced by
        # `phronon_common/tests/test_cookie_tables_de.py`, which fails if a tool
        # declares "de" and has no `cookies_de`, if the two lists name different
        # cookies, or if a lifetime cell disagrees between the languages.
        # `closing_audit.py` reads both and understands Stunde/Minute/Tag.
        "cookies_de": [
            ('layoff_participant', 'Signiert, HTTP-only. Enthält ausschließlich eine zufällige Teilnahme-Kennung — nicht Ihre Adresse, nicht den Session-Code. Damit erkennt die Seite, dass dieser Browser derjenige ist, der teilgenommen hat, sodass Briefing, Reihungen, demografische Angaben und Abschlussseite zur selben Person gehören.',
             '8 Stunden', 'Teilnehmende'),
            ('layoff_flash', 'Überträgt eine einmalige Statusmeldung von einer Seite zur nächsten.',
             '5 Minuten', 'alle'),
            ('layoff_admin', 'Hält Lehrpersonen und Administratoren angemeldet (signiert, HTTP-only).',
             '6 Stunden (Lehrpersonen) / 3 Stunden (Administratoren)', 'Backoffice'),
            ('lo_pending_totp / layoff_pending2fa', 'Überträgt den Zwischenschritt der Zwei-Faktor-Anmeldung: die Markierung der offenen Anmeldung (5 Minuten) und, während der Einrichtung, das noch nicht bestätigte TOTP-Geheimnis (15 Minuten).',
             '5–15 Minuten', 'Backoffice'),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "polarity": {
        "domain": "polarity-profiler.org",
        "tool_name": "Polarity Profiler",
        "languages": ["en", "de"],
        # 2026-08 (16 August): the short participant-facing notices said
        # "fully anonymized patterns" and "anonymised answers" for data that
        # keeps scores and any demographics given — pseudonymous, as the formal
        # notice here has always said. One word, but it is the word that
        # decides whether Art. 15-22 rights still apply to what is kept.
        # -b, later the same day: the "what we collect" list was INCOMPLETE.
        # It named nothing of the report and withdrawal tokens (which are what
        # make those links work without a password) and nothing of the consent
        # and acknowledgement evidence stored beside every response. Neither
        # contradicted anything published; both are things a reader is entitled
        # to see listed, and an inventory that omits them is not the inventory
        # Art. 13 asks for.
        # 2026-09 (2 September): the container is a SESSION fleet-wide (README
        # §9) — "class"/"Klasse"/"Kurs" become session/Session in both
        # languages, and the German educator is "Lehrperson" throughout.
        # 2026-09-03-retention: the lifecycle converged on the fleet clock.
        # 2026-09-03-identity: ONE participant identity, resume and
        # withdrawal mechanism fleet-wide (owner's decision, README §11).
        # What changed for a participant: the browser holds a random
        # identifier and nothing else, for 8 hours; a deletion link they can
        # actually use, replaceable if lost; and, where an address exists, a
        # one-time link for continuing on another device.
        # 2026-09-04-identity: the GERMAN erasure section was three versions behind the
        # English: it still offered the report page as a deletion route
        # (removed in migration 023), never mentioned /withdrawal-link,
        # and said no identifier survives the deadline — untrue for anyone
        # who consented to research use. It now mirrors the English.
        "notice_version": "2026-09-04-identity",
        "last_updated": "2026-09-04",
        "art9": False,  # leadership-style point allocations
        "purpose": {
            "en": "The Polarity Profiler collects scenario-based point allocations and "
                  "produces a personal leadership-style repertoire report, with an "
                  "optional session comparison, for use in executive education.",
            "de": "Der Polarity Profiler erhebt szenariobasierte Punktverteilungen und "
                  "erstellt einen persönlichen Bericht zum Führungsstil-Repertoire, "
                  "mit optionalem Session-Vergleich, für die Führungskräfte­bildung.",
        },
        "collect": {
            "en": """
<h3>From participants</h3>
<ul>
  <li><strong>E-mail address</strong> — <strong>required</strong> to take part. It is used to send your PDF report, to include you in the session comparison, and to give you a withdrawal link.</li>
  <li><strong>Questionnaire responses</strong> — point allocations, context answers, derived style scores.</li>
  <li><strong>Optional demographics</strong> — only fields you fill in; used for aggregate analysis only.</li>
  <li><strong>Submission timestamp.</strong></li>
  <li><strong>Two access tokens</strong> — one that opens your report link and one that opens your withdrawal link. They are what let those links work without a password; anyone holding a link can use it, so treat them as private.</li>
  <li><strong>A record of what you were shown and what you chose</strong> — when you acknowledged this notice, and, if you answered the research question on your results page, your answer with the date and the version of the wording you saw. This is how we can demonstrate what you agreed to, which the law requires of us.</li>
</ul>
<h3>From educators and administrators</h3>
<ul>
  <li><strong>E-mail address</strong> — for backoffice sign-in.</li>
  <li><strong>Password</strong> — stored only as a bcrypt hash.</li>
  <li><strong>Session data</strong> — names and codes of sessions you create.</li>
</ul>""",
            "de": """
<h3>Von Teilnehmenden</h3>
<ul>
  <li><strong>E-Mail-Adresse</strong> — <strong>erforderlich</strong> für die Teilnahme. Sie wird verwendet, um Ihnen Ihren PDF-Bericht zu senden, Sie in den Session-Vergleich einzubeziehen und Ihnen einen Widerrufslink bereitzustellen.</li>
  <li><strong>Fragebogen­antworten</strong> — Punktverteilungen, Kontextantworten, abgeleitete Stilwerte.</li>
  <li><strong>Freiwillige demografische Angaben</strong> — nur Felder, die Sie ausfüllen; ausschließlich für aggregierte Auswertungen.</li>
  <li><strong>Zeitstempel der Abgabe.</strong></li>
  <li><strong>Zwei Zugangs-Token</strong> — eines öffnet den Link zu Ihrem Bericht, eines den Link zum Widerruf. Sie sind es, die diese Links ohne Passwort funktionieren lassen; wer einen Link hat, kann ihn verwenden — behandeln Sie sie daher vertraulich.</li>
  <li><strong>Ein Nachweis darüber, was Ihnen gezeigt wurde und wie Sie entschieden haben</strong> — wann Sie diesen Hinweis zur Kenntnis genommen haben und, falls Sie die Forschungsfrage auf Ihrer Ergebnisseite beantwortet haben, Ihre Antwort mit Datum und der Version des Wortlauts, den Sie gesehen haben. So können wir belegen, worin Sie eingewilligt haben — das verlangt das Gesetz von uns.</li>
</ul>
<h3>Von Lehrpersonen und Administratoren</h3>
<ul>
  <li><strong>E-Mail-Adresse</strong> — für die Anmeldung im Backoffice.</li>
  <li><strong>Passwort</strong> — ausschließlich als bcrypt-Hash gespeichert.</li>
  <li><strong>Session-Daten</strong> — Namen und Codes der von Ihnen angelegten Sessions.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the profiler, generating the session aggregate, sending the PDF report</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the executive-education programme in which participants are enrolled.</li>
  <li><strong>Research and cross-session benchmark use</strong> — your consent (Art. 6(1)(a)), offered on your results page once you have seen what your answers produced. It is entirely optional and separate from taking part: declining changes nothing about your report or your place in the session comparison, and you can give or withdraw it at any time from that page. The tick-box on the first page is a different thing — it confirms you have read this notice, and is not a consent to research use.</li>
  <li><strong>Educator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Durchführung des Profilers, Session-Aggregat, Versand des PDF-Berichts</strong> — Art. 6 Abs. 1 lit. f DSGVO, unser berechtigtes Interesse an der Unterstützung des Weiterbildungs­programms, in dem die Teilnehmenden eingeschrieben sind.</li>
  <li><strong>Forschungs- und sessionübergreifende Benchmark-Nutzung</strong> — Ihre Einwilligung (Art. 6 Abs. 1 lit. a DSGVO), die Ihnen auf Ihrer Ergebnisseite angeboten wird, nachdem Sie gesehen haben, was Ihre Antworten ergeben. Sie ist vollkommen freiwillig und von der Teilnahme unabhängig: Eine Ablehnung ändert nichts an Ihrem Bericht oder Ihrem Platz im Session-Vergleich, und Sie können sie dort jederzeit erteilen oder widerrufen. Das Kästchen auf der ersten Seite ist etwas anderes — es bestätigt, dass Sie diese Erklärung gelesen haben, und ist keine Einwilligung in die Forschungsnutzung.</li>
  <li><strong>Konten von Lehrpersonen</strong> — Art. 6 Abs. 1 lit. b DSGVO.</li>
  <li><strong>Sicherheit, Rate-Limiting und Missbrauchs­abwehr</strong> — Art. 6 Abs. 1 lit. f DSGVO.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see a completion list for their session (e-mail address and submission time). They do not see individual scores.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Lehrpersonen</strong> sehen eine Abgabeliste ihrer Session (E-Mail-Adresse und Abgabezeitpunkt). Individuelle Ergebnisse sehen sie nicht.</li>
  <li><strong>Der Administrator</strong> hat ausschließlich technischen Zugriff für Wartung und Sicherheit.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Live-session mode:</strong> report access and withdrawal expire 30 days after the session is first closed. Reopening a session does not restart that clock. Educators are warned 14 days before the deadline and can postpone it by 30 days, up to three times; participants with an e-mail address are warned 7 days before. At the deadline your e-mail address, name, withdrawal token and session linkage are removed. What happens to the answers themselves depends on the research choice on your results page: <strong>if you consented</strong>, the pseudonymised answers, scores and demographics are kept for aggregate analysis and research; <strong>if you did not</strong>, the entire response — answers, scores and demographics — is deleted at that deadline. Not choosing counts as not consenting.</li>
  <li><strong>Self-guided mode:</strong> the same 30-day window, counted from submission. Educators are warned 14 days before and participants with an e-mail address 7 days before; because deadlines are individual rather than session-wide, they cannot be postponed.</li>
  <li><strong>Responses anonymised before 1 August 2026:</strong> the research choice above only became reachable on 31 July 2026 — before that the control existed but nothing in the interface called it, so nobody could give or decline it. Responses already anonymised at that point were kept in pseudonymised form under the older rule and are <strong>not</strong> retrospectively deleted. They carry no e-mail address, name, withdrawal token or session link. If you took part before that date and want yours removed, write to us and we will delete the whole set for the period you name.</li>
  <li><strong>Educator accounts:</strong> retained until deleted by the administrator.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Live-Session-Modus:</strong> Berichtszugriff und Widerruf enden 30 Tage nach dem ersten Schließen der Session. Ein erneutes Öffnen startet diese Frist nicht neu. Lehrpersonen werden 14 Tage vor dem Stichtag gewarnt und können ihn bis zu dreimal um jeweils 30 Tage aufschieben; Teilnehmende mit E-Mail-Adresse werden 7 Tage vorher gewarnt. Zum Stichtag werden E-Mail-Adresse, Name, Widerrufstoken und Session-Zuordnung entfernt. Was mit den Antworten selbst geschieht, hängt von der Forschungs-Entscheidung auf Ihrer Ergebnisseite ab: <strong>Haben Sie eingewilligt</strong>, bleiben die pseudonymisierten Antworten, Werte und demografischen Angaben für aggregierte Auswertungen und Forschung erhalten; <strong>haben Sie nicht eingewilligt</strong>, wird die gesamte Antwort — Antworten, Werte und demografische Angaben — zum Stichtag gelöscht. Keine Entscheidung zu treffen gilt als Nicht-Einwilligung.</li>
  <li><strong>Selbststudium:</strong> dieselbe 30-Tage-Frist, gerechnet ab der Abgabe. Lehrpersonen werden 14 Tage vorher und Teilnehmende mit E-Mail-Adresse 7 Tage vorher gewarnt; da die Stichtage individuell und nicht sessionweit sind, können sie nicht aufgeschoben werden.</li>
  <li><strong>Vor dem 1. August 2026 anonymisierte Antworten:</strong> Die oben beschriebene Forschungs-Entscheidung war erst ab dem 31. Juli 2026 erreichbar — zuvor existierte die Funktion, wurde aber von der Oberfläche nie aufgerufen, sodass niemand einwilligen oder ablehnen konnte. Zu diesem Zeitpunkt bereits anonymisierte Antworten wurden nach der früheren Regel in pseudonymisierter Form aufbewahrt und werden <strong>nicht</strong> rückwirkend gelöscht. Sie enthalten weder E-Mail-Adresse noch Namen, Widerrufstoken oder Session-Zuordnung. Wenn Sie vor diesem Datum teilgenommen haben und Ihre Daten entfernt haben möchten, schreiben Sie uns; wir löschen dann den gesamten Bestand des von Ihnen genannten Zeitraums.</li>
  <li><strong>Konten von Lehrpersonen:</strong> bis zur Löschung durch den Administrator.</li>
</ul>""",
        },
        "erasure": {
            "en": """
<p><strong>You can delete your own response.</strong> Your confirmation e-mail carries a
personal deletion link. Opening it shows what would be removed and asks you to type a
word to confirm; nothing happens until you do. Your report link is <em>only</em> a
report link — it cannot delete anything, so forwarding it is safe.</p>
<p><strong>If you no longer have your deletion link</strong>, ask for a new one at <a href="/withdrawal-link">/withdrawal-link</a> with the session code and the e-mail address you took part with. We send it to that address and nowhere else, and we answer the same way whether or not we hold it, so the page cannot be used to find out who took part. The new link replaces any earlier one, which stops working at that moment. We keep only a one-way fingerprint of these links, never the link itself, so a copy of our database gives nobody the power to delete your data — which is also why we cannot re-send the one you had.</p>
<p>The link keeps working <strong>after</strong> the anonymisation deadline if you
agreed to research use, because the pseudonymous record kept for research carries the
same fingerprint; it deletes that record too. If you did not agree, your response is
deleted outright at the deadline and there is nothing left to withdraw.</p>""",
            "de": """
<p><strong>Sie können Ihre eigene Antwort löschen.</strong> Ihre
Bestätigungs-E-Mail enthält einen persönlichen Löschlink. Beim Öffnen sehen Sie
zunächst, was gelöscht würde, und müssen ein Wort eintippen, um zu bestätigen;
vorher geschieht nichts. Ihr Berichtslink ist <em>nur</em> ein Berichtslink — er
kann nichts löschen, Weiterleiten ist also unbedenklich.</p>
<p><strong>Wenn Sie Ihren Löschlink nicht mehr haben</strong>, fordern Sie unter
<a href="/withdrawal-link">/withdrawal-link</a> einen neuen an, mit dem
Session-Code und der E-Mail-Adresse, mit der Sie teilgenommen haben. Wir senden
ihn ausschließlich an diese Adresse und antworten gleich, ob wir sie kennen oder
nicht — die Seite lässt sich also nicht nutzen, um herauszufinden, wer
teilgenommen hat. Der neue Link ersetzt jeden früheren, der in diesem Moment
ungültig wird. Wir speichern nur einen Einweg-Fingerabdruck dieser Links,
niemals den Link selbst; eine Kopie unserer Datenbank gibt daher niemandem die
Möglichkeit, Ihre Daten zu löschen — und aus demselben Grund können wir Ihnen
Ihren alten Link nicht erneut zusenden.</p>
<p>Der Link funktioniert <strong>auch nach</strong> dem Anonymisierungsstichtag,
wenn Sie der Forschungsnutzung zugestimmt haben: Der für die Forschung
aufbewahrte pseudonyme Datensatz trägt denselben Fingerabdruck, und der Link
löscht auch ihn. Haben Sie nicht zugestimmt, wird Ihre Antwort zum Stichtag
vollständig gelöscht, und es bleibt nichts zu widerrufen.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement, but an e-mail address is <strong>technically required</strong> to
start the profiler — without it a response cannot be recorded. The demographic
questions are genuinely optional.</p>""",
            "de": """<p>Die Bereitstellung von Daten ist weder gesetzlich noch
vertraglich vorgeschrieben; eine E-Mail-Adresse ist jedoch <strong>technisch
erforderlich</strong>, um den Profiler zu starten — ohne sie kann keine Antwort
gespeichert werden. Die demografischen Fragen sind tatsächlich freiwillig.</p>""",
        },
        "provenance": {
            "en": """<p>The LSR framework, scenarios, scoring model and report
design are original works created for executive teaching.</p>""",
        },
        "cookies": [
            ("participant_session", "Signed, HTTP-only. Holds a random identifier and nothing else. Your progress through the questionnaire is held on our server against it, and afterwards it lets you reopen your results page.", "8 hours", "participants"),
            ("backoffice", "Keeps educators and administrators signed in (signed, HTTP-only).", "6 hours (educators) / 3 hours (administrators)", "backoffice"),
            ("lsr_pending_totp / lsr_pending2fa", "Carries the intermediate step of two-factor sign-in: the pending-login marker (5 minutes) and, while you are enrolling, the not-yet-confirmed TOTP secret (15 minutes).", "5-15 minutes", "backoffice"),
        ],
        # The German page renders THIS list, not the one above — same cookies,
        # same order, same numbers, German words. The pairing is enforced by
        # `phronon_common/tests/test_cookie_tables_de.py`, which fails if a tool
        # declares "de" and has no `cookies_de`, if the two lists name different
        # cookies, or if a lifetime cell disagrees between the languages.
        # `closing_audit.py` reads both and understands Stunde/Minute/Tag.
        "cookies_de": [
            ('participant_session', 'Signiert, HTTP-only. Enthält ausschließlich eine zufällige Kennung. Ihr Fortschritt im Fragebogen wird auf unserem Server dazu gespeichert; danach können Sie damit Ihre Ergebnisseite erneut öffnen.',
             '8 Stunden', 'Teilnehmende'),
            ('backoffice', 'Hält Lehrpersonen und Administratoren angemeldet (signiert, HTTP-only).',
             '6 Stunden (Lehrpersonen) / 3 Stunden (Administratoren)', 'Backoffice'),
            ('lsr_pending_totp / lsr_pending2fa', 'Überträgt den Zwischenschritt der Zwei-Faktor-Anmeldung: die Markierung der offenen Anmeldung (5 Minuten) und, während der Einrichtung, das noch nicht bestätigte TOTP-Geheimnis (15 Minuten).',
             '5–15 Minuten', 'Backoffice'),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "moralmirror": {
        "domain": "moral-mirror.org",
        "tool_name": "Moral Mirror",
        "languages": ["en"],
        # 2026-08 (16 August): the retention section described a tool that kept
        # session responses until somebody deleted them by hand, and said an
        # automatic job was "planned". The job exists now (FL-001, the clock
        # Controversy Generator and Whiteout already use), so the notice states
        # the real rule and the real ceiling. The second bullet is new and had
        # to be: closing a session folds its answers into cross-session
        # benchmark COUNTS, which survive the deletion — a reader told only
        # "everything is deleted after 30 days" would have been told something
        # that is not quite true.
        # -b, later the same day: the collection list named neither the
        # randomly-assigned question version (which IS the experiment) nor the
        # record that this notice was shown. Both are stored per participant.
        # 2026-09 (2 September): the container is a SESSION fleet-wide (README
        # §9). "Class code" and "class-level" become session; the participant
        # cookie is "a pseudonymous token", no longer a "session token", so the
        # word means one thing on the page.
        # 2026-09-03-identity: ONE participant identity, resume and
        # withdrawal mechanism fleet-wide (owner's decision, README §11).
        # What changed for a participant: the browser holds a random
        # identifier and nothing else, for 8 hours; a deletion link they can
        # actually use, replaceable if lost; and, where an address exists, a
        # one-time link for continuing on another device.
        # 2026-09-04-identity: unfinished answers are now deleted when the 8-hour pass
        # expires rather than at the session's own deadline, which is why
        # an abandoned attempt never needs a deletion code (owner's
        # decision, 4 September 2026).
        "notice_version": "2026-09-04-identity",
        "last_updated": "2026-09-04",
        "art9": True,  # moral judgments
        "purpose": {
            "en": "Moral Mirror lets the participants in a session observe patterns in "
                  "their own moral judgment: they answer short ethical questions and the "
                  "group sees aggregate results. It is descriptive, not "
                  "prescriptive.",
        },
        "collect": {
            "en": """
<h3>From participants</h3>
<p>We do not ask for your name, e-mail address or any account. We store, per
submission:</p>
<ul>
  <li><strong>Your answers</strong> to the activity's questions. Your answers can reveal your moral views.</li>
  <li><strong>Optional demographics</strong> — only the fields you choose to answer.</li>
  <li><strong>A session code</strong> — attaches responses to the correct session, not to you.</li>
  <li><strong>A pseudonymous token</strong> in a cookie, so your answers within one session hang together. Because such a token exists, the data is pseudonymous rather than anonymous.</li>
  <li><strong>Which version of a question you were shown</strong> — some questions exist in more than one wording, and which one you saw is assigned at random and recorded. Comparing those groups is the point of the activity.</li>
  <li><strong>A record that this notice was shown to you</strong> — the moment you pressed "I understand" and the version of the wording you saw. It is not a consent, and nothing here depends on your agreeing: it records that you were informed, which we must be able to show either way.</li>
</ul>
<h3>From educators</h3>
<ul>
  <li><strong>E-mail address</strong> — for backoffice sign-in.</li>
  <li><strong>Password</strong> — stored only as a bcrypt hash.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the activity and showing group results</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the session in which participants take part.</li>
  <li><strong>Educator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Everyone in the session</strong> sees group aggregates. Demographic breakdowns are shown only when at least 5 participants stand behind a group, so no individual can be singled out.</li>
  <li><strong>Educators</strong> see the same aggregates for their own sessions.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>
<p>Pseudonymised, aggregated answers may contribute to cross-session
benchmarks; these are labelled as a convenience sample, not a representative
one.</p>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Session responses</strong> — deleted automatically <strong>30 days</strong> after the session is closed, or 30 days after the last answer if it is never closed. A session nobody ever joined is removed 90 days after it was created. Deletion removes the whole session: every answer, the optional demographics and the condition each participant was assigned. Educators are warned 14 days beforehand and can postpone up to three times by 30 days. The latest possible date is <strong>120 days after</strong> the session closed or the last answer — 90 days beyond the original deletion date.</li>
  <li><strong>Session-level figures</strong> — when an educator closes a session, its answers are added to cross-session benchmarks as <strong>counts only</strong>. Those counts contain no participant records and are not affected by the deletion above; they cannot be traced to a session or a person.</li>
  <li><strong>Unfinished answers</strong> — if you start the activity and leave without reaching your reflection card, what you answered so far is deleted automatically once your 8-hour pass expires. That pass is the only thing that could bring you back to it, so nothing you could still return to is removed. It is also why an unfinished attempt never needs a deletion code: it is gone before the session's own deadline.</li>
  <li><strong>Educator accounts</strong> — retained until deleted.</li>
</ul>""",
        },
        "erasure": {
            "en": """
<p><strong>The deletion code on your reflection card is how you erase your answers.</strong>
It is shown once, on the card, and it is the only way: we collect no name and no e-mail
address, so we cannot send you a replacement and cannot look your answers up any other
way. That is the same design that stops anyone else finding them. Enter the code at
<a href="/withdraw">/withdraw</a>; the page shows what would go and asks you to type a
word to confirm.</p>
<p><strong>If you did not save the code</strong>, everything from the session is deleted
at its retention deadline in any case, and your educator can delete the whole session at
any time.</p>
<p><strong>After the deadline there is nothing to withdraw.</strong> The session is
deleted outright — every participant, answer and assignment. What remains is a count
of how often each question set has been used, which holds no participant records and
cannot be traced to anyone.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement. Nothing identifying is required; demographic questions are
optional and skipping them has no consequence.</p>""",
        },
        "provenance": {
            "en": """<p>The Moral Mirror question set and reveal design are
original works; individual questions draw on widely discussed cases in ethics
teaching.</p>""",
        },
        "cookies": [
            ("moralmirror_pax", "Pseudonymous participant token: keeps your answers within one session together and lets you return to your reflection card (signed, HTTP-only). Holds no name or address. You can clear it yourself with “I am done — forget this browser” on the card.", "8 hours", "participants"),
            ("moralmirror_admin", "Keeps educators and administrators signed in (signed, HTTP-only).", "6 hours (educators) / 3 hours (administrators)", "backoffice"),
            ("mm_pending_totp / moralmirror_pending2fa", "Carries the intermediate step of two-factor sign-in: the pending-login marker (5 minutes) and, while you are enrolling, the not-yet-confirmed TOTP secret (15 minutes).", "5-15 minutes", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "orgsim": {
        "domain": "orgdesignsim.org",
        "tool_name": "OrgDesignSim",
        "languages": ["en"],
        # 2026-09 (2 September): the container is a SESSION fleet-wide (README
        # §9). The retention list had three consecutive "sessions" meaning
        # three different tables; the participant's own run is now a "run"
        # and their pass a "pass", so "session" means one thing. First
        # explicit version for this tool: rows stamped 2026-07 resolve to the
        # wording before this change.
        # 2026-09-03-retention: the lifecycle converged on the fleet clock —
        # completed runs anonymised 30 days after the session closes (was 90
        # days after EACH run completed), 14/7-day warnings, 3 x 30-day
        # postponements, unused sessions deleted at 90 days.
        # 2026-09-03-identity: ONE participant identity, resume and
        # withdrawal mechanism fleet-wide (owner's decision, README §11).
        # What changed for a participant: the browser holds a random
        # identifier and nothing else, for 8 hours; a deletion link they can
        # actually use, replaceable if lost; and, where an address exists, a
        # one-time link for continuing on another device.
        # 2026-09-04-identity: the participant pass is 8 hours, not 24 — the implementation
        # moved with the fleet cookie on 3 September and the notice said
        # 24 in two places. Also says what the required address is for.
        "notice_version": "2026-09-04-identity",
        "last_updated": "2026-09-04",
        "art9": False,  # structural/organisational decisions
        "purpose": {
            "en": "OrgDesignSim is an organisational-design simulation: "
                  "participants restructure a virtual company over a simulated "
                  "year, and educators debrief the results in class.",
        },
        "collect": {
            "en": """
<h3>From participants</h3>
<ul>
  <li><strong>E-mail address</strong> — required to enter a session.</li>
  <li><strong>Display name</strong> — optional; derived from the e-mail address if omitted.</li>
  <li><strong>Session code</strong> — links you to a specific educator's session.</li>
  <li><strong>Simulation data</strong> — the decisions you make and the results your run produces.</li>
  <li><strong>Activity timestamps.</strong></li>
</ul>
<h3>From educators</h3>
<ul>
  <li><strong>E-mail address</strong> — for backoffice sign-in.</li>
  <li><strong>Password</strong> — stored only as a bcrypt hash.</li>
  <li><strong>Session data</strong> — names, codes, configuration, participant results.</li>
  <li><strong>An audit record of backoffice actions</strong> — which account did what (creating, editing, closing, archiving or deleting a session), when, and the <strong>IP address</strong> it came from. This is a security record: it is how an account compromise or an accidental deletion is reconstructed. It is kept for <strong>12 months</strong> and then deleted automatically.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the simulation and the session debrief</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the educational programme in which participants take part.</li>
  <li><strong>Educator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see the participants of their own sessions (name and joining e-mail) and their simulation results — that is the purpose of the debrief. They can delete or archive sessions.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Abandoned runs</strong> — a participant who joined but never finished — are deleted automatically by an hourly job, once their 8-hour pass has expired.</li>
  <li><strong>Completed runs</strong> are anonymised automatically 30 days after the educator closes the session — or, if it is never closed, 30 days after the session's last completed run. The name and e-mail address are removed; the score and result are kept for educator statistics. Closing a session again never moves that date.</li>
  <li><strong>Warnings and postponement:</strong> educators are warned 14 days before that date and may postpone it by 30 days, up to three times. Participants are warned 7 days before at the e-mail address they joined with.</li>
  <li><strong>Unused sessions:</strong> a session nobody joins is deleted 90 days after it was created.</li>
  <li><strong>A participant's pass</strong> expires automatically after 8 hours.</li>
  <li><strong>The backoffice audit record</strong> (educator account, action and IP address) is deleted automatically after <strong>12 months</strong>, by the same hourly job.</li>
  <li><strong>Educators</strong> can delete or archive a session at any time.</li>
</ul>""",
        },
        "erasure": {
            "en": """
<p><strong>You can delete your own run.</strong> The page you reach when you finish
shows a personal deletion link once. Opening it shows what would be removed and asks
you to type a word to confirm; nothing happens until you do. It removes your saved
run, your result and the name and address you joined with.</p>
<p><strong>If you no longer have your deletion link</strong>, ask for a new one at <a href="/withdrawal-link">/withdrawal-link</a> with the session code and the e-mail address you took part with. We send it to that address and nowhere else, and we answer the same way whether or not we hold it, so the page cannot be used to find out who took part. The new link replaces any earlier one, which stops working at that moment. We keep only a one-way fingerprint of these links, never the link itself, so a copy of our database gives nobody the power to delete your data — which is also why we cannot re-send the one you had.</p>
<p>The link keeps working <strong>after</strong> the session's anonymisation date, when
your name and address have been removed and the run is kept for the educator's
statistics: the link still deletes that run. What we cannot do at that point is find it
for you, because the address you joined with is gone. You can also write to us or to
your educator before that date.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement, but an e-mail address is <strong>technically required</strong> to
join a session; without it you cannot take part. It does three things and nothing else: it stops the same person submitting twice, it lets you pick up where you left off on a different device, and it is where we send the warning before your answers are deleted and the link that deletes them yourself. We do not use it to contact you for anything else.
The display name is optional.</p>""",
        },
        "provenance": {
            "en": """<p>The OrgDesignSim scenario, simulation model and site are
original works created for teaching organisational design.</p>""",
        },
        "cookies": [
            ("orgdesignsim_participant", "Signed, HTTP-only. Holds a random identifier for your run, so your saved game and result stay yours and you can reopen them.", "8 hours", "participants"),
            ("orgdesignsim_backoffice", "Keeps educators and administrators signed in (signed, HTTP-only).", "6 hours (educators) / 3 hours (administrators)", "backoffice"),
            ("os_pending_totp / orgdesignsim_pending2fa", "Carries the intermediate step of two-factor sign-in: the pending-login marker (5 minutes) and, while you are enrolling, the not-yet-confirmed TOTP secret (15 minutes).", "5-15 minutes", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "phronon": {
        "domain": "phronon.org",
        "tool_name": "Phronon",
        "languages": ["en"],
        "art9": False,
        "is_hub": True,
        # 2026-09 (2 September): the container is a SESSION fleet-wide (README
        # §9); the overview bullets no longer hedge "class/session".
        "notice_version": "2026-09",
        "last_updated": "2026-09-02",
        "purpose": {
            "en": "phronon.org is the umbrella site for the Phronon online "
                  "tools. Each tool runs on its own domain and "
                  "carries its own legal pages covering the participant data it "
                  "processes; this site collects no participant data itself.",
        },
        "collect": {
            "en": """
<ul>
  <li><strong>Server log files</strong> — see the server-log section below; nothing beyond it.</li>
  <li><strong>E-mail contact</strong> — if you write to us, the details you provide are stored to handle your enquiry and are not passed on.</li>
  <li><strong>Administrator credentials</strong> — for the private administration area; the password is stored only as a bcrypt hash.</li>
</ul>
<ul>
  <li><strong>Fleet overview (administration area only)</strong> — when a signed-in administrator opens the overview, this site queries each tool over the server's own loopback interface and displays that tool's session titles, session codes, the <strong>educator e-mail address</strong> that owns each one, its status, response count and last activity. This data is read live and shown on screen; the hub does not store it.</li>
</ul>
<p>This umbrella site does not collect questionnaire responses or participant
demographics — that processing happens inside the individual tools, each of
which has its own privacy notice describing it.</p>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Operating and securing the site, answering enquiries</strong> — Art. 6(1)(f) GDPR, our legitimate interest in providing and securing the service.</li>
  <li><strong>The fleet overview</strong> — Art. 6(1)(f) GDPR, our legitimate interest in operating the nine tools as one service: seeing which sessions are running, and where, is what makes support and capacity planning possible.</li>
  <li><strong>Administrator accounts</strong> — Art. 6(1)(b) GDPR.</li>
</ul>""",
        },
        "access": {
            "en": """<p>Only the administrator has access to the administration
area, including the fleet overview described above. No participant responses
are shown there — session titles, session codes, counts and the owning educator's
e-mail address are.</p>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Server logs</strong> — rotated and deleted per the server-log section below.</li>
  <li><strong>E-mail correspondence</strong> — kept as long as needed to handle the enquiry.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>Write to us; correspondence and any stored contact details
are deleted on request.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement; the public pages can be read without providing any data at all.</p>""",
        },
        "provenance": {
            "en": """<p>The Phronon name, wordmark, logo and the tools
linked from this site are original works.</p>""",
        },
        "cookies": [
            ("session", "Set only inside the private administration area to keep an administrator signed in (signed, HTTP-only). Not used on public pages.", "3 hours", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "whiteout": {
        "domain": "whiteout-exercise.org",
        "tool_name": "Whiteout Exercise",
        "languages": ["en", "de"],
        # Ahead of the fleet default since 3 August 2026: the demographic
        # breakdown gained a combined "everyone else" row, so the promise about
        # what an educator can see is no longer "five people gave the same
        # answer" but "an average over at least five people". A weaker promise
        # than the one earlier participants consented to, so it needs its own
        # version — theirs stays stamped 2026-07. The other eight tools have not
        # changed a word and keep the default.
        # -d on 8 August (W6): the winter-outdoors bullet now discloses that the
        # answer is stored on the identifiable participant row, outside the
        # demographics consent. Nothing about the handling changed — only the
        # notice's honesty about it — but earlier participants saw a notice
        # that did not say it, so the stamp moves.
        # -e on 9 August: the participant's address is now USED to send mail —
        # a one-time resume link, when someone rejoins from a device that is
        # not already signed in (migration 027, closing an impersonation hole).
        # That is a new processing purpose for data already held, not a new
        # collection, and it is exactly the kind of change a notice must state
        # rather than let a participant discover from their inbox.
        # -f on 15 August: three changes at once, all of them things a
        # participant must be told rather than discover. (1) There is now a real
        # retention rule — a class is erased thirty days after it finishes,
        # where the notice used to say there was no automatic deletion at all.
        # (2) Two new mails: a warning fourteen days before to the educator
        # and seven days before to participants. (3) A NEW, separate, optional
        # consent: answers may be kept beyond the class for research, as a row
        # stripped of address, class and group. Anyone who joined before this
        # date consented to none of it and stays stamped 2026-08-e.
        # -g, later the same day: the closing round's answers join the
        # research dataset (its free-text group reason deliberately does
        # NOT), and the notice now states that nothing is kept from anyone
        # who declined the research box. Both are facts about what is kept,
        # so they belong in the version a participant is stamped with.
        # -n (24 August 2026): the what-had-your-group-decided question is
        # asked in EVERY session, no longer only ahead of the optional second
        # round, and its per-group counts gained an audience — they may now
        # also appear in the class results handout, not only on the wall.
        # Both change what a participant is agreeing to when they answer.
        # 2026-09 (2 September): the container is a SESSION fleet-wide (README
        # §9). English drops "class" for it; German drops Kurs, Sitzung and
        # Klasse for "Session" and "moderierende Person" for "Lehrperson"; the
        # participant cookie is a "participant token", no longer a "session
        # token". Whiteout's checkbox wording moves with it (wo-ack-2026-09-02).
        # 2026-09-03-identity: ONE participant identity, resume and
        # withdrawal mechanism fleet-wide (owner's decision, README §11).
        # What changed for a participant: the browser holds a random
        # identifier and nothing else, for 8 hours; a deletion link they can
        # actually use, replaceable if lost; and, where an address exists, a
        # one-time link for continuing on another device.
        # 2026-09-04-identity: the erasure section now names /withdrawal-link, so a
        # participant who lost the 7-day warning mail has a route that is
        # not 'write to us'; and the provision section says what the
        # required address is for.
        "notice_version": "2026-09-04-identity",
        "last_updated": "2026-09-04",
        "art9": False,  # survival-item rankings
        "purpose": {
            "en": "The Whiteout Exercise presents a survival scenario in which "
                  "participants rank 16 items individually and then as a group, "
                  "to support debriefs on team decision-making.",
            "de": "Die Whiteout Exercise stellt ein Überlebensszenario dar, in dem "
                  "Teilnehmende 16 Gegenstände zuerst einzeln und dann als Gruppe "
                  "reihen, um Auswertungen zu Team­entscheidungen zu unterstützen.",
        },
        "collect": {
            "en": """
<h3>From participants</h3>
<ul>
  <li><strong>E-mail address</strong> — <strong>required</strong> to join a session. It is stored with your ranking and is visible to your educator in the session's participant list. <strong>We send mail to it in exactly two cases:</strong> if someone tries to rejoin your session with your address from a device that is not already signed in, we send a one-time link so that only you can continue; and seven days before the session is erased we send you one notice with your personal withdrawal link. There is no newsletter and no other use.</li>
  <li><strong>Your acknowledgment and consents, as a record</strong> — that you ticked the required box confirming you read this notice (taking part itself rests on our legitimate interest above, not on consent), whether you ticked the genuinely optional research and demographics boxes, when, and which version of this notice and of the wording you were shown. For the optional boxes we keep it because we must be able to show that consent was actually given (Art. 7(1)); for the required box it records that you were informed.</li>
  <li><strong>A pseudonymous participant token</strong> in a cookie, linking your responses within one session.</li>
  <li><strong>Session code</strong> — attributes your response to the correct session.</li>
  <li><strong>Your item rankings</strong> — individual and, where applicable, the group ranking.</li>
    <li><strong>Submission timestamp.</strong></li>
  <li><strong>Your prediction</strong> — on the screen after your ranking you are asked, in one click, how you think it will compare with the rest of the session. It is <strong>required</strong>: the gap between what a session expected and what happened is part of what the exercise teaches. It is stored with your ranking and shown to your educator as session totals and as one unnamed point per person on a chart of predictions against results — never labelled with your name. In a small session, an educator who can see everyone's score could work out which point is yours.</li>
  <li><strong>How often you are outdoors in winter</strong> — asked on that same screen and <strong>optional</strong>; "prefer not to say" is preselected. If you answer, the answer is stored with your response — on the same record as your e-mail address, like your ranking, <strong>not</strong> behind the demographics consent described below. Your educator sees it only as averages over at least five people, never next to your name, and it is not part of the data export.</li>
  <li><strong>Closing questions, in sessions that include them</strong> — some sessions end a group round with two short private questions: which considerations came up in your group's discussion, and what happened to what you yourself knew. <strong>Required in those sessions</strong>, stored with your response, and shown to your educator only in combined form — per group as majority counts, and the self-descriptions only as totals over at least five people. If you gave the separate research consent, these answers are among those kept beyond the session; <strong>the group's written reason for its decision is not kept</strong>, because free text can contain anything and no consent can cover what nobody can predict.</li>
  <li><strong>What your group had decided</strong> — once your group's agreement on a ranking is final, you are asked privately what your group had explicitly agreed to do in the situation: stay, leave, split the group, no agreement, or not discussed as a separate question. In sessions with the optional second round this happens before the second round's material is shown. <strong>Required</strong>, stored with your response, shown as counts per group — never next to your name. Your educator may show those counts to everyone in the session after the exercise and include them in the session results handout, so a group that answers unanimously can be read off them. Deleted with the session, and <strong>not</strong> part of the research data.</li>
  <li><strong>What you yourself would have done, in sessions with the optional second round</strong> — after you have read the shared update and your own recollection, and before your group talks again, you are asked privately whether you would stay with the van or try to reach help. <strong>Required in those sessions</strong>, stored with your response, shown as counts per group — never next to your name. Your educator may show those counts to everyone in the session after the exercise, so a group that leans unanimously can be read off them. Deleted with the session, and <strong>not</strong> part of the research data.</li>
  <li><strong>Optional demographics</strong> — age band, gender, years of work experience, experience leading a team, field of study or work, and country. <strong>Every one of these is optional, the whole page can be skipped, and nothing is stored unless you tick the consent box.</strong> They are shown to your educator only as group averages, and never for a group of fewer than five people. Your country answer is also shown grouped into a world region. We record when you consented and which version of this notice and of the consent wording you saw.</li>
</ul>
<h3>From educators</h3>
<ul>
  <li><strong>Login credentials</strong> — the password is stored only as a bcrypt hash.</li>
  <li><strong>Session data</strong> — names, codes and configuration of sessions you create.</li>
</ul>""",
            "de": """
<h3>Von Teilnehmenden</h3>
<ul>
  <li><strong>E-Mail-Adresse</strong> — <strong>erforderlich</strong>, um an einer Session teilzunehmen. Sie wird zusammen mit Ihrer Reihung gespeichert und ist für die Lehrperson in der Teilnehmendenliste sichtbar. <strong>In genau zwei Fällen senden wir eine Nachricht an diese Adresse:</strong> Versucht jemand, mit Ihrer Adresse von einem nicht angemeldeten Gerät aus wieder einzusteigen, schicken wir einen einmalig gültigen Link, damit nur Sie fortfahren können; und sieben Tage vor der Löschung der Session senden wir Ihnen eine Nachricht mit Ihrem persönlichen Widerrufslink. Es gibt keinen Newsletter und keine weitere Verwendung.</li>
  <li><strong>Ihre Kenntnisnahme und Einwilligungen als Nachweis</strong> — dass Sie das Pflichtkästchen angekreuzt haben, das bestätigt, dass Sie diese Erklärung gelesen haben (die Teilnahme selbst stützt sich auf unser oben genanntes berechtigtes Interesse, nicht auf eine Einwilligung), ob Sie die wirklich freiwilligen Forschungs- und Demografie-Kästchen angekreuzt haben, wann, und welche Fassung dieser Erklärung und des Wortlauts Ihnen angezeigt wurde. Für die freiwilligen Kästchen speichern wir das, weil wir nachweisen können müssen, dass eine Einwilligung tatsächlich erteilt wurde (Art. 7 Abs. 1); für das Pflichtkästchen dokumentiert es, dass Sie informiert wurden.</li>
  <li><strong>Ein pseudonymes Teilnahme-Token</strong> in einem Cookie, das Ihre Antworten innerhalb einer Session verknüpft.</li>
  <li><strong>Session-Code</strong> — ordnet Ihre Antwort der richtigen Session zu.</li>
  <li><strong>Ihre Reihungen</strong> — individuell und ggf. die Gruppenreihung.</li>
    <li><strong>Zeitstempel der Abgabe.</strong></li>
  <li><strong>Ihre Einschätzung</strong> — auf dem Bildschirm nach Ihrer Reihung werden Sie mit einem Klick gefragt, wie diese im Vergleich zum Rest der Session abschneiden wird. Diese Angabe ist <strong>erforderlich</strong>: der Abstand zwischen Erwartung und Ergebnis gehört zum Lernziel der Übung. Sie wird zusammen mit Ihrer Reihung gespeichert und der Lehrperson als Gesamtwert für die Session sowie als je ein unbeschrifteter Punkt pro Person in einem Diagramm angezeigt, das Einschätzungen und Ergebnisse gegenüberstellt — nie mit Ihrem Namen beschriftet. In einer kleinen Session könnte eine Lehrperson, die alle Punktzahlen sieht, allerdings erschließen, welcher Punkt Ihrer ist.</li>
  <li><strong>Wie oft Sie im Winter draußen sind</strong> — auf demselben Bildschirm wie die Einschätzung gefragt und <strong>freiwillig</strong>; „keine Angabe“ ist voreingestellt. Wenn Sie antworten, wird die Angabe zusammen mit Ihrer Antwort gespeichert — im selben Datensatz wie Ihre E-Mail-Adresse, wie Ihre Reihung, <strong>nicht</strong> hinter der unten beschriebenen Einwilligung für demografische Angaben. Die Lehrperson sieht sie ausschließlich als Durchschnittswerte über mindestens fünf Personen, nie neben Ihrem Namen; im Datenexport ist sie nicht enthalten.</li>
  <li><strong>Abschlussfragen, in Sessions, die sie enthalten</strong> — manche Sessions beenden eine Gruppenrunde mit zwei kurzen privaten Fragen: welche Überlegungen in der Diskussion Ihrer Gruppe zur Sprache kamen, und was mit dem geschah, was Sie selbst wussten. In diesen Sessions <strong>erforderlich</strong>; gespeichert mit Ihrer Antwort und der Lehrperson ausschließlich zusammengefasst angezeigt — je Gruppe als Mehrheitszählung, die Selbstauskünfte nur als Summen über mindestens fünf Personen. Wenn Sie die gesonderte Forschungseinwilligung erteilt haben, gehören diese Antworten zu den über die Session hinaus aufbewahrten; <strong>die schriftliche Begründung der Gruppe wird nicht aufbewahrt</strong>, weil Freitext alles enthalten kann und keine Einwilligung abdecken kann, was niemand vorhersehen kann.</li>
  <li><strong>Was Ihre Gruppe entschieden hatte</strong> — sobald die Einigung Ihrer Gruppe auf eine Reihung endgültig ist, werden Sie privat gefragt, was Ihre Gruppe in der Situation ausdrücklich vereinbart hatte: bleiben, aufbrechen, die Gruppe aufteilen, keine Einigung, oder nicht als eigene Frage besprochen. In Sessions mit der optionalen zweiten Runde geschieht das, bevor das Material der zweiten Runde angezeigt wird. <strong>Erforderlich</strong>; gespeichert mit Ihrer Antwort, als Zählung je Gruppe angezeigt — nie neben Ihrem Namen. Ihre Lehrperson kann diese Zählung nach der Übung allen in der Session zeigen und in die Ergebnisunterlagen der Session aufnehmen; bei einer einstimmigen Gruppe lässt sich die einzelne Antwort daran ablesen. Mit der Session gelöscht und <strong>nicht</strong> Teil der Forschungsdaten.</li>
  <li><strong>Was Sie selbst getan hätten, in Sessions mit der optionalen zweiten Runde</strong> — nachdem Sie die gemeinsame Ergänzung und Ihre eigene Erinnerung gelesen haben und bevor Ihre Gruppe erneut spricht, werden Sie privat gefragt, ob Sie beim Van bleiben oder versuchen würden, Hilfe zu erreichen. <strong>In diesen Sessions erforderlich</strong>, zusammen mit Ihrer Antwort gespeichert, als Zählung pro Gruppe angezeigt — nie neben Ihrem Namen. Ihre Lehrperson kann diese Zählung nach der Übung allen in der Session zeigen; bei einer einstimmigen Gruppe lässt sich die einzelne Antwort daran ablesen. Mit der Session gelöscht und <strong>nicht</strong> Teil der Forschungsdaten.</li>
  <li><strong>Freiwillige demografische Angaben</strong> — Altersgruppe, Geschlecht, Jahre Berufserfahrung, Erfahrung in der Teamleitung, Studien- oder Tätigkeitsfeld sowie Land. <strong>Jede dieser Angaben ist freiwillig, die gesamte Seite kann übersprungen werden, und ohne Ihr angekreuztes Einverständnis wird nichts gespeichert.</strong> Der Lehrperson werden sie ausschließlich als Gruppendurchschnitte angezeigt, und nie für Gruppen mit weniger als fünf Personen. Ihre Länderangabe wird zusätzlich zu einer Weltregion zusammengefasst angezeigt. Wir erfassen, wann Sie eingewilligt haben und welche Fassung dieser Erklärung und des Einwilligungstextes Ihnen angezeigt wurde.</li>
</ul>
<h3>Von Lehrpersonen</h3>
<ul>
  <li><strong>Anmeldedaten</strong> — das Passwort wird ausschließlich als bcrypt-Hash gespeichert.</li>
  <li><strong>Session-Daten</strong> — Namen, Codes und Konfiguration der von Ihnen angelegten Sessions.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the exercise and producing group results</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the educational programme in which participants take part.</li>
  <li><strong>Optional demographics</strong> — Art. 6(1)(a) GDPR, your consent. You give it by ticking a box that is not ticked for you, you can skip the page entirely without any effect on the exercise, and you may withdraw it at any time by writing to us, after which the answers are deleted.</li>
  <li><strong>Keeping your answers beyond the session, for research and teaching</strong> — Art. 6(1)(a) GDPR, your separate consent, with the safeguards of Art. 89(1). It is a second box, also not ticked for you, on the same screen as the first. <strong>Leaving it unticked changes nothing about taking part</strong>: you are grouped, you see your results, and everything of yours is simply erased with the rest of the session. Ticking it means one row is kept after the session is erased — see "How long we keep data" — and you can withdraw that consent at any time, with no deadline, using the link we e-mail you before the session is erased.</li>
  <li><strong>Educator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Durchführung der Übung und Erstellung der Gruppenergebnisse</strong> — Art. 6 Abs. 1 lit. f DSGVO, unser berechtigtes Interesse an der Unterstützung des Bildungsprogramms, an dem die Teilnehmenden teilnehmen.</li>
  <li><strong>Freiwillige demografische Angaben</strong> — Art. 6 Abs. 1 lit. a DSGVO, Ihre Einwilligung. Sie erteilen sie durch Ankreuzen eines nicht vorausgewählten Kästchens, Sie können die Seite folgenlos überspringen und Ihre Einwilligung jederzeit widerrufen; die Angaben werden dann gelöscht.</li>
  <li><strong>Aufbewahrung Ihrer Antworten über die Session hinaus, für Forschung und Lehre</strong> — Art. 6 Abs. 1 lit. a DSGVO, Ihre gesonderte Einwilligung, mit den Garantien des Art. 89 Abs. 1. Es ist ein zweites, ebenfalls nicht vorausgewähltes Kästchen auf demselben Bildschirm wie das erste. <strong>Bleibt es leer, ändert das nichts an Ihrer Teilnahme</strong>: Sie werden einer Gruppe zugeordnet, sehen Ihre Ergebnisse, und alles von Ihnen wird zusammen mit der übrigen Session gelöscht. Kreuzen Sie es an, bleibt bei der Löschung der Session ein Datensatz erhalten — siehe „Wie lange wir Daten speichern“ — und Sie können diese Einwilligung jederzeit und ohne Frist widerrufen, über den Link, den wir Ihnen vor der Löschung der Session zusenden.</li>
  <li><strong>Konten von Lehrpersonen</strong> — Art. 6 Abs. 1 lit. b DSGVO.</li>
  <li><strong>Sicherheit, Rate-Limiting und Missbrauchs­abwehr</strong> — Art. 6 Abs. 1 lit. f DSGVO.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see, for their own sessions, the participant list <strong>including each participant's e-mail address</strong>, alongside the individual and group rankings. Demographics are shown to them <strong>only as averages over at least five people</strong> — never next to a name. Answers given by fewer than five people are not shown separately; they are either withheld or combined with other rare answers into a single "everyone else" figure that also covers at least five people.</li>
  <li><strong>Everyone in your session</strong> may be shown those same demographic averages during the debrief, and they may be included in a written summary your educator hands out afterwards. That is part of the discussion the answers are collected for. The five-person floor and the "everyone else" pooling apply exactly as above, so nothing is shown that stands for fewer than five people — but be aware that <strong>five people in a room where everyone knows each other are not anonymous in the way five strangers would be</strong>. If you would rather your answers were not part of that, skip the questions, or ask your educator to delete them.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Lehrpersonen</strong> sehen für ihre eigenen Sessions die Teilnehmendenliste <strong>einschließlich der E-Mail-Adressen</strong> sowie die individuellen und die Gruppenreihungen. Demografische Angaben sehen sie <strong>ausschließlich als Durchschnittswerte über mindestens fünf Personen</strong> — nie neben einem Namen. Antworten, die weniger als fünf Personen gegeben haben, werden nicht einzeln ausgewiesen; sie werden entweder zurückgehalten oder mit anderen seltenen Antworten zu einem einzigen Wert „alle Übrigen“ zusammengefasst, der ebenfalls mindestens fünf Personen umfasst.</li>
  <li><strong>Alle in Ihrer Session</strong> bekommen diese demografischen Durchschnittswerte unter Umständen ebenfalls zu sehen, und sie können in einer schriftlichen Zusammenfassung enthalten sein, die Ihre Lehrperson im Anschluss austeilt. Das ist Teil der Auswertung, für die die Angaben erhoben werden. Die Fünf-Personen-Grenze und die Zusammenfassung zu „alle Übrigen“ gelten dabei unverändert, es wird also nichts angezeigt, was für weniger als fünf Personen steht — bedenken Sie aber, dass <strong>eine Gruppe von fünf Personen in einem Raum, in dem man sich kennt, nicht in demselben Sinne anonym ist wie fünf Fremde</strong>. Wenn Sie das nicht möchten, überspringen Sie die Fragen oder bitten Sie Ihre Lehrperson, Ihre Angaben zu löschen.</li>
  <li><strong>Der Administrator</strong> hat ausschließlich technischen Zugriff für Wartung und Sicherheit.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Everything from a session is erased 30 days after it finishes.</strong> That means your e-mail address, your ranking, your group, your votes, the boards, the results page and the session itself. It runs automatically, it cannot be undone, and it is the same date for everyone in the session. A session that is never finished is erased 30 days after its last submission instead; a session nobody ever joined is deleted 90 days after it was created.</li>
  <li><strong>Your educator can postpone that date by 30 days, up to three times</strong> — never further, and never earlier than a date you have already been told. They are warned 14 days before, and if the date is still approaching, <strong>you are e-mailed 7 days before</strong> so you can withdraw first. That is the only such message you get for a session.</li>
  <li><strong>If you gave the separate research consent</strong>, one row of yours is kept when the session is erased, and kept indefinitely: your ranking, your score, your group's result, your optional answers about yourself, your answers to the closing round in sessions that include one, and the half-year it happened in. <strong>Nothing is kept from anyone who did not tick that box</strong> — their answers are deleted with the session and never counted. It carries no e-mail address, no name, no session code, no group name and no date more precise than the half-year, and the link between it and you is destroyed with the session. It is not anonymous — a ranking plus several bands can still be rare — so we treat it as personal data throughout, keep it only for research and teaching, and never publish anything that stands for fewer than five people. <strong>You can withdraw it at any time, with no time limit</strong>, using the link in that 7-day e-mail.</li>
  <li><strong>Educator accounts</strong> — retained until deactivated or deleted by an administrator.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Alles aus einer Session wird 30 Tage nach deren Abschluss gelöscht.</strong> Das umfasst Ihre E-Mail-Adresse, Ihre Reihung, Ihre Gruppe, Ihre Stimmen, die Gruppentafeln, die Ergebnisseite und die Session selbst. Das geschieht automatisch, ist nicht rückgängig zu machen und gilt für alle in der Session zum selben Datum. Eine nie abgeschlossene Session wird stattdessen 30 Tage nach der letzten Abgabe gelöscht; eine Session, der nie jemand beigetreten ist, 90 Tage nach ihrer Erstellung.</li>
  <li><strong>Ihre Lehrperson kann dieses Datum um jeweils 30 Tage verschieben, höchstens dreimal</strong> — nicht weiter und nie auf ein früheres als das Ihnen bereits genannte Datum. Sie wird 14 Tage vorher benachrichtigt; steht das Datum dann weiterhin bevor, <strong>erhalten Sie 7 Tage vorher eine E-Mail</strong>, damit Sie vorher widerrufen können. Es ist die einzige Nachricht dieser Art zu einer Session.</li>
  <li><strong>Wenn Sie die gesonderte Forschungseinwilligung erteilt haben</strong>, bleibt bei der Löschung der Session ein Datensatz von Ihnen erhalten, und zwar unbefristet: Ihre Reihung, Ihr Ergebnis, das Ergebnis Ihrer Gruppe, Ihre freiwilligen Angaben zur Person, in Sessions mit Abschlussrunde Ihre Antworten darin, sowie das Halbjahr. <strong>Von Personen ohne dieses Häkchen wird nichts aufbewahrt</strong> — ihre Antworten werden mit der Session gelöscht und niemals gezählt. Er enthält keine E-Mail-Adresse, keinen Namen, keinen Session-Code, keinen Gruppennamen und kein Datum genauer als das Halbjahr; die Verbindung zwischen ihm und Ihnen wird mit der Session vernichtet. Er ist nicht anonym — eine Reihung zusammen mit mehreren Angaben kann selten sein —, deshalb behandeln wir ihn durchgehend als personenbezogenes Datum, verwenden ihn nur für Forschung und Lehre und veröffentlichen nichts, was für weniger als fünf Personen steht. <strong>Sie können ihn jederzeit und ohne Frist widerrufen</strong>, über den Link in dieser E-Mail nach 7 Tagen.</li>
  <li><strong>Konten von Lehrpersonen</strong> — bis zur Deaktivierung oder Löschung durch einen Administrator.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p><strong>While the session still exists</strong> your e-mail
address identifies your submission, so we can always find and delete it: write
to us, or ask your educator, naming the session code and the address you
joined with. Educators can delete a single participant's response, or a whole
session, at any time. If you gave optional demographics, withdrawing that
consent deletes those answers and nothing else — the exercise results are
unaffected.</p>
<p><strong>After the session is erased</strong> there is nothing of yours left to
find unless you gave the separate research consent. That row we cannot find
either — by design, it carries no address and nothing linking it to you — so it
can only be reached with the personal link in the e-mail we send you seven days
before the session is erased. Opening the link shows you what would be removed
and removes nothing until you confirm; use it before the deadline and it deletes
your session answers as well. There is no time limit on it.</p>
<p><strong>If you no longer have that link</strong> — or would rather not wait
for the e-mail — ask for one at <a href="/withdrawal-link">/withdrawal-link</a>
with the session code and the address you joined with. We send it to that address
and nowhere else, and we answer the same way whether or not we hold it, so the
page cannot be used to find out who took part. The new link replaces any earlier
one, which stops working at that moment. We keep only a one-way fingerprint of
these links, never the link itself, so a copy of our database gives nobody the
power to delete your data — which is also why we cannot re-send the one you
had.</p>""",
            "de": """<p><strong>Solange die Session besteht</strong>, identifiziert
Ihre E-Mail-Adresse Ihre Abgabe, wir können sie also jederzeit finden und
löschen: Schreiben Sie uns oder Ihrer Lehrperson unter Angabe des
Session-Codes und der verwendeten Adresse. Lehrpersonen können einzelne
Antworten oder ganze Sessions jederzeit löschen. Wenn Sie freiwillige
demografische Angaben gemacht haben, führt der Widerruf dieser Einwilligung
ausschließlich zur Löschung dieser Angaben; die Übungsergebnisse bleiben davon
unberührt.</p>
<p><strong>Nach der Löschung der Session</strong> ist von Ihnen nichts mehr
vorhanden — es sei denn, Sie haben die gesonderte Forschungseinwilligung
erteilt. Diesen Datensatz können auch wir nicht finden: Er enthält
absichtsvoll keine Adresse und nichts, was ihn mit Ihnen verbindet. Erreichbar
ist er ausschließlich über den persönlichen Link in der E-Mail, die wir Ihnen
sieben Tage vor der Löschung der Session senden. Der Link zeigt Ihnen zunächst,
was gelöscht würde, und löscht nichts, bevor Sie bestätigen; vor dem Stichtag
verwendet, löscht er auch Ihre Session-Antworten. Eine Frist gibt es dafür
nicht.</p>
<p><strong>Wenn Sie diesen Link nicht mehr haben</strong> — oder nicht auf die
E-Mail warten möchten — fordern Sie unter
<a href="/withdrawal-link">/withdrawal-link</a> einen neuen an, mit dem
Session-Code und der Adresse, mit der Sie teilgenommen haben. Wir senden ihn
ausschließlich an diese Adresse und antworten gleich, ob wir sie kennen oder
nicht — die Seite lässt sich also nicht nutzen, um herauszufinden, wer
teilgenommen hat. Der neue Link ersetzt jeden früheren, der in diesem Moment
ungültig wird. Wir speichern nur einen Einweg-Fingerabdruck dieser Links,
niemals den Link selbst; eine Kopie unserer Datenbank gibt daher niemandem die
Möglichkeit, Ihre Daten zu löschen — und aus demselben Grund können wir Ihnen
Ihren alten Link nicht erneut zusenden.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement, but an e-mail address is <strong>technically required</strong> to
join a session — without it a submission cannot be recorded. It does three things and nothing else: it stops the same person submitting twice, it lets you pick up where you left off on a different device, and it is where we send the warning before your answers are deleted and the link that deletes them yourself. We do not use it to contact you for anything else.</p>""",
            "de": """<p>Die Bereitstellung von Daten ist weder gesetzlich noch
vertraglich vorgeschrieben; eine E-Mail-Adresse ist jedoch <strong>technisch
erforderlich</strong>, um an einer Session teilzunehmen — ohne sie kann keine
Abgabe gespeichert werden. Sie erfüllt drei Zwecke und sonst keinen: Sie verhindert doppelte Abgaben, sie erlaubt Ihnen, auf einem anderen Gerät dort weiterzumachen, wo Sie aufgehört haben, und an sie gehen die Warnung vor der Löschung Ihrer Antworten sowie der Link, mit dem Sie sie selbst löschen. Für nichts anderes verwenden wir sie.</p>""",
        },
        "provenance": {
            "en": """<p>The Whiteout scenario, benchmark ranking, trap-item design,
scoring logic and source code are original works; the survival-ranking format
draws on established facilitation methodology.</p>""",
        },
        "cookies": [
            ("whiteout_p", "Pseudonymous participant token: keeps your ranking consistent across pages (signed, HTTP-only).", "8 hours", "participants"),
            ("whiteout_csrf", "Protects forms against cross-site request forgery (signed, HTTP-only).", "8 hours", "all"),
            ("whiteout_session", "Keeps educators and administrators signed in (signed, HTTP-only).", "6 hours (educators) / 3 hours (administrators)", "backoffice"),
            ("wo_pending_totp / whiteout_pending2fa", "Carries the intermediate step of two-factor sign-in: the pending-login marker (5 minutes) and, while you are enrolling, the not-yet-confirmed TOTP secret (15 minutes).", "5-15 minutes", "backoffice"),
        ],
        # The German page renders THIS list, not the one above — same cookies,
        # same order, same numbers, German words. The pairing is enforced by
        # `phronon_common/tests/test_cookie_tables_de.py`, which fails if a tool
        # declares "de" and has no `cookies_de`, if the two lists name different
        # cookies, or if a lifetime cell disagrees between the languages.
        # `closing_audit.py` reads both and understands Stunde/Minute/Tag.
        "cookies_de": [
            ('whiteout_p', 'Pseudonymes Teilnahme-Token: hält Ihre Reihung über alle Seiten hinweg konsistent (signiert, HTTP-only).',
             '8 Stunden', 'Teilnehmende'),
            ('whiteout_csrf', 'Schützt Formulare gegen Cross-Site-Request-Forgery (signiert, HTTP-only).',
             '8 Stunden', 'alle'),
            ('whiteout_session', 'Hält Lehrpersonen und Administratoren angemeldet (signiert, HTTP-only).',
             '6 Stunden (Lehrpersonen) / 3 Stunden (Administratoren)', 'Backoffice'),
            ('wo_pending_totp / whiteout_pending2fa', 'Überträgt den Zwischenschritt der Zwei-Faktor-Anmeldung: die Markierung der offenen Anmeldung (5 Minuten) und, während der Einrichtung, das noch nicht bestätigte TOTP-Geheimnis (15 Minuten).',
             '5–15 Minuten', 'Backoffice'),
        ],
    },
}


def get_tool(key: str) -> dict:
    cfg = dict(TOOLS[key])
    cfg.setdefault("key", key)
    cfg.setdefault("contact_email", f"info@{cfg['domain']}")
    cfg.setdefault("notice_version", NOTICE_VERSION)
    cfg.setdefault("last_updated", LAST_UPDATED)
    cfg.setdefault("log_retention_days", LOG_RETENTION_DAYS)
    cfg.setdefault("is_hub", False)
    return cfg
