# -*- coding: utf-8 -*-
"""Шрифты интерфейса: из вариативных шрифтов Google Fonts делаются обычные файлы нужной насыщенности,
в которых оставлены только латиница, кириллица и знаки препинания (так они в десять раз меньше).

    pip install fonttools
    python tools/gen_fonts.py fetch        # скачать исходники в .cache/model_src/gfonts (git)
    python tools/gen_fonts.py              # записать assets/fonts/*.ttf и тексты лицензий

Inter — основной текст и числа, Oswald — заголовки и подписи прописными, Caveat — рукописные надписи.
Все три распространяются по SIL Open Font License.
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '.cache', 'model_src', 'gfonts')
OUT = os.path.join(ROOT, 'assets', 'fonts')
REPO = 'https://github.com/google/fonts'

# файл в игре -> (исходник, оси)
FONTS = {
    'Inter-Medium.ttf': ('ofl/inter/Inter[opsz,wght].ttf', dict(wght=500, opsz=20)),
    'Inter-Bold.ttf': ('ofl/inter/Inter[opsz,wght].ttf', dict(wght=700, opsz=20)),
    'Oswald-Medium.ttf': ('ofl/oswald/Oswald[wght].ttf', dict(wght=500)),
    'Oswald-Bold.ttf': ('ofl/oswald/Oswald[wght].ttf', dict(wght=700)),
    'Caveat-Bold.ttf': ('ofl/caveat/Caveat[wght].ttf', dict(wght=700)),
}
LICENSES = {'OFL-Inter.txt': 'ofl/inter/OFL.txt', 'OFL-Oswald.txt': 'ofl/oswald/OFL.txt',
            'OFL-Caveat.txt': 'ofl/caveat/OFL.txt'}

UNICODES = (list(range(0x20, 0x7F)) + list(range(0xA0, 0xC0)) + [0xD7, 0xF7] + list(range(0x400, 0x460)) +
            [0x490, 0x491, 0x2009, 0x200A] + list(range(0x2010, 0x2027)) + [0x2030, 0x2032, 0x2033, 0x2039, 0x203A, 0x20BD, 0x2116,
                                                              0x2022, 0x2190, 0x2191, 0x2192, 0x2193, 0x2212, 0x2713])


def fetch():
    if not os.path.isdir(os.path.join(SRC, '.git')):
        os.makedirs(os.path.dirname(SRC), exist_ok=True)
        subprocess.check_call(['git', 'clone', '--depth', '1', '--filter=blob:none', '--sparse', REPO, SRC])
    subprocess.check_call(['git', 'sparse-checkout', 'set', '--no-cone', '/ofl/inter/', '/ofl/oswald/', '/ofl/caveat/'],
                          cwd=SRC)


def main():
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    from fontTools import subset
    os.makedirs(OUT, exist_ok=True)
    for name, (src, axes) in sorted(FONTS.items()):
        f = TTFont(os.path.join(SRC, src))
        f = instancer.instantiateVariableFont(f, axes, inplace=False)
        opt = subset.Options()
        opt.layout_features = ['kern', 'liga', 'tnum', 'case', 'locl']
        opt.name_IDs = ['*']
        opt.notdef_outline = True
        opt.hinting = False
        sub = subset.Subsetter(opt)
        sub.populate(unicodes=UNICODES)
        sub.subset(f)
        path = os.path.join(OUT, name)
        f.save(path)
        have = set(f.getBestCmap())
        miss = [hex(u) for u in UNICODES if u not in have]
        print('%-20s %6.1f КБ, знаков %d%s' % (name, os.path.getsize(path) / 1024.0, len(have),
                                               (', нет: ' + ' '.join(miss[:12])) if miss else ''))
    for name, src in LICENSES.items():
        shutil.copyfile(os.path.join(SRC, src), os.path.join(OUT, name))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'fetch':
        fetch()
    else:
        main()
