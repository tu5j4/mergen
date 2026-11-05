"""Keep trusted image coordinates across uncertain frames before requesting a reread."""
from dataclasses import dataclass
import time
import numpy as np
from . import capture


@dataclass(frozen=True)
class TrackingEvent:
    shift: int = 0
    reset: bool = False
    pending: bool = False
    reason: str = 'stable'


class ScrollTracker:
    def __init__(self,change_threshold=3.,max_pending_frames=3,max_pending_seconds=.45,
                 blank_grace_frames=6,blank_grace_seconds=.8,clock=time.monotonic,
                 scroll_tracking=True,matcher=None):
        self.change_threshold=float(change_threshold)
        self.max_pending_frames=max(2,int(max_pending_frames))
        self.max_pending_seconds=max(0.,float(max_pending_seconds))
        self.blank_grace_frames=max(self.max_pending_frames,int(blank_grace_frames))
        self.blank_grace_seconds=max(self.max_pending_seconds,float(blank_grace_seconds))
        self.clock=clock;self.scroll_tracking=scroll_tracking;self.matcher=matcher
        self.reset()

    def reset(self):
        self._good_gray=None;self._good_thumbnail=None
        self._candidate_thumbnail=None;self._pending_since=None
        self._pending_frames=0;self._stable_candidates=0

    def set_scroll_tracking(self,enabled):
        self.scroll_tracking=bool(enabled)
        self.reset()

    def _accept(self,gray,thumbnail):
        self._good_gray=gray.copy();self._good_thumbnail=thumbnail.copy()
        self._candidate_thumbnail=None;self._pending_since=None
        self._pending_frames=0;self._stable_candidates=0

    def update(self,gray,thumbnail=None):
        if gray.ndim!=2 or not gray.size:raise ValueError('takip görüntüsü iki boyutlu olmalı')
        thumbnail=capture.thumbnail_gray(gray) if thumbnail is None else thumbnail
        if self._good_gray is None:
            self._accept(gray,thumbnail);return TrackingEvent(reason='initial')
        if gray.shape!=self._good_gray.shape:
            self._accept(gray,thumbnail);return TrackingEvent(reset=True,reason='resized')
        shift=(self.matcher or capture.estimate_vshift)(self._good_gray,gray,self.change_threshold) if self.scroll_tracking else None
        difference=capture.frame_diff(thumbnail,self._good_thumbnail)
        if shift is not None and shift!=0:
            self._accept(gray,thumbnail);return TrackingEvent(shift=int(shift),reason='scroll')
        if difference<=self.change_threshold:
            # Only reported displacement may advance the coordinate anchor.
            # Otherwise repeated subpixel/coarse-zero steps disappear forever.
            self._candidate_thumbnail=None;self._pending_since=None
            self._pending_frames=0;self._stable_candidates=0
            return TrackingEvent(reason='stable')
        now=self.clock()
        if self._pending_since is None:self._pending_since=now
        self._pending_frames+=1
        if (self._candidate_thumbnail is not None and
                capture.frame_diff(thumbnail,self._candidate_thumbnail)<=min(1.,self.change_threshold)):
            self._stable_candidates+=1
        else:self._stable_candidates=1
        self._candidate_thumbnail=thumbnail.copy()
        blank=float(np.std(gray))<2.
        frame_limit=self.blank_grace_frames if blank else self.max_pending_frames
        time_limit=self.blank_grace_seconds if blank else self.max_pending_seconds
        bounded=self._pending_frames>=frame_limit or now-self._pending_since>=time_limit
        # Continuous motion remains hidden/pending: a deadline alone cannot
        # establish a new page. Two consistent candidate frames are required.
        if bounded and self._stable_candidates>=2:
            self._accept(gray,thumbnail)
            return TrackingEvent(reset=True,reason='blank_stable' if blank else 'unmatched_stable')
        return TrackingEvent(pending=True,reason='blank_pending' if blank else 'uncertain')
