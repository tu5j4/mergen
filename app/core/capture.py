"""
Ekran yakalama, değişim algılama ve KAYDIRMA TAHMİNİ (UI bağımsız).
"""
from __future__ import annotations

import cv2
import numpy as np
import sys


class ScreenCapturer:
    """mss nesnesi thread'e bağlıdır; kullanılacağı thread içinde tembel oluşturulur."""

    def __init__(self) -> None:
        self._sct = None
        self._underlay = None

    def grab_under_overlay(self,left,top,width,height,hwnd,areas):
        if sys.platform!='win32':return None
        from .window_capture import WindowsUnderlayCapture
        try:
            if self._underlay is None:self._underlay=WindowsUnderlayCapture()
            image=self.grab(left,top,width,height)
            if image is None:return None
            return self._underlay.restore(image,left,top,hwnd,areas)
        except (OSError,ValueError):
            return None

    def grab(self, left: int, top: int, width: int, height: int) -> np.ndarray | None:
        if width <= 0 or height <= 0:
            return None
        if self._sct is None:
            import mss
            self._sct = mss.mss()
        shot = self._sct.grab({"left": int(left), "top": int(top),
                               "width": int(width), "height": int(height)})
        bgra = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)
        return cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGB)

    def close(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None


def to_gray(img_rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)


def thumbnail_gray(gray: np.ndarray, size: int = 96) -> np.ndarray:
    return cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)


def frame_diff(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None or a.shape != b.shape:
        return 255.0
    return float(np.mean(np.abs(a - b)))


def estimate_vshift(prev_gray: np.ndarray, cur_gray: np.ndarray,
                    diff_threshold: float = 3.0, small_w: int = 320,
                    min_score: float = 0.9) -> int | None:
    """
    İki kare arasındaki dikey kaydırma miktarını (piksel) tahmin eder.
      > 0 : içerik yukarı kaydı (aşağı scroll)
      < 0 : içerik aşağı kaydı (yukarı scroll)
      0   : kayma yok
      None: saf bir dikey kaydırma değil (sayfa değişti / belirsiz)
    """
    H, W = prev_gray.shape[:2]
    if cur_gray.shape != prev_gray.shape or H < 64 or W < 32:
        return None

    s = min(1.0, small_w / W)
    sw, sh = max(16, int(round(W * s))), max(16, int(round(H * s)))
    ps = cv2.resize(prev_gray, (sw, sh), interpolation=cv2.INTER_AREA)
    cs = cv2.resize(cur_gray, (sw, sh), interpolation=cv2.INTER_AREA)
    psf, csf = ps.astype(np.float32), cs.astype(np.float32)
    if float(np.mean(np.abs(psf - csf))) < 0.5:
        return 0

    band_h = max(8, int(sh * 0.2))
    if sh - band_h < 4:
        return None

    # Önceki karede en çok doku içeren yatay şeridi şablon olarak seç
    row_tex = np.abs(np.diff(psf, axis=1)).mean(axis=1)
    csum = np.concatenate([[0.0], np.cumsum(row_tex)])
    win = csum[band_h:] - csum[:-band_h]
    y0 = int(np.argmax(win))
    if win[y0] / band_h < 1.5:      # bembeyaz/düz alan -> güvenilmez
        return None

    tmpl = ps[y0:y0 + band_h]
    res = cv2.matchTemplate(cs, tmpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    if not np.isfinite(score) or score < min_score:
        return None
    y1 = int(loc[1])
    dys = y0 - y1

    # Doğrulama: örtüşen alan gerçekten aynı mı?
    if dys > 0:
        a, b = psf[dys:], csf[:sh - dys]
    elif dys < 0:
        a, b = psf[:sh + dys], csf[-dys:]
    else:
        a, b = psf, csf
    if a.shape[0] < sh * 0.2 or float(np.mean(np.abs(a - b))) > diff_threshold * 4:
        return None
    if dys == 0:
        return 0

    # Tam çözünürlükte hassas düzeltme
    fy0 = min(H - 8, int(round(y0 / s)))
    fbh = min(max(8, int(round(band_h / s))), H - fy0)
    guess = int(round(y1 / s))
    r = int(np.ceil(1 / s)) + 2
    lo, hi = max(0, guess - r), min(H - fbh, guess + r)
    if hi >= lo:
        region = cur_gray[lo:hi + fbh]
        tmpl_f = prev_gray[fy0:fy0 + fbh]
        res_f = cv2.matchTemplate(region, tmpl_f, cv2.TM_CCOEFF_NORMED)
        _, sf, _, loc_f = cv2.minMaxLoc(res_f)
        if np.isfinite(sf) and sf >= min_score:
            return int(fy0 - (lo + loc_f[1]))
    return int(round(dys / s))
