"""Bound new predictions while replaying an unfinished strip without lost jobs."""
import hashlib
import json
from ..operations import Cancelled

EMPTY_RESULT = {'rec_boxes': [], 'rec_texts': [], 'rec_scores': []}


class PredictionBudget:
    def __init__(self, limit=6):
        self.limit=limit
        self.identity=None
        self.cache={}
        self.failures=set()
        self.used=0
        self.pending=set()

    @staticmethod
    def key(image):
        return (image.shape, image.dtype.str, hashlib.blake2b(image.tobytes(),digest_size=16).digest())

    def begin(self, image):
        identity=self.key(image)
        if identity != self.identity:
            self.cache.clear()
            self.failures.clear()
        self.identity=identity
        self.used=0
        self.pending=set()

    def call(self, namespace, key, function, deferred, cache_failures=True):
        key=(namespace,key)
        if key in self.cache:
            return self.cache[key]
        if self.used >= self.limit:
            self.pending.add(key)
            return deferred
        self.used += 1
        try:
            result=function()
        except Cancelled:
            raise
        except Exception:
            # Optional failures are terminal for this strip, not endlessly retried
            # ahead of deferred jobs. Store no exception/traceback or image views.
            if cache_failures:
                self.cache[key]=deferred
                self.failures.add(key)
            raise
        self.cache[key]=result
        return result

    def predict(self, predictor, image, primary=False):
        def invoke():
            result=next(iter(predictor(image)))
            data=getattr(result,'json',result)
            if isinstance(data,str):
                data=json.loads(data)
            if not isinstance(data,dict):
                raise ValueError('invalid OCR result')
            data=data.get('res',data)
            # Cache only recognition rows, never result objects/image buffers.
            fields={key:data.get(key,[]) for key in ('rec_boxes','rec_texts','rec_scores')}
            if len({len(value) for value in fields.values()})!=1:
                raise ValueError('incomplete OCR result rows')
            return fields
        return self.call('paddle',self.key(image),invoke,EMPTY_RESULT,cache_failures=not primary)

    def finish(self):
        if not self.pending:
            self.cache.clear()
            self.failures.clear()
            self.identity=None
