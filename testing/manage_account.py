"""The Manage account page — wiring, and the guards that make it safe.

Why source and template assertions rather than driven routes: the dangerous
parts of this page are CONDITIONS (is the password asked for? is the section
hidden while a temporary password is in force? does confirming end the open
sessions?), and every one of them is a line that can be deleted without any
page failing to render. The token logic itself is exercised properly in
phronon_common/tests/test_account.py.

SHARED SINCE 4 SEPTEMBER 2026. This was 309 lines copied into eight tools in
four versions, and the four differed in exactly three things: which template
holds the nav, which route resets another account's two-factor, and a
`NAME_FIELD` constant that **no copy ever read** — Polarity Profiler was
maintaining a different value for a knob nobody used. The first two are real
and stay overridable below; the third is gone.

Each tool subclasses the mixins in its own tests/ file, which is what keeps the
check inside that project's own gate. No pytest import here — see
phronon_common/testing/__init__.py.

TOOLS THAT MOUNT THE ACCOUNT KIT (FL-083, 4 October 2026). Moral Mirror and
Drawbridge no longer write these routes or the account templates themselves:
`phronon_common/account_kit.py` does, from an adapter in their app.py. For
such a tool every check below reads the code where it now lives: a route's
body is found in the kit when app.py has none (the administrator's two-factor
reset included), the page is the kit's template, the two gates are the kit's
lists, and the row the account page renders is followed from the adapter's
`current_account=` into the tool's own session helper. A tool that does not
mount the kit is read exactly as before.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def _read(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


#: A route decorator: `@app.post(...)` in a tool whose routes are in app.py,
#: `@router.post(...)` in one that keeps them in APIRouter modules (FL-082).
_DECORATOR = r"@(?:app|router)\."

#: The shared account routes and their templates (account_kit.py). Found next
#: to this package rather than imported: the wheel ships both.
KIT_PY = Path(__file__).resolve().parents[1] / "account_kit.py"
KIT_TEMPLATES = Path(__file__).resolve().parents[1] / "account_templates"
#: What an app.py that mounts the kit contains.
KIT_MOUNT = "account_kit.build_account_router("


def _route_pattern(owner: str, method: str, path: str) -> "re.Pattern":
    """A route's decorator, its def line, and the body up to the next route.
    `owner` is `app` for a tool's app.py, `router` for the kit, whose routes
    are nested in build_account_router and therefore indented."""
    return re.compile(
        r"@%s\.%s\(\s*['\"]%s['\"].*?\n(?:[ \t]*@%s\.\w+\([^\n]*\n)*"
        r"[ \t]*(?:async )?def [^\n]*\n(.*?)(?=\n[ \t]*@%s\.|\n[ \t]*%s\.add_api_route|\Z)"
        % (owner, method, re.escape(path), owner, owner, owner), re.S)


class AccountPageContract:
    """Config plus the helpers every mixin below shares.

    A tool sets PROJECT_ROOT; everything else has a fleet default and is
    overridden only where the tool genuinely differs.
    """

    #: Set by the tool: the repository root.
    PROJECT_ROOT: Path | None = None
    #: Where the backoffice nav markup lives, relative to templates/backoffice.
    NAV_TEMPLATE = "base.html"
    #: Candidates for "an admin resets somebody else's two-factor". The first
    #: one this tool actually registers is the one checked.
    TWOFACTOR_RESET_ROUTES = (
        "/backoffice/users/{uid}/reset-two-factor",
        "/backoffice/users/{user_id}/reset-two-factor",
    )
    #: Layout classes the page's own stylesheets must define.
    STRUCTURAL = (".bo-form-card", ".field", ".bo-account")
    #: What the template reads off the account row, mapped to the column behind it.
    NEEDED = ("totp_enabled", "must_change_password")
    #: The tool's Python sources, relative to PROJECT_ROOT. Empty means app.py
    #: alone, which was every tool until 4 October 2026. A tool that keeps its
    #: routes in router modules names them ALL (OrgDesignSim, FL-082): this
    #: contract reads handlers by route, and a route in an unlisted file would
    #: fail as "not wired" — or, for the substring checks, pass on nothing.
    APP_SOURCES: tuple = ()

    # ── the files this contract reads ───────────────────────────────────────
    @property
    def tpl(self) -> Path:
        return Path(self.PROJECT_ROOT) / "templates" / "backoffice"

    @property
    def app_texts(self) -> list:
        """Each source file's text, kept apart so a handler is never read
        across a file boundary."""
        return [_read(Path(self.PROJECT_ROOT) / name)
                for name in (self.APP_SOURCES or ("app.py",))]

    @property
    def app_src(self) -> str:
        return "\n".join(self.app_texts)

    @property
    def uses_account_kit(self) -> bool:
        """Does this tool mount phronon_common.account_kit (FL-083)?"""
        return KIT_MOUNT in self.app_src

    @property
    def kit_src(self) -> str:
        return _read(KIT_PY)

    def _page(self, name: str) -> Path:
        """The tool's own template, or the kit's when the tool mounts the kit
        and no longer carries one."""
        own = self.tpl / name
        if self.uses_account_kit and not own.is_file():
            return KIT_TEMPLATES / name
        return own

    @property
    def account_html(self) -> str:
        return _read(self._page("account.html"))

    @property
    def confirm_html(self) -> str:
        return _read(self._page("account_confirm_email.html"))

    @property
    def nav_html(self) -> str:
        return _read(self.tpl / self.NAV_TEMPLATE)

    @property
    def users_html(self) -> str:
        return _read(self.tpl / "users.html")

    def route_src(self, path: str, method: str = "post") -> str:
        """The body of the handler decorated with `@app.<method>('<path>')`
        (or `@router.<method>(...)`), in whichever source file holds it.

        Found by ROUTE rather than by function name: the nine tools spell their
        handlers differently, and a test that hunts for a function name goes
        quietly green the day somebody renames one.
        """
        pattern = re.compile(
            r"%s%s\(\s*['\"]%s['\"].*?\n(?:%s\w+\([^\n]*\n)*"
            r"(?:async )?def [^\n]*\n(.*?)(?=\n%s|\Z)"
            % (_DECORATOR, method, re.escape(path), _DECORATOR, _DECORATOR),
            re.S)
        for text in self.app_texts:
            m = pattern.search(text)
            if m:
                return m.group(1)
        if self.uses_account_kit:
            m = _route_pattern("router", method, path).search(self.kit_src)
            if m:
                return m.group(1)
        raise AssertionError(f"no @app.{method} route for {path} — the page is not wired")


class ItIsReachable(AccountPageContract):
    """The bug that started this: the two-factor page existed for weeks and
    nothing in the fleet linked to it, so educators could not find it."""

    def test_the_nav_points_at_the_account_page(self):
        assert "/backoffice/account" in self.nav_html

    def test_the_old_change_password_link_is_gone_from_the_nav(self):
        assert 'href="/backoffice/change-password"' not in self.nav_html
        assert 'href="/backoffice/change_password"' not in self.nav_html

    def test_the_account_page_reaches_two_factor(self):
        assert "/backoffice/two-factor" in self.account_html


class SectionsAreGatedByState(AccountPageContract):

    def test_a_temporary_password_hides_everything_but_the_password(self):
        """Otherwise a leaked temporary password could be used to move the
        account's e-mail address — which is the account itself."""
        assert self.account_html.count("{% if not must_change %}") >= 2

    def test_the_name_and_email_handlers_refuse_while_a_password_is_pending(self):
        for path in ("/backoffice/account/name", "/backoffice/account/email"):
            src = self.route_src(path)
            assert "must_change_password" in src, f"{path} does not check it"
            assert "password_needed" in src

    def test_the_forced_enrolment_gate_did_not_widen(self):
        """An admin who has not enrolled may do exactly one thing. The account
        page is on the must-change list because the password form lives there;
        it must NOT be on the two-factor one."""
        if self.uses_account_kit:
            # The kit's gate (account_kit.account_gate) holds both lists; its
            # own tests drive it. Here: the lists say what this test says.
            from phronon_common import account_kit
            assert not "/backoffice/account".startswith(account_kit.ENROLMENT_OPEN), (
                "the account page is open to an administrator who has not enrolled")
            assert account_kit.TWO_FACTOR_URL in account_kit.ENROLMENT_OPEN
            return
        if "_2FA_ALLOWED" not in self.app_src:
            return          # this tool guards the two gates separately already
        block = self.app_src.split("_2FA_ALLOWED")[1][:400]
        assert "/backoffice/account" in block, "the narrower list is not derived"
        assert "!=" in block or "not in" in block

    def test_the_account_page_is_allowed_through_the_must_change_gate(self):
        """It carries the password form now, so a locked-out account has to be
        able to reach it — the section gating above is what makes that safe."""
        if self.uses_account_kit:
            from phronon_common import account_kit
            assert "/backoffice/account" in account_kit.MUST_CHANGE_OPEN
            return
        block = self.app_src.split("_MUST_CHANGE_ALLOWED")[1][:600]
        assert "/backoffice/account" in block


