import re
from functools import reduce

Section = tuple[int, int, int, int, int]

def to_alpha(num: int) -> str:
    num += 1 # 0-indexed alpha
    chars = []
    while num > 0:
        num, d = divmod(num, 26)
        if d == 0:
            num, d = num - 1, d + 26
        chars.append(chr(ord('a') + d - 1))
    return ''.join(reversed(chars))

def from_alpha(alpha: str) -> int:
    alpha = alpha.strip().casefold()
    if not alpha.isalpha():
        raise ValueError(alpha)
    return reduce(lambda r, x: r * 26 + x, (ord(c) - ord('a') + 1 for c in alpha)) - 1

ROMAN_VALUES = 1, 4, 5, 9, 10, 40, 50, 90, 100, 400, 500, 900, 1000
ROMAN_LETTERS = 'i', 'iv', 'v', 'ix', 'x', 'xl', 'l', 'xc', 'c', 'cd', 'd', 'cm', 'm'

def to_roman(num: int) -> str:
    num += 1 # 0-indexed alpha
    letters = []
    i = len(ROMAN_VALUES) - 1
    while num > 0:
        x, num = divmod(num, ROMAN_VALUES[i])
        letters.extend([ROMAN_LETTERS[i]] * x)
        i -= 1
    return ''.join(letters)

def from_roman(roman: str) -> int:
    i = len(ROMAN_VALUES) - 1
    num = 0
    while roman and i >= 0:
        while roman.startswith(ROMAN_LETTERS[i]):
            num += ROMAN_VALUES[i]
            roman = roman[len(ROMAN_LETTERS[i]):]
        i -= 1
    return num - 1

def lineno_to_section(lineno: int, lines: list[str]) -> Section:
    if lineno < 0:
        raise ValueError(f'Line {lineno} is before first line 0')
    section = [-1, -1, -1, -1, -1]
    for ln, line in enumerate(lines):
        if re.match(r'^#\s+', line):
            section[0] += 1
            section[1:] = [-1] * 4
        elif re.match(r'^##\s+', line):
            section[1] += 1
            section[2:] = [-1] * 3
        elif re.match(r'^\d+\.\s+', line):
            section[2] += 1
            section[3:] = [-1] * 2
        elif re.match(r'^(    ?|\t)\d+\.\s+', line):
            section[3] += 1
            section[4] = -1
        elif re.match(r'^(    ?|\t){2}\d+\.\s+', line):
            section[4] += 1
        if ln == lineno:
            return (section[0], section[1], section[2], section[3], section[4])
    raise ValueError(f'Line {lineno} is past last line {len(lines) - 1}')

def section_to_lineno(sect: Section, lines: list[str]) -> int:
    section = [-1, -1, -1, -1, -1]
    for ln, line in enumerate(lines):
        if re.match(r'^#\s+', line):
            section[0] += 1
            section[1:] = [-1] * 4
        elif re.match(r'^##\s+', line):
            section[1] += 1
            section[2:] = [-1] * 3
        elif re.match(r'^\d+\.\s+', line):
            section[2] += 1
            section[3:] = [-1] * 2
        elif re.match(r'^(    ?|\t)\d+\.\s+', line):
            section[3] += 1
            section[4] = -1
        elif re.match(r'^(    ?|\t){2}\d+\.\s+', line):
            section[4] += 1
        if tuple(section) == sect:
            return ln
    raise ValueError(f'No such section {sect}')

def section_to_str(section: Section) -> str:
    s = str(section[0])
    if section[1] >= 0:
        s += '.' + str(section[1])
        if section[2] >= 0:
            s += '.' + str(section[2] + 1)
            if section[3] >= 0:
                s += '.' + to_alpha(section[3])
                if section[4] >= 0:
                    s += '.' + to_roman(section[4])
    return s
