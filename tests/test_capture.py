"""Window capture integration, failure fallback and macOS launcher detection without a game."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ['MAPLE_EXP_DATA'] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import maple_exp as m
from capture import WindowCapture, capture_window
from harness import Checks, Pipeline, Scene

c = Checks()

with Pipeline(gh=7) as p:
    p.show(Scene(gh=7).inventory())
    p.platform.captures_window_alone = True
    requests = []
    def picture(handle, *rect):
        requests.append((handle, rect))
        bgr = p.platform.game.image
        return np.dstack((bgr, np.full(bgr.shape[:2], 255, np.uint8)))
    p.platform.capture_window = picture
    p.reader.own_rect = p.platform.game.rect  # the overlay covers the entire game
    first = p.poll()
    second = p.poll()
    c.check('window capture reads EXP even under the overlay', first.confident and second.confident)
    c.check('one window capture per look, no screen grabs', len(requests) == 2 and p.screen.grabs == 0)
    c.check('diagnostics name the window source', p.reader.diagnostics()['capture'] == 'window')
    p.show(Scene(gh=7).exp(68681, 71.76).inventory())
    c.check('each look gets a fresh window frame', p.poll().candidates == [(68681, 71.76)])
    for name, result in [('none', None), ('wrong size', np.zeros((20, 20, 4), np.uint8)),
                         ('wrong type', np.zeros((720, 1280, 4), np.float32)), ('exception', OSError('capture failed'))]:
        def broken(*args):
            if isinstance(result, Exception):
                raise result
            return result
        p.platform.capture_window = broken
        got = p.poll()
        c.check(f'{name}: falls back and never reads through its own window',
                not got.confident and not p.reader.capture.sees_through_windows and 'cover' in got.where.lower())
    p.platform.capture_window = picture
    c.check('capture recovers after a failure', p.poll().confident)
    p.reader.use_region({'left': 100, 'top': 60, 'width': 1280, 'height': 720})
    before = len(requests)
    p.poll()
    c.check('selected-area mode stays on screen capture', len(requests) == before and not p.reader.capture.sees_through_windows)

frame = np.zeros((80, 100, 4), np.uint8)
frame[:, :, :3] = (12, 34, 56)
cap = WindowCapture((-100, -80, 100, 80), frame)
shot = cap.grab(-120, -100, 50, 40)
c.check('negative display coordinates clip with the correct origin',
        shot[1:] == (-100, -80) and shot[0].shape == (20, 30, 3) and tuple(shot[0][0, 0]) == (12, 34, 56))
c.check('outside the window never falls back to unrelated desktop pixels', cap.grab(10, 10, 20, 20) is None)

# A report must use a fresh window frame, and mask the fallback even after a window-only look.
with Pipeline(gh=7) as p:
    p.show(Scene(gh=7))
    p.platform.captures_window_alone = True
    p.platform.capture_window = lambda *args: np.full((720, 1280, 4), 200, np.uint8)
    p.poll()
    app = m.App.__new__(m.App)
    app.reader = p.reader
    with patch.object(m.mss, 'mss', side_effect=AssertionError('screen must not be opened')):
        path = app._save_report_screen()
    c.check('bug-report picture uses window capture without opening screen capture', path is not None and path.exists())
    p.reader.own_rect = p.platform.game.rect
    p.platform.capture_window = lambda *args: None
    with patch.object(m.mss, 'mss', return_value=p.screen):
        path = app._save_report_screen()
    from PIL import Image
    c.check('bug-report fallback masks the overlay despite a previous window capture',
            path is not None and np.asarray(Image.open(path)).max() == 0)

if sys.platform == 'darwin':
    from platforms import macos
    W = macos.MacWindow
    game = W(7, 12345, 'MapleStory Classic World', '', 26, (0, 38, 1280, 720), True)
    tiny = W(8, 12345, 'MapleStory Launcher', '', 0, (0, 0, 1, 1), True)
    c.check('Nexon game at layer 26 is accepted', macos.is_game(game, 99))
    c.check('popup layer and title-only high layers are rejected',
            not macos.is_game(game._replace(layer=101), 99)
            and not macos.is_game(game._replace(owner='wine64-preloader', title='MapleStory'), 99))
    def listing(option=None, number=0):
        return [w for w in (tiny, game) if not number or w.number == number]
    with patch.object(macos, 'window_list', side_effect=listing):
        c.check('launcher tiny window is skipped in favor of the game', m.PLATFORM.find_game_window() == 7)
    with patch.object(macos, 'window_list', return_value=[tiny]):
        c.check('tiny launcher alone is not a game window', m.PLATFORM.find_game_window() is None)
    with patch.object(macos, '_window_capture_api', side_effect=AttributeError('API removed')):
        c.check('missing deprecated API falls back without breaking imports', capture_window(m.PLATFORM, 7, game.rect) is None)

    # Native buffers can have padded rows and must be copied before CF objects are released.
    import ctypes
    raw = (ctypes.c_ubyte * 96)(*range(96))
    released = []
    api = {
        '_CreateImage': lambda *args: 1,
        '_ImageInfo': lambda image: 0x2002,
        '_ImageWidth': lambda image: 10,
        '_ImageHeight': lambda image: 2,
        '_ImageBits': lambda image: 32,
        '_ImageRowBytes': lambda image: 48,
        '_ImageData': lambda image: 3,
        '_CopyData': lambda provider: 2,
        '_DataLength': lambda data: 96,
        '_DataBytes': lambda data: ctypes.addressof(raw),
    }
    with patch.object(macos, '_window_capture_api', return_value=api), patch.object(macos, '_CFRelease', side_effect=released.append):
        got = m.PLATFORM.capture_window(7, 0, 0, 10, 2)
        raw[0] = 255
        c.check('native padded rows are copied before both CF objects are released',
                got.shape == (2, 10, 4) and got[0, 0, 0] == 0 and got[1, 0, 0] == 48 and released == [2, 1])
        released.clear()
        api['_DataLength'] = lambda data: 4
        c.check('truncated native buffer is rejected and resources released',
                m.PLATFORM.capture_window(7, 0, 0, 10, 2) is None and released == [2, 1])
        released.clear()
        api['_CreateImage'] = lambda *args: None
        c.check('null native image returns unavailable without releasing invalid handles',
                m.PLATFORM.capture_window(7, 0, 0, 10, 2) is None and not released)

c.done()
