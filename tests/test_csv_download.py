"""The export helper refuses what reviews keep finding (FL-022)."""
import pytest

from phronon_common.exports import csv_download


def _calls():
    seen = []
    def audit(action, **kw):
        seen.append((action, kw))
    return seen, audit


def test_it_writes_the_audit_row_before_the_body():
    seen, audit = _calls()
    r = csv_download(filename='x.csv', header=['a'], rows=[['1']],
                     audit=audit, actor='her@example.org', subject='CLASS1')
    assert seen == [('data_exported', {'request': None, 'subject': 'CLASS1',
                                       'details': None, 'admin_id': None,
                                       'admin_email': 'her@example.org'})]
    assert r.media_type == 'text/csv'


def test_no_actor_is_a_refusal_not_a_default():
    _, audit = _calls()
    with pytest.raises(ValueError):
        csv_download(filename='x.csv', header=['a'], rows=[], audit=audit, actor='')


def test_no_audit_writer_is_a_refusal():
    with pytest.raises(ValueError):
        csv_download(filename='x.csv', header=['a'], rows=[],
                     audit=None, actor='her@example.org')


def test_participant_data_is_never_cached():
    _, audit = _calls()
    r = csv_download(filename='x.csv', header=['a'], rows=[], audit=audit,
                     actor='her@example.org')
    assert r.headers['cache-control'] == 'no-store'
    assert 'attachment; filename="x.csv"' in r.headers['content-disposition']


def test_every_cell_is_formula_safe():
    """The reason this helper builds the body itself rather than taking one:
    a caller who forgets csv_safe ships a live formula to the educator's
    spreadsheet, and that has to be impossible rather than remembered."""
    import asyncio

    _, audit = _calls()
    r = csv_download(filename='x.csv', header=['name'],
                     rows=[['=cmd|calc']], audit=audit, actor='her@example.org')

    async def read():
        # StreamingResponse wraps a sync iterator in an async generator, so the
        # body only exists once something awaits it.
        out = []
        async for chunk in r.body_iterator:
            out.append(chunk if isinstance(chunk, str) else chunk.decode())
        return ''.join(out)

    body = asyncio.run(read())
    assert "'=cmd|calc" in body, 'a participant-typed formula must arrive as text'
    assert body.splitlines()[0] == 'name'
