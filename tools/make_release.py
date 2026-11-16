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
    Shift                закись азота (если стоит на машине)
    Левая кнопка мыши    стрельба на ходу (пистолеты, «Узи»)
    H                    сигнал или сирена
    R                    радио: следующая станция
    N                    следующая песня
    B                    взгляд назад
    T                    подработка в такси (сидя в такси)
    F                    выйти из машины

  Общее
    Enter                следующая реплика в разговоре
    C                    дальность камеры
    Esc или P            пауза, карта, статистика, настройки
    F12                  снимок экрана

ЭКРАН
  Игра открывается во весь экран в разрешении вашего монитора.
  Окно или полноэкранный режим, разрешение, вид текстур (чёткие или
  сглаженные) и сглаживание краёв выбираются в меню:
  Настройки -> Графика и экран.

СВОЯ МУЗЫКА
  Положите песни (mp3, ogg, wav, flac, m4a) в папку music рядом с игрой.
  В машине клавишей R выберите станцию «Астрахань FM».

С ЧЕГО НАЧАТЬ
  Новая игра открывается короткой сценкой: Enter — следующий кадр,
  Esc — пропустить. После неё Макс остаётся на автобусной остановке,
  и ему звонит брат — Брюс. Так начинается сюжет: «Брат за брата»,
  потом «Жёлтый контейнер». Реплики листает Enter. Куда ехать,
  показывают жёлтая метка на радаре и строка внизу экрана.
  Дом Макса — Сосновая, 12. Синий маркер у кровати — сохранение.
  Гараж у дома: загоните машину внутрь и выйдите — она останется
  вашей вместе с цветом и тюнингом. Мест три.
  Покрасочная (значок баллончика на радаре) — она же ателье: заедьте
  в бокс и остановитесь. Там красят, чинят и ставят тюнинг.
  Жёлтая стрелка у двери — вход: в неё надо войти пешком. Так же
  выходят наружу. С розыском и во время задания в двери не пускают.
  После сюжета открывается подработка: Вано (В), Роза (Р), Захар (З),
  Гром (Г) и Проф (П); Захар и Гром живут за мостами, на других берегах.
  Звёзды под счётчиком денег — розыск: скройтесь из виду, подберите
  значок-взятку или перекрасьте машину в покрасочной.
  На мотоцикле сильный удар выбивает из седла, а пули достаются
  самому ездоку. Вдвоём можно ехать только на том, где есть второе место.

ЕСЛИ ИГРА НЕ ЗАПУСКАЕТСЯ
  Настройки, сохранения, снимки экрана и журналы лежат в папке
  %LOCALAPPDATA%\\DeadlyDistrict (вставьте путь в адресную строку Проводника).
  Причина сбоя записывается в файлы output.log и crash.log.
  Чтобы сбросить настройки (в том числе режим экрана), удалите там
  файл settings.json.

АВТОРЫ МОДЕЛЕЙ И МАТЕРИАЛОВ
  Люди — Elbolilloduro («Characters PSX»), анимация — Mesh2Motion.
  Мебель — Elbolilloduro («Pack of low poly psx style models»).
  Машины — GGBot («PSX Style Cars»), такси — MoiDev (CC-BY-SA-4.0).
  Круизер — Duhgless (CC0), велосипеды — Kenney (CC0), остальная мелкая
  техника собрана кодом игры. Панели меню и HUD — rohhsa («FREEPSXUI», CC0).
  Оружие — Mextie, Ace Spectre, Cemckrc и другие авторы сборника
  M3-org/retro3d-assets; бита, гранаты и бутылка — Quaternius.
  Материалы города и комнат — Classic64 Asset Library (Craig Snedeker).
  Подробности: assets/models/CREDITS.md

Исходный код: https://github.com/MatronixOwner/DeadlyDistrict
"""


MUSIC_TXT = u"""Песни для радиостанции «Астрахань FM»

Положите в эту папку свои музыкальные файлы (mp3, ogg, wav, flac, m4a) — можно с подпапками.
В игре сядьте в машину и клавишей R выберите «Астрахань FM»: песни играют вперемешку.
N — следующая песня. Название берётся из имени файла, например «Глюкоза - Швайне.mp3».

Перезапускать игру не нужно: папка перечитывается, когда вы переключаетесь на станцию.
Пока папка пуста, станция играет музыку из самой игры.
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
        z.writestr(TOP + '/music/Как добавить песни.txt',
                   (u'\ufeff' + MUSIC_TXT.replace('\n', '\r\n')).encode('utf-8'))
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