class ChangingTheAddress(AccountPageContract):

    def test_it_asks_for_the_password(self):
        """A session is what an attacker has; the password is what this asks for."""
        src = self.route_src("/backoffice/account/email")
        assert "current_password" in src
        assert re.search(
            r"_check_pw|verify_password|check_password|checkpw|verify_admin", src), (
            "the current password is never verified")

    def test_the_form_asks_for_it_too(self):
        assert 'name="current_password"' in self.account_html

    def test_nothing_is_written_before_the_link_comes_back(self):
        src = self.route_src("/backoffice/account/email")
        # `{T}` is the kit's name for the tool's account table.
        assert not re.search(r"UPDATE (?:admins|\{T\}) SET\s+email", src, re.I), (
            "the address must not change until the new mailbox has been proved")

    def test_both_addresses_are_told(self):
        src = self.route_src("/backoffice/account/email")
        assert "send_email_change_confirm" in src
        assert "send_email_change_notice" in src, (
            "the current address must hear about it while the link is still unused")

    def test_asking_for_a_change_is_rate_limited(self):
        """It sends two mails to addresses the request names, so a signed-in
        account must not be able to use it as a mailer."""
        src = self.route_src("/backoffice/account/email")
        assert "is_allowed(" in src and "emailchange:" in src

    def test_a_duplicate_address_is_caught_before_the_mail_goes_out(self):
        assert "email_taken" in self.route_src("/backoffice/account/email")

    def test_confirming_ends_every_existing_session(self):
        src = self.route_src("/backoffice/account/email/confirm")
        assert re.search(r"session_epoch\s*=\s*session_epoch\s*\+\s*1", src)
        assert "delete_cookie" in src

    def test_opening_the_link_changes_nothing(self):
        """A corporate mail scanner fetches every URL it sees. Whiteout learned
        this when a HEAD probe spent a participant's one-time resume token and
        locked them out, so the change waits behind a button."""
        get_src = self.route_src("/backoffice/account/email/confirm", method="get")
        assert not re.search(r"\bUPDATE\b", get_src, re.I)
        assert 'name="token"' in self.confirm_html


