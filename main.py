# -*- coding: utf-8 -*-
"""Deadly District — точка входа."""
import os
import sys
import traceback


def _crash_log(text):
    try:
        from game import settings
        path = os.path.join(settings.user_dir(), 'crash.log')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path
    except Exception:
        return None


def main():
    try:
        from game.app import Game
        game = Game()
        game.run()
    except SystemExit:
        raise
    except Exception:
        text = traceback.format_exc()
        sys.stderr.write(text)
        _crash_log(text)
        raise


if __name__ == '__main__':
    main()
