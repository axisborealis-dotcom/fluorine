import time
import math
import random
import threading
import ctypes
import win32gui
import win32con
import win32api
import keyboard

running = True
current_part = 1
reset_audio_time = False

class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", ctypes.c_ushort),
        ("nChannels", ctypes.c_ushort),
        ("nSamplesPerSec", ctypes.c_ulong),
        ("nAvgBytesPerSec", ctypes.c_ulong),
        ("nBlockAlign", ctypes.c_ushort),
        ("wBitsPerSample", ctypes.c_ushort),
        ("cbSize", ctypes.c_ushort)
    ]

class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_char_p),
        ("dwBufferLength", ctypes.c_ulong),
        ("dwBytesRecorded", ctypes.c_ulong),
        ("dwUser", ctypes.c_void_p),
        ("dwFlags", ctypes.c_ulong),
        ("dwLoops", ctypes.c_ulong),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_void_p)
    ]

SAMPLE_RATE = 8000
PART_SECONDS = 30
PART_SAMPLES = SAMPLE_RATE * PART_SECONDS
WHDR_BEGINLOOP = 0x4
WHDR_ENDLOOP = 0x8

def _i32(x):
    # JavaScript-style 32-bit signed wrap, so the formulas behave like they do in a bytebeat player
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x & 0x80000000 else x

def _jsmod(a, b):
    # JS % keeps the sign of the dividend; Python's does not
    r = abs(a) % b
    return -r if a < 0 else r