class TwoFactorFromTheAccountPage(AccountPageContract):

    def test_an_admin_still_cannot_switch_it_off(self):
        src = self.route_src("/backoffice/two-factor")
        assert re.search(r"if (not )?required", src)

    def test_replacing_the_authenticator_needs_no_switching_off(self):
        """An admin with a new phone had no way through at all: disable is
        refused for them, and enrolment only ran when it was off."""
        assert "replace" in self.route_src("/backoffice/two-factor", method="get")
        assert "?replace=1" in self.account_html

    def test_new_recovery_codes_need_a_current_code(self):
        marker = "'regenerate'" if "'regenerate'" in self.app_src else '"regenerate"'
        block = self.route_src("/backoffice/two-factor").split(marker)[1]
        audit_call = "kit.audit(" if self.uses_account_kit else "_audit"
        assert "twofactor.verify" in block.split(audit_call)[0]

    def test_the_disable_button_is_hidden_from_admins(self):
        assert "{% if not totp_required %}" in self.account_html

    def test_recovery_codes_only_appear_behind_the_download_lock(self):
        """Since 2 October 2026 fresh codes must be downloaded before the user
        can continue (recovery-codes.js). The account page used to carry a
        second, unlocked list that no route filled any more (FL-066, deleted);
        a template that lists codes again must bring the lock with it."""
        root = Path(self.PROJECT_ROOT) / "templates"
        pages = [(p, root) for p in root.rglob("*.html")]
        if self.uses_account_kit:
            pages += [(p, KIT_TEMPLATES) for p in KIT_TEMPLATES.glob("*.html")]
        assert pages, "no templates found — this check would pass vacuously"
        for page, base in pages:
            html = _read(page)
            if not re.search(r"{%\s*for \w+ in codes\s*%}", html):
                continue
            where = page.relative_to(base)
            assert "data-recovery-codes" in html, f"{where}: codes listed without the download lock"
            assert "data-recovery-done" in html, f"{where}: nothing for the lock to hold back"
            assert "/static/js/recovery-codes.js" in html, f"{where}: the lock's script is not loaded"


