from __future__ import annotations
from difflib import SequenceMatcher
from io import TextIOWrapper
from itertools import zip_longest
import sys
from typing import Iterable, Literal

from diff_to_annotations import gather_diff, FrozenSection, lines_to_chapters
from lineno_to_section import section_to_str
from mds_to_html import clean_html

START = """
<table border="1" frame="border">
<tr><th>Section</th><th>Text</th></tr>
""".strip()

SAME_ROW = '''<tr>
<td>{0}</td>
<td>{1}</td>
</tr>'''

def diff_sections(body1: tuple[FrozenSection, ...], body2: tuple[FrozenSection, ...],
                  prefix1: tuple[int, ...] = (), prefix2: tuple[int, ...] = (),
                  contextualized: bool = False) -> Iterable[tuple[Literal['insert', 'delete', 'replace', 'context', 'equal'], tuple[int, ...] | None, str, tuple[int, ...] | None, str]]:
    sm = SequenceMatcher(a=body1, b=body2)
    for ops in sm.get_grouped_opcodes():
        # find whether any of the changes are actually at this level;
        # if none are (i.e. the only changes are in sub-sections), narrow the
        # group down to just the subsection changes
        uneq_ops: list[tuple[str, int, int, int, int]] = []
        for tag, i1, j1, i2, j2 in ops:
            if tag in {'insert', 'delete'}:
                uneq_ops = ops
                break
            if tag == 'replace':
                for i, j in zip_longest(range(i1, j1), range(i2, j2), fillvalue=None):
                    if i is None:
                        assert j is not None
                        uneq_ops.append(('insert', i1+j-i2, i1+j-i2, j, j+1))
                    elif j is None:
                        assert i is not None
                        uneq_ops.append(('delete', i, i+1, j2, j2))
                    else:
                        if body1[i].title != body2[j].title:
                            uneq_ops = ops
                            break
                        uneq_ops.append((tag, i, i+1, j, j+1))
                else:
                    continue
                break
        # if this is the first time in this recursion branch that a change was
        # made at this level, provide one higher level of context and disable
        # context generation for the rest of this recursion branch
        if not contextualized:
            if _contextualized := ops == uneq_ops:
                yield 'context', prefix1, '', prefix2, ''
        else:
            _contextualized = False
        for tag, i1, j1, i2, j2 in uneq_ops:
            if tag == 'insert':
                assert i1 == j1
                for j in range(i2, j2):
                    prefix = (*prefix2, j)
                    yield tag, None, '', prefix, body2[j].title
                    yield from diff_sections((), body2[j].body, (*prefix1, i1), prefix, contextualized or _contextualized)
            elif tag == 'delete':
                assert i2 == j2
                for i in range(i1, j1):
                    prefix = (*prefix1, i)
                    yield tag, prefix, body1[i].title, None, ''
                    yield from diff_sections(body1[i].body, (), prefix, (*prefix2, i2), contextualized or _contextualized)
            elif tag == 'replace':
                for i, j in zip_longest(range(i1, j1), range(i2, j2), fillvalue=None):
                    if i is None:
                        assert j is not None
                        prefix = (*prefix2, j)
                        yield 'insert', None, '', prefix, body2[j].title
                        yield from diff_sections((), body2[j].body, (*prefix1, j1), prefix, contextualized or _contextualized)
                    elif j is None:
                        assert i is not None
                        prefix = (*prefix1, i)
                        yield 'delete', prefix, body1[i].title, None, ''
                        yield from diff_sections(body1[i].body, (), prefix, (*prefix2, j2), contextualized or _contextualized)
                    else:
                        prefixi = (*prefix1, i)
                        prefixj = (*prefix2, j)
                        if body1[i].title != body2[j].title:
                            yield tag, prefixi, body1[i].title, prefixj, body2[j].title
                        else:
                            yield 'equal', prefixi, body1[i].title, prefixj, body2[j].title
                        yield from diff_sections(body1[i].body, body2[j].body, prefixi, prefixj, contextualized or _contextualized)
            elif tag == 'equal':
                for i, j in zip(range(i1, j1), range(i2, j2), strict=True):
                    prefixi = (*prefix1, i)
                    prefixj = (*prefix2, j)
                    assert body1[i].title == body2[j].title
                    yield tag, prefixi, body1[i].title, prefixj, body2[j].title

