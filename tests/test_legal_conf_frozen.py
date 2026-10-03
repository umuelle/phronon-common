"""legal_conf.TOOLS is frozen (4 October 2026).

Every tool publishes from its own legal_content/notice.json. The entries in
legal_conf.TOOLS serve only tool versions that have not migrated and earlier
versions a rollback may restore, so they must stay exactly as they were. An
edit here changes no published notice of a migrated tool, and would quietly
make the two copies disagree.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common import legal_conf  # noqa: E402

FROZEN = "3ed807f38aeafc16a839da9c802228347005aa92b3ef4c9c2717182a56713fdc"


def test_the_legacy_table_is_unchanged():
    now = hashlib.sha256(json.dumps(legal_conf.TOOLS, sort_keys=True, ensure_ascii=False,
                                    default=list).encode()).hexdigest()
    assert now == FROZEN, (
        "legal_conf.TOOLS changed. To change a tool's notice, edit that tool's own "
        "legal_content/notice.json and deploy that tool; this table is a frozen "
        "compatibility copy (see the top of legal_conf.py)")