class TheAdminSideReset(AccountPageContract):

    def _reset(self) -> str:
        last = self.TWOFACTOR_RESET_ROUTES[-1]
        for path in self.TWOFACTOR_RESET_ROUTES:
            if re.search(r"%s\w+\(\s*['\"]%s['\"]" % (_DECORATOR, re.escape(path)), self.app_src):
                return self.route_src(path)
        # None registered: ask for the last one so the failure names a route.
        return self.route_src(last)

    def test_only_admins_may(self):
        assert re.search(
            r"role.*!=|!=.*role|_require_admin|require_admin|is_admin|require_role|"
            r"role.*==.*ADMIN", self._reset(), re.I)

    def test_it_clears_the_secret_and_the_codes(self):
        src = self._reset()
        assert re.search(r"totp_secret\s*=\s*NULL", src, re.I)
        assert re.search(r"totp_backup_codes\s*=\s*NULL", src, re.I)

    def test_it_signs_the_account_out_everywhere(self):
        assert re.search(r"session_epoch\s*=\s*session_epoch\s*\+\s*1", self._reset())

    def test_it_is_audited_and_the_account_is_told(self):
        src = self._reset()
        assert "two_factor_reset_by_admin" in src
        assert "send_two_factor_reset_notice" in src, (
            "an admin reset and an account takeover look identical from the inside")

    def test_the_button_asks_once_before_doing_it(self):
        block = self.users_html.split("reset-two-factor")[1]
        assert "data-confirm" in block


class MessagesAreNotRenderedFromTheUrl(AccountPageContract):

    def test_the_page_looks_texts_up_by_key(self):
        """`?msg=` carries a key, never a sentence — a page that prints back
        whatever the URL says can be sent to somebody saying anything."""
        if self.uses_account_kit:      # the kit's tables, and its lookups
            assert ("ACCOUNT_MESSAGES.get(" in self.kit_src
                    and "ACCOUNT_ERRORS.get(" in self.kit_src)
            return
        assert ("_ACCOUNT_MESSAGES.get(" in self.app_src
                and "_ACCOUNT_ERRORS.get(" in self.app_src)


class EveryFormCarriesItsCsrfToken(AccountPageContract):

    def test_no_form_without_a_token(self):
        for html in (self.account_html, self.confirm_html):
            forms = re.findall(
                r"<form[^>]*method=\"post\"[^>]*>(.*?)</form>", html, re.S | re.I)
            assert forms
            for body in forms:
                assert "csrf_token" in body


class EveryFormPostsToARouteThatExists(AccountPageContract):
    """Layoff's password form 404ed in production for the length of one deploy:
    the page rendered, the form looked right, and nothing had ever POSTed to it.
    A form is not wired until something posts to it."""

    def test_every_action_resolves(self):
        actions = set(re.findall(
            r'<form[^>]*method="post"[^>]*action="([^"]+)"',
            self.account_html + self.confirm_html, re.I))
        assert actions, "no POST form actions found — the page cannot be right"
        for action in actions:
            path = action.split("?")[0]
            # A `{{ k.id }}` in the template is a `{pid}` in the route (the
            # passkeys' Remove buttons, 2 October 2026).
            pattern = r"\{\w+\}".join(re.escape(part)
                                       for part in re.split(r"\{\{.*?\}\}", path))
            assert re.search(
                r'%s(?:post|api_route)\(\s*[\'"]%s[\'"]' % (_DECORATOR, pattern),
                self.app_src) or (self.uses_account_kit and re.search(
                    r'@router\.(?:post|api_route)\(\s*[\'"]%s[\'"]' % pattern,
                    self.kit_src)), f"nothing answers POST {path}"


