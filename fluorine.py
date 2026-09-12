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

def audio_bytebeat_engine():
    global running, current_part, reset_audio_time
    t = 0
    sample_rate = 8000
    HWAVEOUT = ctypes.c_void_p()
    wfx = WAVEFORMATEX(1, 1, sample_rate, sample_rate, 1, 8, 0)

    if ctypes.windll.winmm.waveOutOpen(ctypes.byref(HWAVEOUT), -1, ctypes.byref(wfx), 0, 0, 0) != 0:
        return

    chunk_size = 4000
    buffers = []
    try:
        while running:
            if reset_audio_time:
                t = 0
                reset_audio_time = False

            raw_data = bytearray(chunk_size)
            for i in range(chunk_size):
                if current_part == 1:
                    val = (((t * 9) & (t >> 4)) | (t * 5 & t >> 7) | (t * 3 & int(t / 1024))) - 1
                elif current_part == 2:
                    val = (t << 2 ^ t >> 4 ^ t << 4 & t >> 8) | (t << 1 & -t >> 4)
                elif current_part == 3:
                    val = ((t * (t >> 8 | t >> 9) & 46 & t >> 8)) ^ (t & t >> 13 | t >> 6)
                elif current_part == 4:
                    shift_amt = (t >> 6) & 3
                    val = (t >> 6) ^ (t & (t >> 9)) ^ (t >> 12) | ((t << shift_amt ^ (-t) & ((-t) >> 13)) % 128) ^ ((-t) >> 1)
                elif current_part == 5:
                    val = ((t & (t >> 8)) | (t & (t >> 13))) * (1 + ((t >> 14) & 3)) | (t >> 7)
                else:
                    # FIX: Enforcing strict 32-bit register masking to stop execution crashes
                    x1 = (t * 2) & 0xFFFFFFFF
                    denom1 = (((x1 >> 14) & 3) + 4)
                    num1 = ((x1 >> 9) * x1) & 0xFFFFFFFF
                    div1 = (num1 // denom1) if denom1 != 0 else 0
                    f1 = (int(x1 / 8) >> (div1 & 31)) & 255

                    x2 = (t * 2 + 1) & 0xFFFFFFFF
                    denom2 = (((x2 >> 14) & 3) + 4)
                    num2 = ((x2 >> 9) * x2) & 0xFFFFFFFF
                    div2 = (num2 // denom2) if denom2 != 0 else 0
                    f2 = (int(x2 / 8) >> (div2 & 31)) & 255

                    u = (f1 | (f2 << 8)) & 0xFFFF

                    # Manual bitwise short signed casting
                    if u & 0x8000:
                        signed_u = u - 0x10000
                    else:
                        signed_u = u

                    sample_float = signed_u / 32768.0
                    val = int((sample_float + 1.0) * 127.5)

                raw_data[i] = int(val) & 255
                t = (t + 1) & 0xFFFFFFFF

            raw_bytes = bytes(raw_data)
            whdr = WAVEHDR()
            whdr.lpData = ctypes.c_char_p(raw_bytes)
            whdr.dwBufferLength = chunk_size

            buffers.append((raw_bytes, whdr))
            ctypes.windll.winmm.waveOutPrepareHeader(HWAVEOUT, ctypes.byref(whdr), ctypes.sizeof(WAVEHDR))
            ctypes.windll.winmm.waveOutWrite(HWAVEOUT, ctypes.byref(whdr), ctypes.sizeof(WAVEHDR))

            if len(buffers) > 8:
                old_bytes, old_hdr = buffers.pop(0)
                ctypes.windll.winmm.waveOutUnprepareHeader(HWAVEOUT, ctypes.byref(old_hdr), ctypes.sizeof(WAVEHDR))

            time.sleep(chunk_size / sample_rate - 0.02)
    except Exception:
        pass
    finally:
        ctypes.windll.winmm.waveOutReset(HWAVEOUT)
        ctypes.windll.winmm.waveOutClose(HWAVEOUT)

def get_titlebar_buttons_regions(screen_left, screen_top):
    regions = []
    def enum_windows_callback(hwnd, lParam):
        if win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
            rect = win32gui.GetWindowRect(hwnd)
            w_left, w_top, w_right, w_bottom = rect
            if (w_right - w_left) > 50 and (w_bottom - w_top) > 50:
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                if style & win32con.WS_CAPTION:
                    btn_width = win32api.GetSystemMetrics(win32con.SM_CXSIZE) * 3
                    btn_height = win32api.GetSystemMetrics(win32con.SM_CYSIZE)
                    rx1 = w_right - btn_width - screen_left
                    ry1 = w_top - screen_top + 2
                    rx2 = w_right - screen_left - 2
                    ry2 = w_top + btn_height - screen_top + 4
                    regions.append((rx1, ry1, rx2, ry2))
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
            reset_audio_time = False
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

            # Dynamic exclusion layout masks protect close button groups
            button_regions = get_titlebar_buttons_regions(screen_left, screen_top)
            for box in button_regions:
                bx1, by1, bx2, by2 = box
                bw = bx2 - bx1
                bh = by2 - by1
                if 0 <= bx1 < screen_width and 0 <= by1 < screen_height:
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
    audio_thread = threading.Thread(target=audio_bytebeat_engine, daemon=True)
    audio_thread.start()
    try:
        gdi_animation_loop()
    except Exception:
        pass
    finally:
        running = False
        time.sleep(0.15)
        win32gui.RedrawWindow(0, None, None, win32con.RDW_INVALIDATE | win32con.RDW_ERASE | win32con.RDW_ALLCHILDREN | win32con.RDW_UPDATENOW)
        ctypes.windll.user32.SystemParametersInfoW(win32con.SPI_SETDESKWALLPAPER, 0, None, win32con.SPIF_SENDCHANGE)
