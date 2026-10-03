"""Old name of `phronon_common.mail_diagnostics` (moved 3 October 2026).

Not a copy and not a re-export: importing this name hands back the very module
object `phronon_common.mail_diagnostics`, so a test that patches an attribute
through either name patches the one the code reads, and there is one
FULL_SEND_STAMP, one TEST_RECIPIENT, one set of functions. New code imports
`phronon_common.mail_diagnostics`.
"""
import sys

from phronon_common import mail_diagnostics as _moved

sys.modules[__name__] = _moved