class ThePageIsActuallyStyled(AccountPageContract):
    """Inequality's and Layoff's account pages shipped as unstyled labels and
    browser-default buttons: both tools define `.bo-form-card` in a sheet they
    load PER PAGE, and this page did not carry that line. Nothing failed — the
    page rendered, every test passed, and it looked like a 1998 form.

    So the check is not "does it load the same sheets as some other page" (the
    tools legitimately differ) but "is every class this page's layout depends on
    actually DEFINED in a sheet this page loads"."""

    def _sheets(self) -> str:
        base = _read(self.tpl / "base.html")
        hrefs = re.findall(r'<link rel="stylesheet"[^>]*href="([^"]+)"',
                           base + self.account_html)
        out = []
        for h in hrefs:
            m = re.search(r"(css/[A-Za-z0-9._-]+\.css)", h)          # /static/css/x.css
            if not m:
                m = re.search(r"filename='(css/[A-Za-z0-9._-]+\.css)'", h)  # url_for(...)
            if m:
                p = Path(self.PROJECT_ROOT) / "static" / m.group(1)
                if p.is_file():
                    out.append(_read(p))
        return "\n".join(out)

    def test_the_classes_this_page_uses_have_rules(self):
        css = self._sheets()
        assert css, "this page loads no stylesheet this test can find"
        used = [c for c in self.STRUCTURAL if c[1:] in self.account_html]
        assert used, "the page uses none of the shared layout classes — check this test"
        missing = [c for c in used if not re.search(re.escape(c) + r"\s*[,{: ]", css)]
        assert not missing, (
            f"{missing} styles nothing: this page uses those classes and loads no "
            f"stylesheet that defines them, so it renders unstyled")


class ThePageReadsARowThatHasTheColumns(AccountPageContract):
    """It said "Two-factor login is off" for an account that had it on.

    Inequality Explorer's session helper selects four columns — id, email, role,
    session_epoch — because it runs on every request. The account page rendered
    `account.totp_enabled` off that dict, the key was simply absent,
    `bool(None)` is False, and the page reported it as fact (owner, 18 August
    2026). Nothing failed: no error, no empty page, just a confident wrong
    answer, with the Name field blank beside it and the must-change guard
    reading False for everyone.

    So the check follows the DATA rather than the markup: whatever query the
    account page's row comes from, does it carry the columns the page renders
    off that row?
    """

    def _queries_reachable_from_the_account_page(self):
        """Every `SELECT … FROM admins` in the account GET handler and in the
        functions it calls by name. One level of indirection is enough: these
        pages read a row either directly or through the tool's own session
        helper."""
        src = self.route_src("/backoffice/account", method="get")

        def defined(name):
            """`def name(...)` and its body, from whichever file defines it."""
            for text in self.app_texts:
                m = re.search(r"^(?:async )?def %s\(.*?(?=\n(?:async )?def |\n%s|\Z)"
                              % (re.escape(name), _DECORATOR), text, re.S | re.M)
                if m:
                    return m.group(0)
            return None

        if self.uses_account_kit:
            # The kit renders the row the adapter's `current_account=` returns,
            # and that is the tool's own function: start the walk there.
            m = re.search(r"current_account\s*=\s*([A-Za-z_]\w*)", self.app_src)
            assert m, "the kit is mounted but no current_account= is visible in app.py"
            src = f"{m.group(1)}()"
        called = set(re.findall(r"\b([a-zA-Z_][\w]*)\s*\(", src))
        bodies = [src]
        for name in called:
            body = defined(name)
            if body:
                bodies.append(body)
        # …and one more hop, for `require_x -> get_admin_by_id -> SELECT`.
        for body in list(bodies):
            for name in set(re.findall(r"\b([a-zA-Z_][\w]*)\s*\(", body)):
                found = defined(name)
                if found:
                    bodies.append(found)
        joined = "\n".join(bodies)
        return re.findall(r"SELECT\s+(.*?)\s+FROM\s+admins", joined, re.S | re.I)

    def test_the_row_carries_what_the_page_renders(self):
        selects = self._queries_reachable_from_the_account_page()
        assert selects, (
            "no `SELECT … FROM admins` is reachable from the account page — this "
            "test cannot see where its row comes from, so it would pass vacuously")
        if any("*" in sel for sel in selects):
            return                      # a full row carries everything
        columns = " ".join(selects)
        missing = [c for c in self.NEEDED if c not in columns]
        assert not missing, (
            f"the account page renders {missing} off a row whose query does not "
            f"select it — the key is absent, not false, and the page states the "
            f"absence as fact")


#: The mixins a tool's tests/test_manage_account.py subclasses, in the order
#: they were written. Named so a wrapper can loop rather than list them.
CONTRACT_MIXINS = (
    ItIsReachable,
    SectionsAreGatedByState,
    ChangingTheAddress,
    TwoFactorFromTheAccountPage,
    TheAdminSideReset,
    MessagesAreNotRenderedFromTheUrl,
    EveryFormCarriesItsCsrfToken,
    EveryFormPostsToARouteThatExists,
    ThePageIsActuallyStyled,
    ThePageReadsARowThatHasTheColumns,
)
