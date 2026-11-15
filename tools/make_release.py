# -*- coding: utf-8 -*-
"""Собрать приложение для Windows и упаковать его в release/DeadlyDistrict-win64.zip.

    python tools/make_release.py            собрать заново и упаковать
    python tools/make_release.py --no-build упаковать уже собранное из build/win_amd64
"""
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, 'build', 'win_amd64')
OUT = os.path.join(ROOT, 'release', 'DeadlyDistrict-win64.zip')
TOP = 'DeadlyDistrict'

README_TXT = u"""DEADLY DISTRICT — «Гиблый район»
Криминальный боевик с открытым миром в духе GTA III.

КАК ЗАПУСТИТЬ
  Распакуйте архив целиком и запустите DeadlyDistrict.exe.
  Нужна 64-разрядная Windows 10 или 11. Устанавливать ничего не требуется.
  Файл exe не работает отдельно от соседних файлов (*.dll и папка assets).

  Если Windows покажет окно «Система Windows защитила ваш компьютер»,
  нажмите «Подробнее», затем «Выполнить в любом случае»: у сборки нет
  цифровой подписи.

УПРАВЛЕНИЕ
  Пешком
    W A S D              движение
    Мышь                 обзор и прицел
    Shift                бег
    Пробел               прыжок
    Левая кнопка мыши    удар или выстрел
    Правая кнопка мыши   точный прицел
    Колесо, Q / E, 1-9   выбор оружия
    F или Enter          сесть в машину (чужую — угнать)

  За рулём
    W / S                газ, тормоз и задний ход
    A / D                руль
    Пробел               ручной тормоз
    Левая кнопка мыши    стрельба из окна (пистолет, «Узи»)
    H                    сигнал или сирена
    R                    радио
    B                    взгляд назад
    T                    подработка в такси (сидя в такси)
    F                    выйти из машины

  Общее
    C                    дальность камеры
    Esc или P            пауза, карта, статистика, настройки
    F12                  снимок экрана

С ЧЕГО НАЧАТЬ
  Буква «В» на радаре — гараж Вано, там дают первое задание.
  Синий маркер у общаги — сохранение игры.
  Звёзды под счётчиком денег — розыск: скройтесь из виду, подберите
  значок-взятку или перекрасьте машину в покрасочной.

ЕСЛИ ИГРА НЕ ЗАПУСКАЕТСЯ
  Настройки, сохранения, снимки экрана и журналы лежат в папке
  %LOCALAPPDATA%\\DeadlyDistrict (вставьте путь в адресную строку Проводника).
  Причина сбоя записывается в файлы output.log и crash.log.
  Чтобы сбросить настройки, удалите там файл settings.json.

Исходный код: https://github.com/MatronixOwner/DeadlyDistrict
"""


def main():
    if '--no-build' not in sys.argv:
        shutil.rmtree(os.path.join(ROOT, 'build'), ignore_errors=True)
        subprocess.check_call([sys.executable, 'setup.py', 'build_apps'], cwd=ROOT)
    exe = os.path.join(BUILD, 'DeadlyDistrict.exe')
    if not os.path.isfile(exe):
        sys.exit('не найден %s — сначала выполните сборку' % exe)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    n = 0
    total = 0
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        # BOM нужен, чтобы «Блокнот» старых версий Windows верно показал кириллицу
        z.writestr(TOP + '/README.txt', (u'\ufeff' + README_TXT.replace('\n', '\r\n')).encode('utf-8'))
        for base, dirs, files in os.walk(BUILD):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(base, name)
                rel = os.path.relpath(path, BUILD).replace(os.sep, '/')
                z.write(path, TOP + '/' + rel)
                n += 1
                total += os.path.getsize(path)
    print('%s: %d файлов, %.1f МБ без сжатия, архив %.1f МБ' % (
        os.path.relpath(OUT, ROOT), n, total / 1e6, os.path.getsize(OUT) / 1e6))


if __name__ == '__main__':
    main()
