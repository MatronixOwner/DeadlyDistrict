# -*- coding: utf-8 -*-
"""Deadly District — точка входа сборки для тестера (DeadlyDistrict-tester.exe).

Та же игра, но с меню тестера на F9 (game/tester.py) и со своей папкой настроек и сохранений.
В обычную сборку не входит ни этот файл, ни game/tester.py.
"""
import main

if __name__ == '__main__':
    main.enable_tester()
    main.main()