def _sample(part, t):
    if part == 1:
        return (((t * 9) & (t >> 4)) | (t * 5 & t >> 7) | (t * 3 & (t // 1024))) - 1
    if part == 2:
        return _i32(t << 2 ^ t >> 4 ^ t << 4 & t >> 8) | (_i32(t << 1) & (-t >> 4))
    if part == 3:
        return ((_i32(t * (t >> 8 | t >> 9)) & 46 & t >> 8)) ^ (t & t >> 13 | t >> 6)
    if part == 4:
        s = (t >> 6) & 3
        return (t >> 6) ^ (t & (t >> 9)) ^ (t >> 12) | _jsmod(_i32(t << s) ^ (-t) & ((-t) >> 13), 128) ^ ((-t) >> 1)
    if part == 5:
        return _i32(((t & (t >> 8)) | (t & (t >> 13))) * (1 + ((t >> 14) & 3))) | (t >> 7)
    x1 = (t * 2) & 0xFFFFFFFF
    f1 = ((x1 // 8) >> ((((x1 >> 9) * x1) & 0xFFFFFFFF) // (((x1 >> 14) & 3) + 4) & 31)) & 255
    x2 = (t * 2 + 1) & 0xFFFFFFFF
    f2 = ((x2 // 8) >> ((((x2 >> 9) * x2) & 0xFFFFFFFF) // (((x2 >> 14) & 3) + 4) & 31)) & 255
    u = f1 | (f2 << 8)
    if u & 0x8000:
        u -= 0x10000
    return int((u / 32768.0 + 1.0) * 127.5)

# Every part starts its formula at t = 0.
PART_START_T = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}

def render_part(part):
    t0 = PART_START_T[part]
    return bytes(_sample(part, t0 + i) & 255 for i in range(PART_SAMPLES))

part_audio = {}

def audio_bytebeat_engine():
    # The old engine generated samples live in Python and fed winmm with sleep()
    # timing. With the GDI loop fighting for the GIL, the heavier formulas could
    # not keep up and played as gaps/crackle. Now every part is rendered ahead of
    # time and handed to winmm as one looping buffer, so playback is glitch-free.
    global running
    HWAVEOUT = ctypes.c_void_p()
    wfx = WAVEFORMATEX(1, 1, SAMPLE_RATE, SAMPLE_RATE, 1, 8, 0)
    if ctypes.windll.winmm.waveOutOpen(ctypes.byref(HWAVEOUT), -1, ctypes.byref(wfx), 0, 0, 0) != 0:
        return

    def prerender():
        for p in range(2, 7):
            if not running:
                return
            part_audio[p] = render_part(p)
    threading.Thread(target=prerender, daemon=True).start()

    playing = None
    whdr = None
    try:
        while running:
            part = current_part
            if part != playing and part in part_audio:
                ctypes.windll.winmm.waveOutReset(HWAVEOUT)
                if whdr is not None:
                    ctypes.windll.winmm.waveOutUnprepareHeader(HWAVEOUT, ctypes.byref(whdr), ctypes.sizeof(WAVEHDR))
                data = part_audio[part]
                whdr = WAVEHDR()
                whdr.lpData = ctypes.c_char_p(data)
                whdr.dwBufferLength = len(data)
                whdr.dwFlags = WHDR_BEGINLOOP | WHDR_ENDLOOP
                whdr.dwLoops = 0xFFFFFFFF
                ctypes.windll.winmm.waveOutPrepareHeader(HWAVEOUT, ctypes.byref(whdr), ctypes.sizeof(WAVEHDR))
                ctypes.windll.winmm.waveOutWrite(HWAVEOUT, ctypes.byref(whdr), ctypes.sizeof(WAVEHDR))
                playing = part
            time.sleep(0.01)
    except Exception:
        pass
    finally:
        ctypes.windll.winmm.waveOutReset(HWAVEOUT)
        if whdr is not None:
            ctypes.windll.winmm.waveOutUnprepareHeader(HWAVEOUT, ctypes.byref(whdr), ctypes.sizeof(WAVEHDR))
        ctypes.windll.winmm.waveOutClose(HWAVEOUT)

def cursor_seizure_loop():
    # Hijacks the mouse: the cursor wanders toward random spots on the virtual
    # screen while violently jittering around its path. ESC still ends it all.
    sl = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
    st = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
    sw = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
    sh = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
    ax, ay = win32api.GetCursorPos()   # anchor: seize around this, no drift
    last = (ax, ay)
    while running:
        cx, cy = win32api.GetCursorPos()
        # If the cursor is somewhere we didn't put it, the user moved it: follow.
        if (cx, cy) != last:
            ax, ay = cx, cy
        jitter = 20 if random.randint(1, 6) > 1 else 40
        jx = int(ax + random.randint(-jitter, jitter))
        jy = int(ay + random.randint(-jitter, jitter))
        jx = max(sl, min(jx, sl + sw - 1))
        jy = max(st, min(jy, st + sh - 1))
        try:
            win32api.SetCursorPos((jx, jy))
        except Exception:
            pass
        last = (jx, jy)
        time.sleep(0.03)

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
GA_ROOT = 2

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]

def _window_frame(hwnd):
    # GetWindowRect includes the invisible resize border on Win10/11, which puts
    # the caption buttons several pixels off. The DWM frame bounds are exact.
    r = RECT()
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(
            ctypes.c_void_p(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(r), ctypes.sizeof(r)) == 0:
        return r.left, r.top, r.right, r.bottom
    return win32gui.GetWindowRect(hwnd)

def _is_cloaked(hwnd):
    c = ctypes.c_int(0)
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(
            ctypes.c_void_p(hwnd), DWMWA_CLOAKED,
            ctypes.byref(c), ctypes.sizeof(c)) == 0:
        return c.value != 0
    return False

def _window_scale(hwnd):
    try:
        return ctypes.windll.user32.GetDpiForWindow(ctypes.c_void_p(hwnd)) / 96.0
    except Exception:
        return 1.0

def get_titlebar_buttons_regions(screen_left, screen_top):
    # Returns screen-local cells covering the minimize/maximize/close group of
    # every visible top-level window, so the pixelation can be punched out there
    # and the X stays readable and clickable.
    regions = []
    def enum_windows_callback(hwnd, lParam):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
            return True
        if _is_cloaked(hwnd):
            return True
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        if not (style & win32con.WS_CAPTION):
            return True

        w_left, w_top, w_right, w_bottom = _window_frame(hwnd)
        if (w_right - w_left) <= 50 or (w_bottom - w_top) <= 50:
            return True

        scale = _window_scale(hwnd)
        # Win11 caption buttons are ~46x32 DIP each; the old SM_CXSIZE metric is
        # far too narrow and clipped the close button in half.
        btn_w = max(int(46 * scale), win32api.GetSystemMetrics(win32con.SM_CXSIZE))
        btn_h = max(int(32 * scale), win32api.GetSystemMetrics(win32con.SM_CYSIZE))
        pad = max(2, int(2 * scale))

        strip_top = w_top - pad
        strip_bottom = w_top + btn_h + pad
        # Walk the three buttons right-to-left and keep only the cells that this
        # window actually owns on screen, so a window stacked on top of it does
        # not get a sharp rectangle stamped over it.
        for n in range(3):
            cx2 = w_right - (n * btn_w) + pad
            cx1 = cx2 - btn_w - (pad * 2)
            probe_x = (cx1 + cx2) // 2
            probe_y = (strip_top + strip_bottom) // 2
            hit = win32gui.WindowFromPoint((probe_x, probe_y))
            if not hit:
                continue
            if ctypes.windll.user32.GetAncestor(hit, GA_ROOT) != hwnd:
                continue
            regions.append((cx1 - screen_left, strip_top - screen_top,
                            cx2 - screen_left, strip_bottom - screen_top))
        return True
    win32gui.EnumWindows(enum_windows_callback, 0)
    return regions

def gdi_animation_loop():
    global running, current_part, reset_audio_time
    hdc_screen = win32gui.GetDC(0)
    h_icon = win32gui.LoadIcon(0, win32con.IDI_HAND)

    screen_left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
    screen_top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
    screen_width = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
    screen_height = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)

    hdc_mem = win32gui.CreateCompatibleDC(hdc_screen)
    h_bm_mem = win32gui.CreateCompatibleBitmap(hdc_screen, screen_width, screen_height)
    win32gui.SelectObject(hdc_mem, h_bm_mem)

    hdc_live_capture = win32gui.CreateCompatibleDC(hdc_screen)
    h_bm_live = win32gui.CreateCompatibleBitmap(hdc_screen, screen_width, screen_height)
    win32gui.SelectObject(hdc_live_capture, h_bm_live)

    win32gui.BitBlt(hdc_mem, 0, 0, screen_width, screen_height, hdc_screen, screen_left, screen_top, win32con.SRCCOPY)

    ripple_time = 0.0
    color_cycle = 0.0
    button_regions = []
    button_regions_time = 0.0
    start_time = time.time()

    while running:
        if keyboard.is_pressed('escape'):
            running = False
            break

        elapsed_time = time.time() - start_time

        if current_part == 1 and elapsed_time >= 30.0:
            current_part = 2
            reset_audio_time = True
            win32gui.BitBlt(hdc_mem, 0, 0, screen_width, screen_height, hdc_screen, screen_left, screen_top, win32con.SRCCOPY)
        elif current_part == 2 and elapsed_time >= 60.0:
            current_part = 3
            reset_audio_time = True
            win32gui.BitBlt(hdc_mem, 0, 0, screen_width, screen_height, hdc_screen, screen_left, screen_top, win32con.SRCCOPY)
        elif current_part == 3 and elapsed_time >= 90.0:
            current_part = 4
            reset_audio_time = True
        elif current_part == 4 and elapsed_time >= 120.0:
            current_part = 5
            reset_audio_time = True
        elif current_part == 5 and elapsed_time >= 150.0:
            current_part = 6
            reset_audio_time = True

        mx, my = win32api.GetCursorPos()
        mx_local = mx - screen_left
        my_local = my - screen_top

        if current_part == 1:
            win32gui.BitBlt(hdc_live_capture, 0, 0, screen_width, screen_height, hdc_screen, screen_left, screen_top, win32con.SRCCOPY)
            win32gui.DrawIconEx(hdc_live_capture, mx_local - 16, my_local - 16, h_icon, 32, 32, 0, 0, win32con.DI_NORMAL)

            pixel_size = 4
            win32gui.StretchBlt(hdc_mem, 0, 0, screen_width // pixel_size, screen_height // pixel_size, hdc_live_capture, 0, 0, screen_width, screen_height, win32con.SRCCOPY)
            win32gui.StretchBlt(hdc_screen, screen_left, screen_top, screen_width, screen_height, hdc_mem, 0, 0, screen_width // pixel_size, screen_height // pixel_size, win32con.SRCCOPY)

            # Dynamic exclusion layout masks protect close button groups.
            # EnumWindows + DWM queries are not free, so refresh the layout a few
            # times a second and reuse it for the frames in between.
            now = time.time()
            if now - button_regions_time > 0.15:
                button_regions = get_titlebar_buttons_regions(screen_left, screen_top)
                button_regions_time = now
            for box in button_regions:
                bx1, by1, bx2, by2 = box
                # Clamp to the virtual screen instead of dropping the whole cell,
                # so a button group hanging off an edge is still restored.
                bx1 = max(0, min(bx1, screen_width))
                by1 = max(0, min(by1, screen_height))
                bx2 = max(0, min(bx2, screen_width))
                by2 = max(0, min(by2, screen_height))
                bw = bx2 - bx1
                bh = by2 - by1
                if bw > 0 and bh > 0:
                    win32gui.BitBlt(hdc_screen, screen_left + bx1, screen_top + by1, bw, bh, hdc_live_capture, bx1, by1, win32con.SRCCOPY)

        elif current_part == 2:
            win32gui.DrawIconEx(hdc_mem, mx_local - 16, my_local - 16, h_icon, 32, 32, 0, 0, win32con.DI_NORMAL)
            if random.randint(1, 40) == 1:
                ix = random.randint(0, screen_width - 250)
                iy = random.randint(0, screen_height - 250)
                win32gui.BitBlt(hdc_mem, ix, iy, 250, 250, hdc_mem, ix, iy, win32con.NOTSRCCOPY)
            ripple_time += 0.12
            slice_w = 4
            for x in range(0, screen_width, slice_w):
                y_offset = int(math.sin((x / 15.0) - ripple_time) * 45.0)
                win32gui.BitBlt(hdc_screen, screen_left + x, screen_top + y_offset, slice_w, screen_height, hdc_mem, x, 0, win32con.SRCCOPY)

        elif current_part == 3:
            win32gui.DrawIconEx(hdc_mem, mx_local - 16, my_local - 16, h_icon, 32, 32, 0, 0, win32con.DI_NORMAL)
            for _ in range(3):
                block_w = random.randint(100, 400)
                block_h = random.randint(50, 150)
                src_x = random.randint(0, screen_width - block_w)
                src_y = random.randint(0, screen_height - block_h)
                shift_x = random.choice([-15, -10, 10, 15])
                dest_x = (src_x + shift_x) % screen_width
                win32gui.BitBlt(hdc_mem, dest_x, src_y, block_w, block_h, hdc_mem, src_x, src_y, win32con.SRCCOPY)
            if random.randint(1, 10) == 1:
                gx = random.randint(0, screen_width - 300)
                gy = random.randint(0, screen_height - 300)
                win32gui.BitBlt(hdc_mem, gx, gy, 300, 300, hdc_mem, gx, gy, win32con.SRCINVERT)
            win32gui.BitBlt(hdc_screen, screen_left, screen_top, screen_width, screen_height, hdc_mem, 0, 0, win32con.SRCCOPY)

        elif current_part == 4:
            win32gui.DrawIconEx(hdc_mem, mx_local - 16, my_local - 16, h_icon, 32, 32, 0, 0, win32con.DI_NORMAL)
            slice_h = 16
            for y in range(0, screen_height, slice_h):
                shift_r = int(math.sin(y / 30.0 + time.time() * 5) * 12)
                shift_g = int(math.cos(y / 20.0 + time.time() * 3) * 8)
                win32gui.BitBlt(hdc_mem, shift_r, y, screen_width, slice_h, hdc_mem, 0, y, win32con.SRCINVERT)
                win32gui.BitBlt(hdc_mem, shift_g, y, screen_width, slice_h, hdc_mem, 0, y, win32con.SRCPAINT)
            if random.randint(1, 25) == 1:
                win32gui.BitBlt(hdc_mem, 0, 0, screen_width, screen_height, hdc_mem, 0, 0, win32con.DSTINVERT)
            win32gui.BitBlt(hdc_screen, screen_left, screen_top, screen_width, screen_height, hdc_mem, 0, 0, win32con.SRCCOPY)

        elif current_part == 5:
            win32gui.BitBlt(hdc_mem, 0, 0, screen_width, screen_height, hdc_screen, screen_left, screen_top, win32con.SRCCOPY)
            win32gui.DrawIconEx(hdc_mem, mx_local - 16, my_local - 16, h_icon, 32, 32, 0, 0, win32con.DI_NORMAL)
            color_cycle += 0.03
            r = int((math.sin(color_cycle + 0) * 127) + 128)
            g = int((math.sin(color_cycle + 2) * 127) + 128)
            b = int((math.sin(color_cycle + 4) * 127) + 128)
            brush = win32gui.CreateSolidBrush(win32api.RGB(r, g, b))
            old_brush = win32gui.SelectObject(hdc_mem, brush)
            win32gui.PatBlt(hdc_mem, 0, 0, screen_width, screen_height, win32con.PATINVERT)
            win32gui.SelectObject(hdc_mem, old_brush)
            win32gui.DeleteObject(brush)
            win32gui.BitBlt(hdc_screen, screen_left, screen_top, screen_width, screen_height, hdc_mem, 0, 0, win32con.SRCCOPY)

        else:
            win32gui.BitBlt(hdc_mem, 0, 0, screen_width, screen_height, hdc_screen, screen_left, screen_top, win32con.SRCCOPY)
            win32gui.DrawIconEx(hdc_mem, mx_local - 16, my_local - 16, h_icon, 32, 32, 0, 0, win32con.DI_NORMAL)

            fr = random.randint(0, 255)
            fg = random.randint(0, 255)
            fb = random.randint(0, 255)
            flash_brush = win32gui.CreateSolidBrush(win32api.RGB(fr, fg, fb))
            old_brush = win32gui.SelectObject(hdc_mem, flash_brush)
            win32gui.PatBlt(hdc_mem, 0, 0, screen_width, screen_height, win32con.PATINVERT)
            win32gui.SelectObject(hdc_mem, old_brush)
            win32gui.DeleteObject(flash_brush)

            if random.randint(1, 2) == 1:
                win32gui.BitBlt(hdc_mem, 0, 0, screen_width, screen_height, hdc_mem, 0, 0, win32con.DSTINVERT)
            win32gui.BitBlt(hdc_screen, screen_left, screen_top, screen_width, screen_height, hdc_mem, 0, 0, win32con.SRCCOPY)

        time.sleep(0.01)

    win32gui.DeleteObject(h_bm_mem)
    win32gui.DeleteDC(hdc_mem)
    win32gui.DeleteObject(h_bm_live)
    win32gui.DeleteDC(hdc_live_capture)
    win32gui.ReleaseDC(0, hdc_screen)

if __name__ == "__main__":
    part_audio[1] = render_part(1)
    audio_thread = threading.Thread(target=audio_bytebeat_engine, daemon=True)
    audio_thread.start()
    threading.Thread(target=cursor_seizure_loop, daemon=True).start()
    try:
        gdi_animation_loop()
    except Exception:
        pass
    finally:
        running = False
        time.sleep(0.15)
        win32gui.RedrawWindow(0, None, None, win32con.RDW_INVALIDATE | win32con.RDW_ERASE | win32con.RDW_ALLCHILDREN | win32con.RDW_UPDATENOW)
        ctypes.windll.user32.SystemParametersInfoW(win32con.SPI_SETDESKWALLPAPER, 0, None, win32con.SPIF_SENDCHANGE)
