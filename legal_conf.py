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
  whiteout     no job — facilitator-deleted (stated as such)

CORRECTION 2026-07-30 (second pass, after an external review). The first pass
checked retention claims against the code but NOT the "what we collect" claims,
and that is exactly where the false statements were:

  whiteout    the notice said no name/e-mail was collected. /join REQUIRES an
              e-mail, stores it on participants.email, and shows it to the
              facilitator. Corrected.
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

# Version stamp shown on every legal document, fleet-wide. Bump the version
# when wording changes substantively; git is the audit trail for the text.
NOTICE_VERSION = "2026-07"
LAST_UPDATED = "2026-07-30"

# nginx logs to /var/log/nginx/access.log, logrotate: daily, rotate 14.
# Verified on the server 2026-07-30. If the rotation policy changes, change it
# THERE and HERE together.
LOG_RETENTION_DAYS = 14

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
  <li><strong>Running the survey and pairing discussion partners</strong> — Art. 6(1)(f) GDPR, our legitimate interest in supporting the educational programme in which participants take part.</li>
  <li><strong>Educator and administrator accounts</strong> — Art. 6(1)(b) GDPR, performance of the arrangement under which the account was created.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR, our legitimate interest in operating the service securely.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see participant names, e-mail addresses (where provided) and responses for their own surveys only.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security purposes only.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Automatic anonymisation:</strong> surveys older than 12 months are anonymised automatically — names and e-mail addresses are removed; numerical responses are kept for aggregate analysis. A daily job enforces this.</li>
  <li><strong>Educator reminders:</strong> educators are prompted to review surveys inactive for 30 days or more.</li>
  <li><strong>Manual deletion:</strong> educators and administrators can delete whole surveys or individual submissions at any time.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>Within a short window after submitting you can withdraw your
