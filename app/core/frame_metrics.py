"""Bounded numeric diagnostics and conservative adaptive idle polling."""
from collections import Counter, deque
import json
import os
import time


class AdaptivePoll:
    def __init__(self, enabled=None, clock=time.monotonic):
        self.enabled = os.environ.get('MERGEN_ADAPTIVE_POLL', '1') != '0' if enabled is None else enabled
        self.clock = clock
        self.reset()

    def reset(self):
        self.last_motion = self.clock()

    def interval(self, base_ms, requires_hide=False):
        base = max(20, int(base_ms))
        if requires_hide:
            return max(400, base)
        if not self.enabled:
            return base
        idle = self.clock() - self.last_motion
        # Never exceed the user's requested polling frequency while moving.
        target = 120 if idle >= 2 else 60 if idle >= .5 else 30
        return max(base, target)


class FrameMetrics:
    """Fixed sample capacity; counters cover the whole run, percentiles recent samples."""
    def __init__(self, capacity=1024):
        self.capacity = capacity
        self.samples = {name: deque(maxlen=capacity) for name in (
            'capture_ms', 'grayscale_ms', 'motion_ms', 'actual_interval_ms',
            'poll_target_ms', 'job_first_dispatch_ms')}
        self.counts = Counter()
        self.previous_frame = None

    def add(self, name, value):
        self.samples[name].append(float(value))

    def frame(self, now):
        self.counts['frames'] += 1
        if self.previous_frame is not None:
            self.add('actual_interval_ms', (now-self.previous_frame)*1000)
        self.previous_frame = now

    def summary(self):
        result = {'counts': dict(self.counts), 'sample_scope': f'last {self.capacity} observations per metric', 'metrics': {}}
        for name, values in self.samples.items():
            ordered = sorted(values)
            if ordered:
                result['metrics'][name] = {'samples': len(ordered), 'p50': round(ordered[(len(ordered)-1)//2], 3),
                    'p95': round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 3), 'max': round(ordered[-1], 3)}
        return result

    def write(self, path):
        try:
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(self.summary(), indent=2), encoding='utf-8')
        except OSError:
            pass
