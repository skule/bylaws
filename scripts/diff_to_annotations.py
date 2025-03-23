from __future__ import annotations
from dataclasses import dataclass, field
from glob import glob
import io
from pathlib import Path
import re
import sys
from typing import Literal, TextIO, Iterable, Self, assert_never

from mds_to_html import Section, get_data
from lineno_to_section import section_to_lineno, Section as _Section, section_to_str

@dataclass
class Hunk:
    del_start: int
    del_count: int
    add_start: int
    add_count: int
    del_lines: list[str] = field(default_factory=list)
    add_lines: list[str] = field(default_factory=list)

@dataclass
class File:
    name: str
    hunks: list[Hunk] = field(default_factory=list)
    add_linenos: set[int] = field(default_factory=set)

Prefix = tuple[int, ...]

@dataclass(frozen=True)
class FrozenSection:
    title: str
    body: tuple[Self, ...]

    @classmethod
    def from_section(cls, section: Section) -> Self:
        title = section['title']
        body = tuple(FrozenSection.from_section(s) for s in section['body'])
        return cls(title, body)

    def __getitem__(self, index: int | Prefix) -> Self:
        if isinstance(index, int):
            return self.body[index]
        for i in index:
            self = self.body[i]
        return self

def lines_to_chapters(lines: Iterable[str]) -> tuple[dict[str, str], tuple[FrozenSection, ...]]:
    sio = io.StringIO()
    sio.writelines(line + '\n' for line in lines)
    sio.seek(0)
    meta, chapters = get_data(sio)
    return meta, tuple(FrozenSection.from_section(chapter) for chapter in chapters)

def update_mod(file: File):
    for hunk in file.hunks:
        for ln, line in enumerate(hunk.add_lines, start=hunk.add_start):
            if line[0] != ' ':
                file.add_linenos.add(ln)

def gather_diff(f: TextIO) -> list[File]:
    files: list[File] = []
    for line in f:
        if re.match(r'(---|\+\+\+) (a/|b/|/dev/null)', line):
            continue # these interfere with regular add/del prefixes
        if m := re.match(r'diff --git a/.+? b/(.+)', line):
            files.append(File(m.group(1)))
        elif m := re.match(r'@@ -?(\d+),(\d+) \+?(\d+),(\d+) @@', line):
            files[-1].hunks.append(Hunk(int(m.group(1)), int(m.group(2)),
                                        int(m.group(3)), int(m.group(4))))
        elif line[0] == ' ':
            files[-1].hunks[-1].del_lines.append(line.rstrip('\n'))
            files[-1].hunks[-1].add_lines.append(line.rstrip('\n'))
        elif line[0] == '-':
            files[-1].hunks[-1].del_lines.append(line.rstrip('\n'))
        elif line[0] == '+':
            files[-1].hunks[-1].add_lines.append(line.rstrip('\n'))
    for file in files:
        update_mod(file)
    return files

def gather_crossrefs(
    body: tuple[FrozenSection, ...], file: str, prefix: Prefix = ()
) -> Iterable[tuple[str, Prefix, str, Prefix]]:
    for i, section in enumerate(body):
        _prefix = (*prefix, i)
        for m in re.finditer(r'<a href="([^"#]*\.html)?#(\d+(?:-\d+)*)">', section.title):
            if m.group(1):
                href = str((Path(file).parent / Path(m.group(1).replace('.html', '.md'))).resolve().relative_to(Path.cwd()))
            else:
                href = file
            sect = tuple(map(int, m.group(2).split('-')))
            yield file, _prefix, href, sect
        yield from gather_crossrefs(section.body, file, _prefix)

def p2s(prefix: Prefix) -> _Section:
    prefix += (-1,) * (5 - len(prefix))
    return (prefix[0], prefix[1], prefix[2], prefix[3], prefix[4])

def mknotice[T](level: T, df: str, ds: Prefix, sf: str, ss: Prefix,
                files: dict[str, list[str]]) -> tuple[T, str, str, str, str, str, str]:
    try:
        sl = str(section_to_lineno(p2s(ss), files[sf]) + 1)
    except ValueError:
        sl = '??'
    try:
        dl = str(section_to_lineno(p2s(ds), files[df]) + 1)
    except ValueError:
        dl = '??'
    return (level, sf, section_to_str(p2s(ss)), sl, df, section_to_str(p2s(ds)), dl)