def diff_lines(a_line: str, b_line: str) -> tuple[str, str]:
    _a_line: list[str] = []
    _b_line: list[str] = []
    a = a_line.split()
    b = b_line.split()
    for tag, i1, j1, i2, j2 in SequenceMatcher(a=a, b=b).get_opcodes():
        if tag == 'equal':
            _a_line.extend(a[i1:j1])
            _b_line.extend(b[i2:j2])
        if tag == 'delete' or tag == 'replace':
            _a_line.append('<b>')
            _a_line.extend(a[i1:j1])
            _a_line.append('</b>')
        if tag == 'insert' or tag == 'replace':
            _b_line.append('<b>')
            _b_line.extend(b[i2:j2])
            _b_line.append('</b>')
    return ' '.join(_a_line), ' '.join(_b_line)

def main() -> None:
    print(START)
    for file in gather_diff(sys.stdin):
        if 'README' in file.name or 'LICENSE' in file.name or 'index' in file.name:
            continue # not part of the diff
        for hunk in file.hunks:
            _, a_chapters = lines_to_chapters(line[1:] for line in hunk.del_lines)
            meta, b_chapters = lines_to_chapters(line[1:] for line in hunk.add_lines)
            title = meta['subtitle'] if 'policies' in meta['pdf'].casefold() else meta['title']
            tag = None
            for tag, a_prefix, a_line, b_prefix, b_line in diff_sections(a_chapters, b_chapters):
                if not a_prefix:
                    a_prefix = ''
                else:
                    a_prefix = section_to_str(a_prefix + (-1,) * (5 - len(a_prefix))) # type: ignore
                a_line = clean_html(a_line)
                if tag == 'equal':
                    print(SAME_ROW.format(a_prefix, a_line))
                    continue
                if tag == 'context':
                    th = f'{title} § {a_prefix}' if a_prefix else title
                    print(f'<tr><th colspan="2">{th}</th></tr>')
                    continue
                if b_prefix is None:
                    b_prefix = ''
                else:
                    b_prefix = section_to_str(b_prefix + (-1,) * (5 - len(b_prefix))) # type: ignore
                b_line = clean_html(b_line)
                if tag == 'replace':
                    a_line, b_line = diff_lines(a_line, b_line)
                if a_prefix and a_line:
                    print(DEL_ROW.format(a_prefix, a_line))
                if b_prefix and b_line:
                    print(INS_ROW.format(b_prefix, b_line))
            if tag is None: # for loop never executed
                print('<tr><td colspan="2"><i>No changes resulted in HTML differences</i></td></tr>')
    print('</table>')

if __name__ == '__main__':
    if isinstance(sys.stdin, TextIOWrapper):
        sys.stdin.reconfigure(encoding='utf8')
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding='utf8')
    if len(sys.argv) < 3:
        print('usage:', sys.argv[0], '<del tag name>', '<ins tag name>', file=sys.stderr)
        sys.exit(1)
    DEL_ROW = '''<tr>
    <td><%(tag)s style="color: #ff0000">{0}</%(tag)s></td>
    <td><%(tag)s style="color: #ff0000">{1}</%(tag)s></td>
    </tr>''' % {'tag': sys.argv[1]}
    INS_ROW = '''<tr>
    <td><%(tag)s style="color: #6aa84f">{0}</%(tag)s></td>
    <td><%(tag)s style="color: #6aa84f">{1}</%(tag)s></td>
    </tr>''' % {'tag': sys.argv[2]}
    main()
