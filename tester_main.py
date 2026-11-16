# -*- coding: utf-8 -*-
"""Deadly District — точка входа сборки для тестера (DeadlyDistrict-tester.exe).

Та же игра, но с меню тестера на F9 (game/tester.py) и со своей папкой настроек и сохранений.
В обычную сборку не входит ни этот файл, ни game/tester.py.
"""
import main

if __name__ == '__main__':
    if not main.enable_tester():
        # сборка для тестера без меню тестера — ошибка сборки; обычной игрой она не притворяется
        main._message_box('В этой сборке нет меню тестера (game/tester.py). Сборку нужно пересобрать.')
        raise SystemExit('tester menu (game/tester.py) is missing from this build')
    main.main()