def notices():
    a_files: dict[str, list[str]] = {}
    a_bodies: dict[str, FrozenSection] = {}
    b_files: dict[str, list[str]] = {}
    b_bodies: dict[str, FrozenSection] = {}
    for file in gather_diff(sys.stdin):
        path = file.name
        if 'README' in path or 'LICENSE' in path or 'index' in path:
            continue
        for hunk in file.hunks:
            a_lines = a_files[path] = [line[1:] for line in hunk.del_lines]
            b_lines = b_files[path] = [line[1:] for line in hunk.add_lines]
            _, a_body = lines_to_chapters(a_lines)
            _, b_body = lines_to_chapters(b_lines)
            a_bodies[path] = FrozenSection('', a_body)
            b_bodies[path] = FrozenSection('', b_body)
    for filename in glob('**/*.md', recursive=True):
        path = filename
        if 'README' in path or 'LICENSE' in path or 'index' in path:
            continue
        if path not in a_files and path not in b_files:
            with open(filename, encoding='utf8') as f:
                a_files[path] = b_files[path] = f.readlines()
                _, body = lines_to_chapters(a_files[path])
                a_bodies[path] = b_bodies[path] = FrozenSection('', body)
    a_refses: dict[tuple[str, Prefix], list[tuple[str, Prefix]]] = {}
    for path, body in a_bodies.items():
        for sf, ss, df, ds in gather_crossrefs(body.body, path):
            a_refses.setdefault((df, ds), []).append((sf, ss))
    b_refses: dict[tuple[str, Prefix], list[tuple[str, Prefix]]] = {}
    for path, body in b_bodies.items():
        for sf, ss, df, ds in gather_crossrefs(body.body, path):
            b_refses.setdefault((df, ds), []).append((sf, ss))
    return gen_notices(a_bodies, b_bodies, a_refses, b_refses, b_files)

def gen_notices(
    a_bodies: dict[str, FrozenSection],
    b_bodies: dict[str, FrozenSection],
    a_refses: dict[tuple[str, Prefix], list[tuple[str, Prefix]]],
    b_refses: dict[tuple[str, Prefix], list[tuple[str, Prefix]]],
    files: dict[str, list[str]],
) -> Iterable[tuple[
    Literal['notice-text', 'notice-ref', 'notice-both', 'error', 'warning', 'debug'],
    str, str, str, str, str, str
]]:
    for (df, ds), sources in b_refses.items():
        try:
            b_section = b_bodies[df][ds]
        except IndexError:
            # invalid reference altogether
            for sf, ss in sources:
                yield mknotice('error', df, ds, sf, ss, files)
            continue
        try:
            a_section = a_bodies[df][ds]
        except IndexError:
            # reference to newly added section
            for sf, ss in sources:
                yield mknotice('notice-text', df, ds, sf, ss, files)
            continue
        if a_section.title != b_section.title:
            level = 'warning'
            b_texts = {b_bodies[sf][ss].title for sf, ss in sources}
            try:
                a_sources = a_refses[df, ds]
            except KeyError:
                level = 'notice-ref'
            else:
                a_texts = {a_bodies[sf][ss].title for sf, ss in a_sources}
                if a_texts != b_texts:
                    level = 'notice-both'
            for sf, ss in sources:
                yield mknotice(level, df, ds, sf, ss, files)
        else:
            for sf, ss in sources:
                yield mknotice('debug', df, ds, sf, ss, files)

def main():
    # [ds][fsl]: destination/source file/section/line of reference
    for level, sf, ss, sl, df, ds, dl in notices():
        dest_ref = f'section {ds} ({df}:{dl})'
        if df != sf:
            dest_ref = f'{df} {dest_ref}'
        if level == 'notice-text':
            msg = f'Section {ss}: Reference {dest_ref} is newly added.'
        elif level == 'notice-ref':
            msg = f'Section {ss}: New reference to recently changed text of ' \
                f'{dest_ref}. Make sure it is up to date.'
        elif level == 'notice-both':
            msg = f'Section {ss}: Newly refers to recently changed text of ' \
                f'{dest_ref}. Make sure it is up to date.'
        elif level == 'error':
            msg = f'Section {ss}: Please fix this invalid reference to {dest_ref}.'
        elif level == 'warning':
            msg = f'Section {ss}: Text of {dest_ref} has changed. ' \
                'Make sure your reference to it here is up to date.'
        elif level == 'debug':
            print(f'::debug::{sf}:{sl}: Section {ss}: All good for {dest_ref}.')
            continue
        else:
            assert_never(level)
        print(f'::{level.split('-')[0]} file={sf},line={sl}::{msg}')

if __name__ == '__main__':
    if isinstance(sys.stdin, io.TextIOWrapper):
        sys.stdin.reconfigure(encoding='utf8')
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding='utf8')
    main()
