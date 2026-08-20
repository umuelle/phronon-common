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
  inequality   startup_auto_anonymize()          30 days after last response
  lsr          lifecycle.py                      14 days, postponable by educator
  orgsim       _retention_worker()               hourly; completed anonymized at 90 d
  layoff       auto_anonymize_old_classes()      60 days, hourly check
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
NOTICE_VERSION = "2026-07"
LAST_UPDATED = "2026-08-19"

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
        "art9": True,  # statement bank can probe political/moral positions
        "purpose": {
            "en": "The Controversy Generator collects short survey responses to "
                  "opinion statements and pairs participants with differing "
                  "viewpoints, to support structured discussion in classrooms "
                  "and organisations.",
        },
        "collect": {
            "en": """
<h3>From survey participants</h3>
<ul>
  <li><strong>Name or username</strong> — as entered by you; a pseudonym is fine.</li>
  <li><strong>E-mail address</strong> — <strong>optional unless your educator turns it on</strong> for a particular survey, in which case it is required to submit. Each survey says which applies.</li>
  <li><strong>Survey code</strong> — attributes your response to the correct survey.</li>
  <li><strong>Survey responses</strong> — your answers to the opinion statements, stored as numerical values. Depending on the statements chosen by your educator, your answers can reveal personal views.</li>
  <li><strong>Submission timestamp.</strong></li>
</ul>
<h3>From educators and administrators</h3>
<ul>
  <li><strong>E-mail address</strong> — for backoffice sign-in.</li>
  <li><strong>Password</strong> — stored only as a bcrypt hash.</li>
  <li><strong>Survey data</strong> — titles, items and settings of surveys you create.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the survey and pairing discussion partners</strong> — Art. 6(1)(a) GDPR, your consent, given by ticking the required box before you submit. You can withdraw it at any time until the survey is consolidated (see Retention), using the link on your confirmation page; withdrawing does not affect processing that already happened. Every answer here is treated as data about your personal views — including political, religious or philosophical positions — whatever the statements happen to ask, so this is always explicit consent within the meaning of Art. 9(2)(a). We do not judge that statement by statement.</li>
  <li><strong>Research and teaching beyond your class</strong> — Art. 6(1)(a) GDPR, a separate optional consent. Declining changes nothing about your participation, your results or your discussion pairing; it means your answers are deleted at the retention deadline rather than counted into the anonymous totals described under Retention.</li>
  <li><strong>Educator and administrator accounts</strong> — Art. 6(1)(b) GDPR, performance of the arrangement under which the account was created.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR, our legitimate interest in operating the service securely.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see participant names, e-mail addresses (where provided) and individual responses for their own surveys only.</li>
  <li><strong>Anonymous statement statistics are shared between educators.</strong> Once a survey is consolidated, what remains is a count of how many people chose each point on the scale for each statement, per half-year. Those totals are pooled across all classes and are visible to every educator using the same statement from the shared library. They are shown only where at least two different surveys and at least five responses stand behind the figure, so no single class can be read out of them, and they contain nothing that identifies a person, a class or a date.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security purposes only.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>One deadline, set when your survey closes.</strong> Thirty days after your educator closes a survey, it is <em>consolidated</em>: the individual responses are erased — names, e-mail addresses, submission times and the record of who was paired with whom. Answers from participants who ticked the optional research box are first counted into anonymous per-statement totals; everyone else's are deleted without being counted. A daily job enforces this.</li>
  <li><strong>If a survey is never closed</strong>, it is consolidated 30 days after the last response instead, so nothing can stay open indefinitely.</li>
  <li><strong>If a survey never receives a response</strong>, it is simply deleted 90 days after it was created.</li>
  <li><strong>Postponement:</strong> the educator is warned 14 days before the date and can push it back by 30 days, at most three times — no later than 120 days after the survey closed or the last response, which is 90 days beyond the original deletion date. If you gave an e-mail address, you are warned 7 days before.</li>
  <li><strong>After consolidation</strong> only anonymous totals remain, and they are kept indefinitely. They cannot be traced back to you, to your class or to a date, which is also why a response cannot be withdrawn once that day has passed.</li>
  <li><strong>Manual deletion:</strong> educators and administrators can delete whole surveys or individual submissions at any time before then.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>Until your survey is consolidated you can withdraw your
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
default; an educator can make it required for their own survey, and where they
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
            ("student_session", "Keeps your survey progress and marks your submission (signed, HTTP-only).", "2 hours", "participants"),
            ("quiz_code / answers / user", "Carry the survey code and your in-progress answers between pages.", "browser session / 2 hours", "participants"),
            ("norms_&lt;code&gt; / privacy_&lt;code&gt;", "Record that the survey's ground-rules and privacy note were shown.", "1 hour", "participants"),
            ("withdrawal_token", "Lets you withdraw your submission right after submitting.", "5–10 minutes", "participants"),
            ("backoffice_user", "Keeps educators and administrators signed in (signed, HTTP-only).", "6 hours (educators) / 3 hours (administrators)", "backoffice"),
            ("cg_pending_totp / cg_pending2fa", "Carries the intermediate step of two-factor sign-in: the pending-login marker (5 minutes) and, while you are enrolling, the not-yet-confirmed TOTP secret (15 minutes).", "5-15 minutes", "backoffice"),
            ("dismiss_anonymize_until", "Remembers that an educator dismissed the \"these surveys need anonymising\" reminder, so it is not shown again for a week. Set only when the educator clicks dismiss.", "7 days", "backoffice"),
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
        "notice_version": "2026-08-d",
        "last_updated": "2026-08-19",
        "art9": True,  # moral-judgment attributions
        "purpose": {
            "en": "The Drawbridge Drama presents a short illustrated narrative and "
                  "asks participants to attribute responsibility, to support "
                  "classroom discussion of moral judgment and framing effects.",
        },
        "collect": {
            "en": """
<h3>From class participants</h3>
<p>We do not ask for your name, e-mail address, phone number or any account.
The data we store is <strong>pseudonymous</strong>, per submission:</p>
<ul>
  <li><strong>Class code</strong> — attributes the response to the correct class; it is not linked to you personally.</li>
  <li><strong>Story-path code</strong> — which version of the story flow was shown.</li>
  <li><strong>Your responses</strong> — your responsibility attribution, certainty rating and optional follow-ups; a free-text explanation if you choose "Other". Your answers can reveal your moral views. The free-text box is the one field we cannot check for you: please do not type your name or anything that identifies you or another person, and we ask you not to on the page itself.</li>
  <li><strong>Optional demographics</strong> — age bracket, gender, childhood country/region, prior familiarity. All optional.</li>
  <li><strong>Submission timestamp.</strong></li>
  <li><strong>A deletion code</strong> — shown to you once when you submit, and stored so that entering it later finds your response. It is the only thing that can, since no name or address is collected. Keep it if you might want your answers removed; we cannot re-send it.</li>
  <li><strong>Your answer to the optional research question</strong>, with the date and the version of the wording you were shown — this is how we can demonstrate what you agreed to.</li>
  <li><strong>Short one-way hashes of your session cookie and browser identifier</strong> — checked before a response is accepted, so that one browser session cannot submit twice. The original cookie and browser string are not retained in these fields, but the hashes can still single out the same browser session; clearing your cookies starts a new session, so this prevents accidental double submission rather than a determined one. Because such a key exists, the data is pseudonymous rather than anonymous.</li>
</ul>
<h3>From baseline (Prolific) participants</h3>
<ul>
  <li><strong>Prolific participant ID</strong> — a quasi-identifier used to deduplicate responses and to honour withdrawal via Prolific.</li>
</ul>
<h3>From educators and administrators</h3>
<ul>
  <li><strong>E-mail address, display name</strong> — for backoffice sign-in.</li>
  <li><strong>Password</strong> — stored only as a bcrypt hash.</li>
  <li><strong>Class data</strong> — names, codes and configuration of classes you create.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the study and aggregate visualisations</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the educational programme in which participants take part.</li>
  <li><strong>Keeping a stripped research row after the class is erased</strong> — Art. 6(1)(a) GDPR, your separate, optional consent. The box is not pre-selected, declining changes nothing about the exercise, and you can withdraw at any time with your deletion code.</li>
  <li><strong>Educator and administrator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see aggregate counts and the pseudonymous response-level data for their own classes, plus aggregated comparison figures from the baseline sample. No stored field identifies a participant directly.</li>
  <li><strong>The administrator</strong> has technical access for maintenance, backups and security only, and is the only role that can open or export the raw baseline (Prolific) sample.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Class responses</strong> — erased automatically <strong>30 days</strong> after the class is closed, or 30 days after the last response if it is never closed. A class nobody ever joined is removed 90 days after it was created. Erasure removes the whole class: every response, the free-text answers, the optional demographics and the browser hashes. Educators are warned 14 days beforehand and may postpone up to three times by 30 days. The latest possible date is <strong>120 days after</strong> the class closed or the last response — 90 days beyond the original deletion date.</li>
  <li><strong>If you tick the optional research box</strong> — one row of yours is kept after that date: the experimental story version and factor levels, your choice, certainty, optional closed-choice follow-up, and any demographics you gave. <strong>Your free-text explanation is never copied.</strong> The row has no class code or class name and no date finer than the half-year. It does carry a new random cohort key shared by people who answered in the same class, so co-membership can be analysed without retaining which class it was. Those rows are <strong>pseudonymous, not anonymous</strong>: the deletion code you were given still matches yours, which is exactly what lets you withdraw it. If you do not tick it, nothing of yours survives the deadline.</li>
  <li><strong>Baseline (Prolific) responses</strong> — a one-time benchmark sample, collected as research from the outset with consent given through Prolific and retained as part of that dataset. It is not on the class clock above. The Prolific ID is held only for deduplication and for withdrawal through Prolific.</li>
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
            ("drawbridge_session", "Signed, HTTP-only session cookie: holds the anonymous session and CSRF value so your pass through the story stays consistent.", "4 hours", "participants"),
            ("drawbridge_progress", "Remembers how far you have read through the story, so returning to the page does not restart it (signed, HTTP-only). Cleared when you finish.", "4 hours", "participants"),
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
  <li><strong>Running the survey and the class debrief</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the educational programme in which participants take part.</li>
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
  <li><strong>After 30 days, what happens depends on your consent.</strong> In every case your name and e-mail address are removed, and the <strong>free-text reflection box is emptied for everyone</strong>. If you did <em>not</em> consent to research use, your demographic and reflection answers are <strong>deleted outright</strong> at the same moment. If you did consent, they are kept — but the record is <strong>cut loose from your class</strong>: the link to the session is removed and the timestamp is reduced to the month, so the answers sit in a large cross-class pool instead of a group of twenty where a combination of age, gender and income could point at one person.</li>
  <li><strong>What that means for you:</strong> once the 30 days have passed we can no longer find your individual response, so a withdrawal request has to reach us before then. Until then, write to us and we will delete it.</li>
  <li>This routine had been broken since the feature was written — the database rejected the deletion every time, and it only ran at start-up — and was repaired on 2026-07-30/31. A test now executes the deletion itself on every deploy rather than merely checking that the code exists.</li>
  <li><strong>Manual anonymisation:</strong> educators can anonymise or archive a session at any time before the 30-day window ends. Doing so applies exactly the steps described above, immediately — it is the same routine, not a lighter version of it.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>Within the first 30 days, ask your educator (who can delete
individual entries) or write to us naming the session and the name you used —
your entry can be found and removed. After 30 days the record has been
anonymised and, if you consented to research use, detached from your class, so
we genuinely cannot identify which row was yours. You can also withdraw a
consent you gave at any time by writing to us; that stops any further use,
though it cannot reach a record we can no longer locate.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement. A name or pseudonym is needed so your educator can see who has
responded. Everything on the demographics page is voluntary: every field
offers &ldquo;prefer not to say&rdquo;, the whole page can be skipped, and
neither consent box has to be ticked. Declining any of it does not affect your
results, the class discussion, or anything else.</p>""",
        },
        "provenance": {
            "en": """<p>The comparison data on real wealth distributions is drawn
from published public sources; the survey design and site are original works.</p>""",
        },
        "cookies": [
            ("survey_state", "Keeps your in-progress estimates as you move through the survey (signed, HTTP-only).", "2 hours", "participants"),
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
        "notice_version": "2026-08-b",
        "last_updated": "2026-08-19",
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
  <li><strong>Class code</strong> — groups participants by class.</li>
  <li><strong>Ranking decisions</strong> — your responses to the exercise.</li>
  <li><strong>Optional demographics</strong> — only the fields you choose to answer.</li>
  <li><strong>Submission timestamps.</strong></li>
</ul>
<h3>From educators</h3>
<ul>
  <li><strong>E-mail address</strong> — for backoffice sign-in.</li>
  <li><strong>Password</strong> — stored only as a bcrypt hash.</li>
  <li><strong>Class data</strong> — names, codes, configuration, responses.</li>
  <li><strong>An audit record of backoffice actions</strong> — the educator's e-mail address and the <strong>IP address</strong> an action came from, stored as database records. This is a security record: it is how an account compromise is reconstructed. Records are deleted after <strong>12 months</strong>.</li>
</ul>""",
            "de": """
<h3>Von Teilnehmenden</h3>
<ul>
  <li><strong>E-Mail-Adresse</strong> — erforderlich; identifiziert Ihre Abgabe und verhindert Doppel­abgaben.</li>
  <li><strong>Klassencode</strong> — ordnet Teilnehmende einer Klasse zu.</li>
  <li><strong>Reihungs­entscheidungen</strong> — Ihre Antworten in der Übung.</li>
  <li><strong>Freiwillige demografische Angaben</strong> — nur die Felder, die Sie ausfüllen.</li>
  <li><strong>Zeitstempel der Abgabe.</strong></li>
</ul>
<h3>Von Lehrenden</h3>
<ul>
  <li><strong>E-Mail-Adresse</strong> — für die Anmeldung im Backoffice.</li>
  <li><strong>Passwort</strong> — ausschließlich als bcrypt-Hash gespeichert.</li>
  <li><strong>Klassendaten</strong> — Namen, Codes, Konfiguration, Antworten.</li>
  <li><strong>Protokoll der Backoffice-Aktionen</strong> — die E-Mail-Adresse der Lehrperson und die <strong>IP-Adresse</strong>, von der eine Aktion ausging, als Datenbank­einträge gespeichert. Dies ist eine Sicherheitsaufzeichnung: Damit lässt sich eine Kontokompromittierung nachvollziehen. Die Einträge werden nach <strong>12 Monaten</strong> gelöscht.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the exercise and the class debrief</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the educational programme in which participants take part.</li>
  <li><strong>Educator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Durchführung der Übung und der Auswertung im Kurs</strong> — Art. 6 Abs. 1 lit. f DSGVO, unser berechtigtes Interesse an der Unterstützung des Bildungsprogramms, an dem die Teilnehmenden teilnehmen.</li>
  <li><strong>Konten von Lehrenden</strong> — Art. 6 Abs. 1 lit. b DSGVO.</li>
  <li><strong>Sicherheit, Rate-Limiting und Missbrauchs­abwehr</strong> — Art. 6 Abs. 1 lit. f DSGVO.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see the participants of their own classes (e-mail addresses) and the class's responses for the debrief. They can also open <strong>aggregate analytics across all classes</strong> — combined figures only, with small groups suppressed, never another class's individual responses or addresses.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Lehrende</strong> sehen die Teilnehmenden ihrer eigenen Klassen (E-Mail-Adressen) und die Antworten der Klasse für die Auswertung. Zusätzlich können sie <strong>aggregierte Auswertungen über alle Klassen hinweg</strong> aufrufen — ausschließlich zusammengefasste Werte, kleine Gruppen unterdrückt, niemals Einzelantworten oder Adressen einer anderen Klasse.</li>
  <li><strong>Der Administrator</strong> hat ausschließlich technischen Zugriff für Wartung und Sicherheit.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Automatic pseudonymisation:</strong> classes whose responses are older than 60 days are pseudonymised automatically (hourly check), whichever rounds the class ran. E-mail addresses are replaced by stable per-class labels; rankings, optional demographics, the class link and submission timestamps remain joined for aggregate analysis. These rows are <strong>not anonymous</strong>.</li>
  <li><strong>Educator-triggered pseudonymisation:</strong> educators are asked to pseudonymise a class as soon as the session is finished, and can do so at any time.</li>
  <li><strong>Backoffice audit log:</strong> kept as database records and deleted after <strong>12 months</strong>.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Automatische Pseudonymisierung:</strong> Klassen, deren Antworten älter als 60 Tage sind, werden automatisch pseudonymisiert (stündliche Prüfung) — unabhängig davon, welche Runden die Klasse durchlaufen hat. E-Mail-Adressen werden durch stabile, klassenbezogene Kennzeichnungen ersetzt; Reihungen, freiwillige demografische Angaben, Klassenzuordnung und Abgabezeitpunkte bleiben für aggregierte Auswertungen miteinander verknüpft. Diese Datensätze sind <strong>nicht anonym</strong>.</li>
  <li><strong>Pseudonymisierung durch Lehrende:</strong> Lehrende werden gebeten, eine Klasse unmittelbar nach der Sitzung zu pseudonymisieren, und können dies jederzeit tun.</li>
  <li><strong>Backoffice-Protokoll:</strong> als Datenbank­einträge gespeichert und nach <strong>12 Monaten</strong> gelöscht.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>Before pseudonymisation, write to us or to your educator naming
the e-mail address you used; the submission can be located and deleted. After
pseudonymisation the address is gone, so we can normally no longer identify
which stable per-class row was yours; the retained rows remain pseudonymous,
not anonymous.</p>""",
            "de": """<p>Vor der Pseudonymisierung schreiben Sie uns oder Ihrer Lehrperson
unter Angabe der verwendeten E-Mail-Adresse; die Abgabe kann gefunden und
gelöscht werden. Nach der Pseudonymisierung ist die Adresse gelöscht; daher
können wir in der Regel nicht mehr feststellen, welche stabile,
klassenbezogene Zeile zu Ihnen gehörte. Die gespeicherten Zeilen bleiben
pseudonym und sind nicht anonym.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement, but an e-mail address is technically required to take part (it
prevents duplicate submissions); without it a submission cannot be recorded.
Demographic fields are optional.</p>""",
            "de": """<p>Die Bereitstellung von Daten ist weder gesetzlich noch
vertraglich vorgeschrieben; eine E-Mail-Adresse ist jedoch technisch für die
Teilnahme erforderlich (sie verhindert Doppel­abgaben) — ohne sie kann keine
Abgabe gespeichert werden. Demografische Felder sind freiwillig.</p>""",
        },
        "provenance": {
            "en": """<p>The Layoff Exercise scenario, materials and site are
original works created for teaching.</p>""",
        },
        "cookies": [
            ("layoff_participant", "Carries your e-mail and class code between the exercise steps (signed, HTTP-only).", "30 minutes", "participants"),
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
            ('layoff_participant', 'Überträgt Ihre E-Mail-Adresse und den Kurscode zwischen den Schritten der Übung (signiert, HTTP-only).',
             '30 Minuten', 'Teilnehmende'),
            ('layoff_flash', 'Überträgt eine einmalige Statusmeldung von einer Seite zur nächsten.',
             '5 Minuten', 'alle'),
            ('layoff_admin', 'Hält Lehrpersonen und Administratoren angemeldet (signiert, HTTP-only).',
             '6 Stunden (Lehrpersonen) / 3 Stunden (Administratoren)', 'Backoffice'),
            ('lo_pending_totp / layoff_pending2fa', 'Überträgt den Zwischenschritt der Zwei-Faktor-Anmeldung: die Markierung der offenen Anmeldung (5 Minuten) und, während der Einrichtung, das noch nicht bestätigte TOTP-Geheimnis (15 Minuten).',
             '5–15 Minuten', 'Backoffice'),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "lsr": {
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
        "notice_version": "2026-08-c",
        "last_updated": "2026-08-19",
        "art9": False,  # leadership-style point allocations
        "purpose": {
            "en": "The Polarity Profiler collects scenario-based point allocations and "
                  "produces a personal leadership-style repertoire report, with an "
                  "optional class comparison, for use in executive education.",
            "de": "Der Polarity Profiler erhebt szenariobasierte Punktverteilungen und "
                  "erstellt einen persönlichen Bericht zum Führungsstil-Repertoire, "
                  "mit optionalem Klassenvergleich, für die Führungskräfte­bildung.",
        },
        "collect": {
            "en": """
<h3>From participants</h3>
<ul>
  <li><strong>E-mail address</strong> — <strong>required</strong> to take part. It is used to send your PDF report, to include you in the class comparison, and to give you a withdrawal link.</li>
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
  <li><strong>Class data</strong> — names and codes of classes you create.</li>
</ul>""",
            "de": """
<h3>Von Teilnehmenden</h3>
<ul>
  <li><strong>E-Mail-Adresse</strong> — <strong>erforderlich</strong> für die Teilnahme. Sie wird verwendet, um Ihnen Ihren PDF-Bericht zu senden, Sie in den Klassenvergleich einzubeziehen und Ihnen einen Widerrufslink bereitzustellen.</li>
  <li><strong>Fragebogen­antworten</strong> — Punktverteilungen, Kontextantworten, abgeleitete Stilwerte.</li>
  <li><strong>Freiwillige demografische Angaben</strong> — nur Felder, die Sie ausfüllen; ausschließlich für aggregierte Auswertungen.</li>
  <li><strong>Zeitstempel der Abgabe.</strong></li>
  <li><strong>Zwei Zugangs-Token</strong> — eines öffnet den Link zu Ihrem Bericht, eines den Link zum Widerruf. Sie sind es, die diese Links ohne Passwort funktionieren lassen; wer einen Link hat, kann ihn verwenden — behandeln Sie sie daher vertraulich.</li>
  <li><strong>Ein Nachweis darüber, was Ihnen gezeigt wurde und wie Sie entschieden haben</strong> — wann Sie diesen Hinweis zur Kenntnis genommen haben und, falls Sie die Forschungsfrage auf Ihrer Ergebnisseite beantwortet haben, Ihre Antwort mit Datum und der Version des Wortlauts, den Sie gesehen haben. So können wir belegen, worin Sie eingewilligt haben — das verlangt das Gesetz von uns.</li>
</ul>
<h3>Von Lehrenden und Administratoren</h3>
<ul>
  <li><strong>E-Mail-Adresse</strong> — für die Anmeldung im Backoffice.</li>
  <li><strong>Passwort</strong> — ausschließlich als bcrypt-Hash gespeichert.</li>
  <li><strong>Klassendaten</strong> — Namen und Codes der von Ihnen angelegten Klassen.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the profiler, generating the class aggregate, sending the PDF report</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the executive-education programme in which participants are enrolled.</li>
  <li><strong>Research and cross-class benchmark use</strong> — your consent (Art. 6(1)(a)), offered on your results page once you have seen what your answers produced. It is entirely optional and separate from taking part: declining changes nothing about your report or your place in the class comparison, and you can give or withdraw it at any time from that page. The tick-box on the first page is a different thing — it confirms you have read this notice, and is not a consent to research use.</li>
  <li><strong>Educator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Durchführung des Profilers, Klassen­aggregat, Versand des PDF-Berichts</strong> — Art. 6 Abs. 1 lit. f DSGVO, unser berechtigtes Interesse an der Unterstützung des Weiterbildungs­programms, in dem die Teilnehmenden eingeschrieben sind.</li>
  <li><strong>Forschungs- und klassen­übergreifende Benchmark-Nutzung</strong> — Ihre Einwilligung (Art. 6 Abs. 1 lit. a DSGVO), die Ihnen auf Ihrer Ergebnisseite angeboten wird, nachdem Sie gesehen haben, was Ihre Antworten ergeben. Sie ist vollkommen freiwillig und von der Teilnahme unabhängig: Eine Ablehnung ändert nichts an Ihrem Bericht oder Ihrem Platz im Klassenvergleich, und Sie können sie dort jederzeit erteilen oder widerrufen. Das Kästchen auf der ersten Seite ist etwas anderes — es bestätigt, dass Sie diese Erklärung gelesen haben, und ist keine Einwilligung in die Forschungsnutzung.</li>
  <li><strong>Konten von Lehrenden</strong> — Art. 6 Abs. 1 lit. b DSGVO.</li>
  <li><strong>Sicherheit, Rate-Limiting und Missbrauchs­abwehr</strong> — Art. 6 Abs. 1 lit. f DSGVO.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see a completion list for their class (e-mail address and submission time). They do not see individual scores.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Lehrende</strong> sehen eine Abgabeliste ihrer Klasse (E-Mail-Adresse und Abgabezeitpunkt). Individuelle Ergebnisse sehen sie nicht.</li>
  <li><strong>Der Administrator</strong> hat ausschließlich technischen Zugriff für Wartung und Sicherheit.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Live-class mode:</strong> report access and withdrawal expire 14 days after the class is closed; educators can postpone this in limited 7-day steps. At that deadline your e-mail address, name, withdrawal token and class linkage are removed. What happens to the answers themselves depends on the research choice on your results page: <strong>if you consented</strong>, the pseudonymised answers, scores and demographics are kept for aggregate analysis and research; <strong>if you did not</strong>, the entire response — answers, scores and demographics — is deleted at that deadline. Not choosing counts as not consenting.</li>
  <li><strong>Self-guided mode:</strong> the same 14-day window, counted from submission.</li>
  <li><strong>Responses anonymised before 1 August 2026:</strong> the research choice above only became reachable on 31 July 2026 — before that the control existed but nothing in the interface called it, so nobody could give or decline it. Responses already anonymised at that point were kept in pseudonymised form under the older rule and are <strong>not</strong> retrospectively deleted. They carry no e-mail address, name, withdrawal token or class link. If you took part before that date and want yours removed, write to us and we will delete the whole set for the period you name.</li>
  <li><strong>Educator accounts:</strong> retained until deleted by the administrator.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Kursmodus:</strong> Berichtszugriff und Widerruf enden 14 Tage nach Schließung der Klasse; Lehrende können dies in begrenzten 7-Tage-Schritten aufschieben. Zu diesem Stichtag werden E-Mail-Adresse, Name, Widerrufstoken und Klassenzuordnung entfernt. Was mit den Antworten selbst geschieht, hängt von der Forschungs-Entscheidung auf Ihrer Ergebnisseite ab: <strong>Haben Sie eingewilligt</strong>, bleiben die pseudonymisierten Antworten, Werte und demografischen Angaben für aggregierte Auswertungen und Forschung erhalten; <strong>haben Sie nicht eingewilligt</strong>, wird die gesamte Antwort — Antworten, Werte und demografische Angaben — zu diesem Stichtag gelöscht. Keine Entscheidung zu treffen gilt als Nicht-Einwilligung.</li>
  <li><strong>Selbststudium:</strong> dieselbe 14-Tage-Frist, gerechnet ab der Abgabe.</li>
  <li><strong>Vor dem 1. August 2026 anonymisierte Antworten:</strong> Die oben beschriebene Forschungs-Entscheidung war erst ab dem 31. Juli 2026 erreichbar — zuvor existierte die Funktion, wurde aber von der Oberfläche nie aufgerufen, sodass niemand einwilligen oder ablehnen konnte. Zu diesem Zeitpunkt bereits anonymisierte Antworten wurden nach der früheren Regel in pseudonymisierter Form aufbewahrt und werden <strong>nicht</strong> rückwirkend gelöscht. Sie enthalten weder E-Mail-Adresse noch Namen, Widerrufstoken oder Kurszuordnung. Wenn Sie vor diesem Datum teilgenommen haben und Ihre Daten entfernt haben möchten, schreiben Sie uns; wir löschen dann den gesamten Bestand des von Ihnen genannten Zeitraums.</li>
  <li><strong>Konten von Lehrenden:</strong> bis zur Löschung durch den Administrator.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>Use the withdrawal link in your confirmation e-mail or on
your report page — it works without a login, any time before the anonymisation
deadline, and deletes your response including demographics. After the deadline
no identifier linking a response to you remains.</p>""",
            "de": """<p>Nutzen Sie den Widerrufslink in Ihrer Bestätigungs-E-Mail
oder auf Ihrer Berichtsseite — er funktioniert ohne Anmeldung, jederzeit vor dem
Anonymisierungs­stichtag, und löscht Ihre Antwort einschließlich der
demografischen Angaben. Nach dem Stichtag verbleibt kein Kennzeichen, das eine
Antwort mit Ihnen verknüpft.</p>""",
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
            ("participant_session", "Keeps your progress through the questionnaire (signed, HTTP-only).", "2 hours", "participants"),
            ("repertoire_answers / scenario_answers / context_answers / demographics_data", "Carry your in-progress answers from page to page so you do not lose them mid-questionnaire (HTTP-only; held in your browser, not signed).", "2 hours", "participants"),
            ("response_id / withdrawal_raw", "Your submission reference and your withdrawal link, so the results page can offer withdrawal (signed, HTTP-only).", "2 hours", "participants"),
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
            ('participant_session', 'Bewahrt Ihren Fortschritt im Fragebogen (signiert, HTTP-only).',
             '2 Stunden', 'Teilnehmende'),
            ('repertoire_answers / scenario_answers / context_answers / demographics_data', 'Übertragen Ihre begonnenen Antworten von Seite zu Seite, damit sie mitten im Fragebogen nicht verloren gehen (HTTP-only; in Ihrem Browser gespeichert, nicht signiert).',
             '2 Stunden', 'Teilnehmende'),
            ('response_id / withdrawal_raw', 'Ihre Einreichungs-Referenz und Ihr Widerrufslink, damit die Ergebnisseite den Widerruf anbieten kann (signiert, HTTP-only).',
             '2 Stunden', 'Teilnehmende'),
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
        "notice_version": "2026-08-b",
        "last_updated": "2026-08-19",
        "art9": True,  # moral judgments
        "purpose": {
            "en": "Moral Mirror lets a class observe patterns in its own moral "
                  "judgment: participants answer short ethical questions and the "
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
  <li><strong>A class code</strong> — attaches responses to the correct session, not to you.</li>
  <li><strong>A pseudonymous session token</strong> in a cookie, so your answers within one session hang together. Because such a token exists, the data is pseudonymous rather than anonymous.</li>
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
  <li><strong>Running the activity and showing group results</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the class in which participants take part.</li>
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
  <li><strong>Class-level figures</strong> — when an educator closes a session, its answers are added to cross-session benchmarks as <strong>counts only</strong>. Those counts contain no participant records and are not affected by the deletion above; they cannot be traced to a session or a person.</li>
  <li><strong>Educator accounts</strong> — retained until deleted.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>We store no name or e-mail address, so we usually cannot
locate a specific response after the fact. Within the lifetime of your session
cookie your submission can still be identified via the session token — contact
us promptly from the same browser session and we will delete it. Educators can
delete whole sessions at any time.</p>""",
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
            ("moralmirror_pax", "Pseudonymous session token: keeps your answers within one session together (signed, HTTP-only).", "24 hours", "participants"),
            ("moralmirror_admin", "Keeps educators and administrators signed in (signed, HTTP-only).", "6 hours (educators) / 3 hours (administrators)", "backoffice"),
            ("mm_pending_totp / moralmirror_pending2fa", "Carries the intermediate step of two-factor sign-in: the pending-login marker (5 minutes) and, while you are enrolling, the not-yet-confirmed TOTP secret (15 minutes).", "5-15 minutes", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "orgsim": {
        "domain": "orgdesignsim.org",
        "tool_name": "OrgDesignSim",
        "languages": ["en"],
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
  <li><strong>E-mail address</strong> — required to enter a simulation session.</li>
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
  <li><strong>An audit record of backoffice actions</strong> — which account did what (creating, editing, closing, archiving or deleting a scenario), when, and the <strong>IP address</strong> it came from. This is a security record: it is how an account compromise or an accidental deletion is reconstructed. It is kept for <strong>12 months</strong> and then deleted automatically.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the simulation and the class debrief</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the educational programme in which participants take part.</li>
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
  <li><strong>Abandoned sessions</strong> are deleted automatically by an hourly job.</li>
  <li><strong>Completed sessions</strong> are anonymised automatically 90 days after completion — the personal identifiers are removed; the score is kept for educator statistics.</li>
  <li><strong>Login sessions</strong> expire automatically after 24 hours.</li>
  <li><strong>The backoffice audit record</strong> (educator account, action and IP address) is deleted automatically after <strong>12 months</strong>, by the same hourly job.</li>
  <li><strong>Educators</strong> can delete or archive a session at any time.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>Before anonymisation, write to us or to your educator naming
the e-mail address you joined with; your run can be located and deleted. After
anonymisation, results are no longer linked to a person.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement, but an e-mail address is technically required to join a session;
without it you cannot take part. The display name is optional.</p>""",
        },
        "provenance": {
            "en": """<p>The OrgDesignSim scenario, simulation model and site are
original works created for teaching organisational design.</p>""",
        },
        "cookies": [
            ("orgdesignsim_participant", "Keeps your simulation session while you play (signed, HTTP-only).", "24 hours", "participants"),
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
  <li><strong>Fleet overview (administration area only)</strong> — when a signed-in administrator opens the overview, this site queries each tool over the server's own loopback interface and displays that tool's class/session titles, join codes, the <strong>educator e-mail address</strong> that owns each one, its status, response count and last activity. This data is read live and shown on screen; the hub does not store it.</li>
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
are shown there — class titles, join codes, counts and the owning educator's
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
        "notice_version": "2026-08-j",
        "last_updated": "2026-08-19",
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
  <li><strong>E-mail address</strong> — <strong>required</strong> to join a session. It is stored with your ranking and is visible to your educator in the session's participant list. <strong>We send mail to it in exactly two cases:</strong> if someone tries to rejoin your session with your address from a device that is not already signed in, we send a one-time link so that only you can continue; and seven days before the class is erased we send you one notice with your personal withdrawal link. There is no newsletter and no other use.</li>
  <li><strong>Your consent, as a record</strong> — that you ticked the box to take part, whether you ticked the separate research box, when, and which version of this notice and of the consent wording you were shown. We keep it because we have to be able to show that consent was actually given (Art. 7(1)).</li>
  <li><strong>A pseudonymous session token</strong> in a cookie, linking your responses within one session.</li>
  <li><strong>Session code</strong> — attributes your response to the correct group session.</li>
  <li><strong>Your item rankings</strong> — individual and, where applicable, the group ranking.</li>
    <li><strong>Submission timestamp.</strong></li>
  <li><strong>Your prediction</strong> — when you send your ranking you are asked, in one click, how you think it will compare with the rest of the class. It is <strong>required</strong>: the gap between what a class expected and what happened is part of what the exercise teaches. It is stored with your ranking and shown to your educator as class totals and as one unnamed point per person on a chart of predictions against results — never labelled with your name. In a small class, an educator who can see everyone's score could work out which point is yours.</li>
  <li><strong>How often you are outdoors in winter</strong> — asked on the same screen and <strong>optional</strong>; "prefer not to say" is preselected. If you answer, the answer is stored with your response — on the same record as your e-mail address, like your ranking, <strong>not</strong> behind the demographics consent described below. Your educator sees it only as averages over at least five people, never next to your name, and it is not part of the data export.</li>
  <li><strong>Closing questions, in sessions that include them</strong> — some sessions end a group round with two short private questions: which considerations came up in your group's discussion, and what happened to what you yourself knew. <strong>Required in those sessions</strong>, stored with your response, and shown to your educator only in combined form — per group as majority counts, and the self-descriptions only as totals over at least five people. If you gave the separate research consent, these answers are among those kept beyond the class; <strong>the group's written reason for its decision is not kept</strong>, because free text can contain anything and no consent can cover what nobody can predict.</li>
  <li><strong>What your group had decided, in sessions with the optional second round</strong> — before the second round's material is shown, you are asked privately what your group had explicitly agreed to do in the situation: stay, leave, split the group, no agreement, or not discussed as a separate question. <strong>Required in those sessions</strong>, stored with your response, shown to your educator only as counts per group — never next to your name — deleted with the class, and <strong>not</strong> part of the research data.</li>
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
  <li><strong>E-Mail-Adresse</strong> — <strong>erforderlich</strong>, um an einer Sitzung teilzunehmen. Sie wird zusammen mit Ihrer Reihung gespeichert und ist für die moderierende Person in der Teilnehmendenliste sichtbar. <strong>In genau zwei Fällen senden wir eine Nachricht an diese Adresse:</strong> Versucht jemand, mit Ihrer Adresse von einem nicht angemeldeten Gerät aus wieder einzusteigen, schicken wir einen einmalig gültigen Link, damit nur Sie fortfahren können; und sieben Tage vor der Löschung des Kurses senden wir Ihnen eine Nachricht mit Ihrem persönlichen Widerrufslink. Es gibt keinen Newsletter und keine weitere Verwendung.</li>
  <li><strong>Ihre Einwilligung als Nachweis</strong> — dass Sie das Kästchen zur Teilnahme angekreuzt haben, ob Sie das gesonderte Forschungskästchen angekreuzt haben, wann, und welche Fassung dieser Erklärung und des Einwilligungstextes Ihnen angezeigt wurde. Wir speichern das, weil wir nachweisen können müssen, dass eine Einwilligung tatsächlich erteilt wurde (Art. 7 Abs. 1).</li>
  <li><strong>Ein pseudonymes Sitzungstoken</strong> in einem Cookie, das Ihre Antworten innerhalb einer Sitzung verknüpft.</li>
  <li><strong>Sitzungscode</strong> — ordnet Ihre Antwort der richtigen Gruppensitzung zu.</li>
  <li><strong>Ihre Reihungen</strong> — individuell und ggf. die Gruppenreihung.</li>
    <li><strong>Zeitstempel der Abgabe.</strong></li>
  <li><strong>Ihre Einschätzung</strong> — beim Absenden Ihrer Reihung werden Sie mit einem Klick gefragt, wie diese im Vergleich zum Rest des Kurses abschneiden wird. Diese Angabe ist <strong>erforderlich</strong>: der Abstand zwischen Erwartung und Ergebnis gehört zum Lernziel der Übung. Sie wird zusammen mit Ihrer Reihung gespeichert und der Lehrperson als Gesamtwert für den Kurs sowie als je ein unbeschrifteter Punkt pro Person in einem Diagramm angezeigt, das Einschätzungen und Ergebnisse gegenüberstellt — nie mit Ihrem Namen beschriftet. In einer kleinen Klasse könnte eine Lehrperson, die alle Punktzahlen sieht, allerdings erschließen, welcher Punkt Ihrer ist.</li>
  <li><strong>Wie oft Sie im Winter draußen sind</strong> — auf demselben Bildschirm gefragt und <strong>freiwillig</strong>; „keine Angabe“ ist voreingestellt. Wenn Sie antworten, wird die Angabe zusammen mit Ihrer Antwort gespeichert — im selben Datensatz wie Ihre E-Mail-Adresse, wie Ihre Reihung, <strong>nicht</strong> hinter der unten beschriebenen Einwilligung für demografische Angaben. Die moderierende Person sieht sie ausschließlich als Durchschnittswerte über mindestens fünf Personen, nie neben Ihrem Namen; im Datenexport ist sie nicht enthalten.</li>
  <li><strong>Abschlussfragen, in Sessions, die sie enthalten</strong> — manche Sessions beenden eine Gruppenrunde mit zwei kurzen privaten Fragen: welche Überlegungen in der Diskussion Ihrer Gruppe zur Sprache kamen, und was mit dem geschah, was Sie selbst wussten. In diesen Sessions <strong>erforderlich</strong>; gespeichert mit Ihrer Antwort und der Lehrperson ausschließlich zusammengefasst angezeigt — je Gruppe als Mehrheitszählung, die Selbstauskünfte nur als Summen über mindestens fünf Personen. Wenn Sie die gesonderte Forschungseinwilligung erteilt haben, gehören diese Antworten zu den über den Kurs hinaus aufbewahrten; <strong>die schriftliche Begründung der Gruppe wird nicht aufbewahrt</strong>, weil Freitext alles enthalten kann und keine Einwilligung abdecken kann, was niemand vorhersehen kann.</li>
  <li><strong>Was Ihre Gruppe entschieden hatte, in Sessions mit der optionalen zweiten Runde</strong> — bevor das Material der zweiten Runde angezeigt wird, werden Sie privat gefragt, was Ihre Gruppe in der Situation ausdrücklich vereinbart hatte: bleiben, aufbrechen, die Gruppe aufteilen, keine Einigung, oder nicht als eigene Frage besprochen. In diesen Sessions <strong>erforderlich</strong>; gespeichert mit Ihrer Antwort, der Lehrperson ausschließlich als Zählung je Gruppe angezeigt — nie neben Ihrem Namen — mit dem Kurs gelöscht und <strong>nicht</strong> Teil der Forschungsdaten.</li>
  <li><strong>Freiwillige demografische Angaben</strong> — Altersgruppe, Geschlecht, Jahre Berufserfahrung, Erfahrung in der Teamleitung, Studien- oder Tätigkeitsfeld sowie Land. <strong>Jede dieser Angaben ist freiwillig, die gesamte Seite kann übersprungen werden, und ohne Ihr angekreuztes Einverständnis wird nichts gespeichert.</strong> Der moderierenden Person werden sie ausschließlich als Gruppendurchschnitte angezeigt, und nie für Gruppen mit weniger als fünf Personen. Ihre Länderangabe wird zusätzlich zu einer Weltregion zusammengefasst angezeigt. Wir erfassen, wann Sie eingewilligt haben und welche Fassung dieser Erklärung und des Einwilligungstextes Ihnen angezeigt wurde.</li>
</ul>
<h3>Von Moderierenden</h3>
<ul>
  <li><strong>Anmeldedaten</strong> — das Passwort wird ausschließlich als bcrypt-Hash gespeichert.</li>
  <li><strong>Sitzungsdaten</strong> — Namen, Codes und Konfiguration der von Ihnen angelegten Sitzungen.</li>
</ul>""",
        },
        "basis": {
            "en": """
<ul>
  <li><strong>Running the exercise and producing group results</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the educational programme in which participants take part.</li>
  <li><strong>Optional demographics</strong> — Art. 6(1)(a) GDPR, your consent. You give it by ticking a box that is not ticked for you, you can skip the page entirely without any effect on the exercise, and you may withdraw it at any time by writing to us, after which the answers are deleted.</li>
  <li><strong>Keeping your answers beyond the class, for research and teaching</strong> — Art. 6(1)(a) GDPR, your separate consent, with the safeguards of Art. 89(1). It is a second box, also not ticked for you, on the same screen as the first. <strong>Leaving it unticked changes nothing about taking part</strong>: you are grouped, you see your results, and everything of yours is simply erased with the rest of the class. Ticking it means one row is kept after the class is erased — see "How long we keep data" — and you can withdraw that consent at any time, with no deadline, using the link we e-mail you before the class is erased.</li>
  <li><strong>Educator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Durchführung der Übung und Erstellung der Gruppenergebnisse</strong> — Art. 6 Abs. 1 lit. f DSGVO, unser berechtigtes Interesse an der Unterstützung des Bildungsprogramms, an dem die Teilnehmenden teilnehmen.</li>
  <li><strong>Freiwillige demografische Angaben</strong> — Art. 6 Abs. 1 lit. a DSGVO, Ihre Einwilligung. Sie erteilen sie durch Ankreuzen eines nicht vorausgewählten Kästchens, Sie können die Seite folgenlos überspringen und Ihre Einwilligung jederzeit widerrufen; die Angaben werden dann gelöscht.</li>
  <li><strong>Aufbewahrung Ihrer Antworten über den Kurs hinaus, für Forschung und Lehre</strong> — Art. 6 Abs. 1 lit. a DSGVO, Ihre gesonderte Einwilligung, mit den Garantien des Art. 89 Abs. 1. Es ist ein zweites, ebenfalls nicht vorausgewähltes Kästchen auf demselben Bildschirm wie das erste. <strong>Bleibt es leer, ändert das nichts an Ihrer Teilnahme</strong>: Sie werden einer Gruppe zugeordnet, sehen Ihre Ergebnisse, und alles von Ihnen wird zusammen mit dem übrigen Kurs gelöscht. Kreuzen Sie es an, bleibt bei der Löschung des Kurses ein Datensatz erhalten — siehe „Wie lange wir Daten speichern“ — und Sie können diese Einwilligung jederzeit und ohne Frist widerrufen, über den Link, den wir Ihnen vor der Löschung des Kurses zusenden.</li>
  <li><strong>Konten von Moderierenden</strong> — Art. 6 Abs. 1 lit. b DSGVO.</li>
  <li><strong>Sicherheit, Rate-Limiting und Missbrauchs­abwehr</strong> — Art. 6 Abs. 1 lit. f DSGVO.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see, for their own sessions, the participant list <strong>including each participant's e-mail address</strong>, alongside the individual and group rankings. Demographics are shown to them <strong>only as averages over at least five people</strong> — never next to a name. Answers given by fewer than five people are not shown separately; they are either withheld or combined with other rare answers into a single "everyone else" figure that also covers at least five people.</li>
  <li><strong>Your class</strong> may be shown those same demographic averages during the debrief, and they may be included in a written summary your educator hands out afterwards. That is part of the discussion the answers are collected for. The five-person floor and the "everyone else" pooling apply exactly as above, so nothing is shown that stands for fewer than five people — but be aware that <strong>five people in a room where everyone knows each other are not anonymous in the way five strangers would be</strong>. If you would rather your answers were not part of that, skip the questions, or ask your educator to delete them.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Moderierende</strong> sehen für ihre eigenen Sitzungen die Teilnehmendenliste <strong>einschließlich der E-Mail-Adressen</strong> sowie die individuellen und die Gruppenreihungen. Demografische Angaben sehen sie <strong>ausschließlich als Durchschnittswerte über mindestens fünf Personen</strong> — nie neben einem Namen. Antworten, die weniger als fünf Personen gegeben haben, werden nicht einzeln ausgewiesen; sie werden entweder zurückgehalten oder mit anderen seltenen Antworten zu einem einzigen Wert „alle Übrigen“ zusammengefasst, der ebenfalls mindestens fünf Personen umfasst.</li>
  <li><strong>Ihr Kurs</strong> bekommt diese demografischen Durchschnittswerte unter Umständen ebenfalls zu sehen, und sie können in einer schriftlichen Zusammenfassung enthalten sein, die Ihre Lehrperson im Anschluss austeilt. Das ist Teil der Auswertung, für die die Angaben erhoben werden. Die Fünf-Personen-Grenze und die Zusammenfassung zu „alle Übrigen“ gelten dabei unverändert, es wird also nichts angezeigt, was für weniger als fünf Personen steht — bedenken Sie aber, dass <strong>eine Gruppe von fünf Personen in einem Raum, in dem man sich kennt, nicht in demselben Sinne anonym ist wie fünf Fremde</strong>. Wenn Sie das nicht möchten, überspringen Sie die Fragen oder bitten Sie Ihre Lehrperson, Ihre Angaben zu löschen.</li>
  <li><strong>Der Administrator</strong> hat ausschließlich technischen Zugriff für Wartung und Sicherheit.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Everything from a class is erased 30 days after the session finishes.</strong> That means your e-mail address, your ranking, your group, your votes, the boards, the results page and the session itself. It runs automatically, it cannot be undone, and it is the same date for everyone in the class. A session that is never finished is erased 30 days after its last submission instead; a session nobody ever joined is deleted 90 days after it was created.</li>
  <li><strong>Your educator can postpone that date by 30 days, up to three times</strong> — never further, and never earlier than a date you have already been told. They are warned 14 days before, and if the date is still approaching, <strong>you are e-mailed 7 days before</strong> so you can withdraw first. That is the only such message you get for a class.</li>
  <li><strong>If you gave the separate research consent</strong>, one row of yours is kept when the class is erased, and kept indefinitely: your ranking, your score, your group's result, your optional answers about yourself, your answers to the closing round in sessions that include one, and the half-year it happened in. <strong>Nothing is kept from anyone who did not tick that box</strong> — their answers are deleted with the class and never counted. It carries no e-mail address, no name, no class, no group name and no date more precise than the half-year, and the link between it and you is destroyed with the class. It is not anonymous — a ranking plus several bands can still be rare — so we treat it as personal data throughout, keep it only for research and teaching, and never publish anything that stands for fewer than five people. <strong>You can withdraw it at any time, with no time limit</strong>, using the link in that 7-day e-mail.</li>
  <li><strong>Educator accounts</strong> — retained until deactivated or deleted by an administrator.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Alles aus einem Kurs wird 30 Tage nach dessen Abschluss gelöscht.</strong> Das umfasst Ihre E-Mail-Adresse, Ihre Reihung, Ihre Gruppe, Ihre Stimmen, die Gruppentafeln, die Ergebnisseite und die Sitzung selbst. Das geschieht automatisch, ist nicht rückgängig zu machen und gilt für alle im Kurs zum selben Datum. Eine nie abgeschlossene Sitzung wird stattdessen 30 Tage nach der letzten Abgabe gelöscht; eine Sitzung, der nie jemand beigetreten ist, 90 Tage nach ihrer Erstellung.</li>
  <li><strong>Ihre Lehrperson kann dieses Datum um jeweils 30 Tage verschieben, höchstens dreimal</strong> — nicht weiter und nie auf ein früheres als das Ihnen bereits genannte Datum. Sie wird 14 Tage vorher benachrichtigt; steht das Datum dann weiterhin bevor, <strong>erhalten Sie 7 Tage vorher eine E-Mail</strong>, damit Sie vorher widerrufen können. Es ist die einzige Nachricht dieser Art zu einem Kurs.</li>
  <li><strong>Wenn Sie die gesonderte Forschungseinwilligung erteilt haben</strong>, bleibt bei der Löschung des Kurses ein Datensatz von Ihnen erhalten, und zwar unbefristet: Ihre Reihung, Ihr Ergebnis, das Ergebnis Ihrer Gruppe, Ihre freiwilligen Angaben zur Person, in Sitzungen mit Abschlussrunde Ihre Antworten darin, sowie das Halbjahr. <strong>Von Personen ohne dieses Häkchen wird nichts aufbewahrt</strong> — ihre Antworten werden mit dem Kurs gelöscht und niemals gezählt. Er enthält keine E-Mail-Adresse, keinen Namen, keinen Kurs, keinen Gruppennamen und kein Datum genauer als das Halbjahr; die Verbindung zwischen ihm und Ihnen wird mit dem Kurs vernichtet. Er ist nicht anonym — eine Reihung zusammen mit mehreren Angaben kann selten sein —, deshalb behandeln wir ihn durchgehend als personenbezogenes Datum, verwenden ihn nur für Forschung und Lehre und veröffentlichen nichts, was für weniger als fünf Personen steht. <strong>Sie können ihn jederzeit und ohne Frist widerrufen</strong>, über den Link in dieser E-Mail nach 7 Tagen.</li>
  <li><strong>Konten von Moderierenden</strong> — bis zur Deaktivierung oder Löschung durch einen Administrator.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p><strong>While the class still exists</strong> your e-mail
address identifies your submission, so we can always find and delete it: write
to us, or ask your educator, naming the session code and the address you
joined with. Educators can delete a single participant's response, or a whole
session, at any time. If you gave optional demographics, withdrawing that
consent deletes those answers and nothing else — the exercise results are
unaffected.</p>
<p><strong>After the class is erased</strong> there is nothing of yours left to
find unless you gave the separate research consent. That row we cannot find
either — by design, it carries no address and nothing linking it to you — so it
can only be reached with the personal link in the e-mail we send you seven days
before the class is erased. <strong>Keep that e-mail.</strong> Opening the link
shows you what would be removed and removes nothing until you confirm; use it
before the deadline and it deletes your class answers as well. There is no time
limit on it.</p>""",
            "de": """<p><strong>Solange der Kurs besteht</strong>, identifiziert
Ihre E-Mail-Adresse Ihre Abgabe, wir können sie also jederzeit finden und
löschen: Schreiben Sie uns oder Ihrer moderierenden Person unter Angabe des
Sitzungscodes und der verwendeten Adresse. Moderierende können einzelne
Antworten oder ganze Sitzungen jederzeit löschen. Wenn Sie freiwillige
demografische Angaben gemacht haben, führt der Widerruf dieser Einwilligung
ausschließlich zur Löschung dieser Angaben; die Übungsergebnisse bleiben davon
unberührt.</p>
<p><strong>Nach der Löschung des Kurses</strong> ist von Ihnen nichts mehr
vorhanden — es sei denn, Sie haben die gesonderte Forschungseinwilligung
erteilt. Diesen Datensatz können auch wir nicht finden: Er enthält
absichtsvoll keine Adresse und nichts, was ihn mit Ihnen verbindet. Erreichbar
ist er ausschließlich über den persönlichen Link in der E-Mail, die wir Ihnen
sieben Tage vor der Löschung des Kurses senden. <strong>Bewahren Sie diese
E-Mail auf.</strong> Der Link zeigt Ihnen zunächst, was gelöscht würde, und
löscht nichts, bevor Sie bestätigen; vor dem Stichtag verwendet, löscht er auch
Ihre Kursantworten. Eine Frist gibt es dafür nicht.</p>""",
        },
        "provision": {
            "en": """<p>Providing data is neither a statutory nor a contractual
requirement, but an e-mail address is <strong>technically required</strong> to
join a session — without it a submission cannot be recorded.</p>""",
            "de": """<p>Die Bereitstellung von Daten ist weder gesetzlich noch
vertraglich vorgeschrieben; eine E-Mail-Adresse ist jedoch <strong>technisch
erforderlich</strong>, um an einer Sitzung teilzunehmen — ohne sie kann keine
Abgabe gespeichert werden.</p>""",
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