response yourself using the withdrawal option on your confirmation page. After
that, contact your educator (who can delete individual submissions) or write to
us. Once a survey has been anonymised, responses are no longer linked to a
person and can no longer be individually located.</p>""",
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
            ("backoffice_user", "Keeps educators and administrators signed in (signed, HTTP-only).", "4 hours", "backoffice"),
            ("cg_pending_totp", "Carries the intermediate step of two-factor sign-in.", "5 minutes", "backoffice"),
            ("dismiss_anonymize_until", "Remembers that an educator dismissed the \"these surveys need anonymising\" reminder, so it is not shown again for a week. Set only when the educator clicks dismiss.", "7 days", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "drawbridge": {
        "domain": "drawbridge-drama.org",
        "tool_name": "The Drawbridge Drama",
        "languages": ["en"],
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
  <li><strong>Your responses</strong> — your responsibility attribution, certainty rating and optional follow-ups; a free-text explanation if you choose "Other". Your answers can reveal your moral views.</li>
  <li><strong>Optional demographics</strong> — age bracket, gender, childhood country/region, prior familiarity. All optional.</li>
  <li><strong>Submission timestamp.</strong></li>
  <li><strong>Short one-way hashes of your session cookie and browser identifier</strong> — used solely to prevent the same browser submitting twice. Because such a key exists, the data is pseudonymous rather than anonymous.</li>
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
  <li><strong>Educator and administrator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see aggregate counts and the pseudonymous response-level data for their own classes. No stored field identifies a participant directly.</li>
  <li><strong>The administrator</strong> has technical access for maintenance, backups and security only.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Class responses</strong> — retained without a fixed deletion schedule; retention is reviewed periodically and data no longer needed for the educational and research purpose is removed. There is currently no automatic deletion job.</li>
  <li><strong>Baseline (Prolific) responses</strong> — retained as part of the research dataset; the Prolific ID is held only for deduplication and withdrawal.</li>
  <li><strong>Educator accounts</strong> — retained until deactivated or deleted by an administrator.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>We store no name or e-mail address, so we usually cannot
locate a specific class response after the fact. Within the lifetime of your
session cookie a submission can still be matched via the duplicate-prevention
hash — if you contact us promptly from the same browser session we will delete
it. Baseline participants can always request deletion via their Prolific ID.</p>""",
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
            ("drawbridge_admin", "Keeps educators and administrators signed in (signed, HTTP-only).", "4 hours", "backoffice"),
            ("bo_csrf", "Protects backoffice forms against cross-site request forgery (signed, HTTP-only).", "1 hour", "backoffice"),
            ("bo_flash", "Carries a one-off status message between two backoffice pages.", "10 seconds", "backoffice"),
            ("db_pending_totp / drawbridge_pending2fa", "Carries the intermediate step of two-factor sign-in.", "5 minutes", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "inequality": {
        "domain": "inequality-explorer.org",
        "tool_name": "Wealth Inequality Explorer",
        "languages": ["en"],
        "art9": True,  # 2026-07-30: the demographics page asks two political-opinion
                       # items (pol_redistribution, pol_regulation), stored as enums.
                       # Political opinions are Art. 9(1) data — the earlier False was wrong.
        "purpose": {
            "en": "The Wealth Inequality Explorer collects numerical estimates of "
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
  <li><strong>Keeping demographics for research beyond this class</strong> — your separate consent (Art. 6(1)(a)), also its own unticked box. If you decline, your demographic answers are used for your class's results and then deleted.</li>
  <li><strong>Educator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Educators</strong> see who responded (names or pseudonyms) but not individual response values linked to a person; responses are shown in aggregate or anonymised form. Educators can delete erroneous entries in their own sessions.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>After 30 days, what happens depends on your consent.</strong> In every case your name and e-mail address are removed. If you did <em>not</em> consent to research use, your demographic answers are <strong>deleted outright</strong> at the same moment. If you did consent, they are kept — but the record is <strong>cut loose from your class</strong>: the link to the session is removed and the timestamp is reduced to the month, so the answers sit in a large cross-class pool instead of a group of twenty where a combination of age, gender and income could point at one person.</li>
  <li><strong>What that means for you:</strong> once the 30 days have passed we can no longer find your individual response, so a withdrawal request has to reach us before then. Until then, write to us and we will delete it.</li>
  <li>This routine had been broken since the feature was written — the database rejected the deletion every time, and it only ran at start-up — and was repaired on 2026-07-30/31. A test now executes the deletion itself on every deploy rather than merely checking that the code exists.</li>
  <li><strong>Manual anonymisation:</strong> educators can anonymise or archive a session at any time before the 30-day window ends.</li>
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
            ("backoffice", "Keeps educators signed in (signed, HTTP-only).", "4 hours", "backoffice"),
            ("wee_pending_totp", "Carries the intermediate step of two-factor sign-in.", "5 minutes", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "layoff": {
        "domain": "layoff-exercise.org",
        "tool_name": "The Layoff Exercise",
        "languages": ["en", "de"],
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
  <li><strong>Educators</strong> see the participants of their own classes (e-mail addresses) and the class's responses for the debrief.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Lehrende</strong> sehen die Teilnehmenden ihrer eigenen Klassen (E-Mail-Adressen) und die Antworten der Klasse für die Auswertung.</li>
  <li><strong>Der Administrator</strong> hat ausschließlich technischen Zugriff für Wartung und Sicherheit.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Automatic anonymisation:</strong> classes whose responses are older than 60 days are anonymised automatically (hourly check) — e-mail addresses are deleted; rankings are kept for aggregate analysis.</li>
  <li><strong>Educator-triggered anonymisation:</strong> educators are asked to anonymise a class as soon as the session is finished, and can do so at any time.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Automatische Anonymisierung:</strong> Klassen, deren Antworten älter als 60 Tage sind, werden automatisch anonymisiert (stündliche Prüfung) — E-Mail-Adressen werden gelöscht; die Reihungen bleiben für aggregierte Auswertungen erhalten.</li>
  <li><strong>Anonymisierung durch Lehrende:</strong> Lehrende werden gebeten, eine Klasse unmittelbar nach der Sitzung zu anonymisieren, und können dies jederzeit tun.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>Before anonymisation, write to us or to your educator naming
the e-mail address you used; the submission can be located and deleted. After
anonymisation, responses are no longer linked to a person.</p>""",
            "de": """<p>Vor der Anonymisierung schreiben Sie uns oder Ihrer Lehrperson
unter Angabe der verwendeten E-Mail-Adresse; die Abgabe kann gefunden und
gelöscht werden. Nach der Anonymisierung sind Antworten keiner Person mehr
zugeordnet.</p>""",
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
            ("layoff_participant", "Carries your e-mail and class code between the exercise steps (signed, HTTP-only).", "24 hours", "participants"),
            ("layoff_flash", "Carries a one-off status message between two pages.", "10 minutes", "all"),
            ("layoff_admin", "Keeps educators signed in (signed, HTTP-only).", "4 hours", "backoffice"),
            ("lo_pending_totp / layoff_pending2fa", "Carries the intermediate step of two-factor sign-in.", "5 minutes", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "lsr": {
        "domain": "lsr-profiler.org",
        "tool_name": "LSR Profiler",
        "languages": ["en", "de"],
        "art9": False,  # leadership-style point allocations
        "purpose": {
            "en": "The LSR Profiler collects scenario-based point allocations and "
                  "produces a personal leadership-style repertoire report, with an "
                  "optional class comparison, for use in executive education.",
            "de": "Der LSR Profiler erhebt szenariobasierte Punktverteilungen und "
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
  <li><strong>Research and cross-class benchmark use</strong> — an unticked checkbox on the first page, which at present must be ticked to continue. Because it cannot currently be declined while still taking part, we do <strong>not</strong> claim it as freely-given consent under Art. 6(1)(a); this processing rests on the same legitimate interest as above, and making the choice genuinely optional is a change we have identified and intend to make.</li>
  <li><strong>Educator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Durchführung des Profilers, Klassen­aggregat, Versand des PDF-Berichts</strong> — Art. 6 Abs. 1 lit. f DSGVO, unser berechtigtes Interesse an der Unterstützung des Weiterbildungs­programms, in dem die Teilnehmenden eingeschrieben sind.</li>
  <li><strong>Forschungs- und klassen­übergreifende Benchmark-Nutzung</strong> — ein nicht vorangekreuztes Kästchen auf der ersten Seite, das derzeit angekreuzt werden muss, um fortzufahren. Da es sich gegenwärtig nicht ablehnen lässt, ohne die Teilnahme abzubrechen, stützen wir diese Verarbeitung <strong>nicht</strong> auf eine freiwillige Einwilligung nach Art. 6 Abs. 1 lit. a DSGVO, sondern auf dasselbe berechtigte Interesse wie oben; die Wahlmöglichkeit tatsächlich freiwillig zu machen, ist eine erkannte und beabsichtigte Änderung.</li>
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
  <li><strong>Live-class mode:</strong> report access and withdrawal expire 14 days after the class is closed; educators can postpone this in limited 7-day steps. At the deadline your e-mail address, name, withdrawal token and class linkage are removed; pseudonymised response data may be kept for aggregate analysis where you consented.</li>
  <li><strong>Self-guided mode:</strong> the same 14-day window, counted from submission.</li>
  <li><strong>Educator accounts:</strong> retained until deleted by the administrator.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Kursmodus:</strong> Berichtszugriff und Widerruf enden 14 Tage nach Schließung der Klasse; Lehrende können dies in begrenzten 7-Tage-Schritten aufschieben. Zum Stichtag werden E-Mail-Adresse, Name, Widerrufstoken und Klassenzuordnung entfernt; pseudonymisierte Antwortdaten können für aggregierte Auswertungen aufbewahrt werden, soweit Sie eingewilligt haben.</li>
  <li><strong>Selbststudium:</strong> dieselbe 14-Tage-Frist, gerechnet ab der Abgabe.</li>
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
            ("repertoire_answers / scenario_answers / context_answers / demographics_data", "Carry your in-progress answers from page to page so you do not lose them mid-questionnaire (signed, HTTP-only).", "2 hours", "participants"),
            ("response_id / withdrawal_raw", "Your submission reference and your withdrawal link, so the results page can offer withdrawal (signed, HTTP-only).", "2 hours", "participants"),
            ("backoffice", "Keeps educators signed in (signed, HTTP-only).", "4 hours", "backoffice"),
            ("lsr_pending_totp", "Carries the intermediate step of two-factor sign-in.", "5 minutes", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "moralmirror": {
        "domain": "moral-mirror.org",
        "tool_name": "Moral Mirror",
        "languages": ["en"],
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
  <li><strong>Session responses</strong> — retained until the session is deleted by an educator or the administrator. There is currently no automatic anonymisation job; one is planned, and this notice will be updated when it exists.</li>
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
            ("moralmirror_admin", "Keeps educators signed in (signed, HTTP-only).", "4 hours", "backoffice"),
            ("mm_pending_totp / moralmirror_pending2fa", "Carries the intermediate step of two-factor sign-in.", "5 minutes", "backoffice"),
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
            ("orgdesignsim_participant", "Keeps your simulation session while you play (HTTP-only).", "24 hours", "participants"),
            ("orgdesignsim_backoffice", "Keeps educators signed in (signed, HTTP-only).", "4 hours", "backoffice"),
            ("os_pending_totp / orgdesignsim_pending2fa", "Carries the intermediate step of two-factor sign-in.", "5 minutes", "backoffice"),
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
            "en": "phronon.org is the umbrella site for the Phronon classroom "
                  "simulations. Each simulation runs on its own domain and "
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
            "en": """<p>The Phronon name, wordmark, logo and the simulations
linked from this site are original works.</p>""",
        },
        "cookies": [
            ("session", "Set only inside the private administration area to keep an administrator signed in (signed, HTTP-only). Not used on public pages.", "4 hours", "backoffice"),
        ],
    },

    # ────────────────────────────────────────────────────────────────────
    "whiteout": {
        "domain": "whiteout-exercise.org",
        "tool_name": "The Whiteout Exercise",
        "languages": ["en", "de"],
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
  <li><strong>E-mail address</strong> — <strong>required</strong> to join a session. It is stored with your ranking and is visible to your facilitator in the session's participant list.</li>
  <li><strong>A pseudonymous session token</strong> in a cookie, linking your responses within one session.</li>
  <li><strong>Session code</strong> — attributes your response to the correct group session.</li>
  <li><strong>Your item rankings</strong> — individual and, where applicable, the group ranking.</li>
  <li><strong>Second-stage response</strong> — your choice in the optional text-message challenge, if activated.</li>
  <li><strong>Submission timestamp.</strong></li>
</ul>
<h3>From facilitators</h3>
<ul>
  <li><strong>Login credentials</strong> — the password is stored only as a bcrypt hash.</li>
  <li><strong>Session data</strong> — names, codes and configuration of sessions you create.</li>
</ul>""",
            "de": """
<h3>Von Teilnehmenden</h3>
<ul>
  <li><strong>E-Mail-Adresse</strong> — <strong>erforderlich</strong>, um an einer Sitzung teilzunehmen. Sie wird zusammen mit Ihrer Reihung gespeichert und ist für die moderierende Person in der Teilnehmendenliste sichtbar.</li>
  <li><strong>Ein pseudonymes Sitzungstoken</strong> in einem Cookie, das Ihre Antworten innerhalb einer Sitzung verknüpft.</li>
  <li><strong>Sitzungscode</strong> — ordnet Ihre Antwort der richtigen Gruppensitzung zu.</li>
  <li><strong>Ihre Reihungen</strong> — individuell und ggf. die Gruppenreihung.</li>
  <li><strong>Antwort der zweiten Stufe</strong> — Ihre Wahl in der optionalen Textnachrichten-Aufgabe, falls aktiviert.</li>
  <li><strong>Zeitstempel der Abgabe.</strong></li>
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
  <li><strong>Facilitator accounts</strong> — Art. 6(1)(b) GDPR.</li>
  <li><strong>Security, rate-limiting and abuse prevention</strong> — Art. 6(1)(f) GDPR.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Durchführung der Übung und Erstellung der Gruppenergebnisse</strong> — Art. 6 Abs. 1 lit. f DSGVO, unser berechtigtes Interesse an der Unterstützung des Bildungsprogramms, an dem die Teilnehmenden teilnehmen.</li>
  <li><strong>Konten von Moderierenden</strong> — Art. 6 Abs. 1 lit. b DSGVO.</li>
  <li><strong>Sicherheit, Rate-Limiting und Missbrauchs­abwehr</strong> — Art. 6 Abs. 1 lit. f DSGVO.</li>
</ul>""",
        },
        "access": {
            "en": """
<ul>
  <li><strong>Facilitators</strong> see, for their own sessions, the participant list <strong>including each participant's e-mail address</strong>, alongside the individual and group rankings.</li>
  <li><strong>The administrator</strong> has technical access for maintenance and security only.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Moderierende</strong> sehen für ihre eigenen Sitzungen die Teilnehmendenliste <strong>einschließlich der E-Mail-Adressen</strong> sowie die individuellen und die Gruppenreihungen.</li>
  <li><strong>Der Administrator</strong> hat ausschließlich technischen Zugriff für Wartung und Sicherheit.</li>
</ul>""",
        },
        "retention": {
            "en": """
<ul>
  <li><strong>Session responses</strong> — retained until the facilitator deletes the session in the backoffice, or until no longer needed for the educational purpose. There is currently no automatic deletion job.</li>
  <li><strong>Facilitator accounts</strong> — retained until deactivated or deleted by an administrator.</li>
</ul>""",
            "de": """
<ul>
  <li><strong>Sitzungsantworten</strong> — bleiben gespeichert, bis die moderierende Person die Sitzung im Backoffice löscht oder die Daten für den Bildungszweck nicht mehr benötigt werden. Einen automatischen Löschjob gibt es derzeit nicht.</li>
  <li><strong>Konten von Moderierenden</strong> — bis zur Deaktivierung oder Löschung durch einen Administrator.</li>
</ul>""",
        },
        "erasure": {
            "en": """<p>Your e-mail address identifies your submission, so we can
always find and delete it: write to us, or ask your facilitator, naming the
session code and the address you joined with. Facilitators can also delete a
whole session at any time.</p>""",
            "de": """<p>Ihre E-Mail-Adresse identifiziert Ihre Abgabe, wir können
sie also jederzeit finden und löschen: Schreiben Sie uns oder Ihrer
moderierenden Person unter Angabe des Sitzungscodes und der verwendeten
Adresse. Moderierende können außerdem ganze Sitzungen jederzeit löschen.</p>""",
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
            ("whiteout_session", "Keeps facilitators signed in (signed, HTTP-only).", "4 hours", "backoffice"),
            ("wo_pending_totp / whiteout_pending2fa", "Carries the intermediate step of two-factor sign-in.", "5 minutes", "backoffice"),
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
