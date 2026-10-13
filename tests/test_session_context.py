import unittest
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from app.config import Settings
from app.core.ocr import OCRBlock
from app.core.pipeline import TranslationWorker
from app.core.session_context import SessionContext
from app.core.translator import Translator


class SessionContextTests(unittest.TestCase):
    def test_verified_full_name_in_all_five_languages(self):
        examples = {'eng_Latn':'Yuji Itadori!', 'jpn_Jpan':'虎杖悠仁だ',
                    'zho_Hant':'是你虎杖悠仁吧!', 'zho_Hans':'虎杖悠仁来了',
                    'kor_Hang':'이타도리 유지야'}
        for lang, source in examples.items():
            context=SessionContext()
            plan=context.prepare([source],lang)[0]
            self.assertIn('Yuji Itadori',plan.prepared)
            self.assertTrue(plan.missing('kaplan sopası'))
            self.assertFalse(plan.missing("Yuji Itadori'ye söyle."))

    def test_ambiguous_short_name_needs_verified_context(self):
        context=SessionContext()
        self.assertEqual(context.prepare(['虎杖'], 'jpn_Jpan')[0].prepared,'虎杖')
        context.remember('虎杖悠仁だ','Yuji Itadori.', 'jpn_Jpan')
        self.assertEqual(context.prepare(['虎杖'], 'jpn_Jpan')[0].prepared,'Yuji Itadori')
        self.assertEqual(context.prepare(['虎杖'], 'zho_Hant')[0].prepared,'虎杖')
        context.clear()
        self.assertEqual(context.prepare(['虎杖'], 'jpn_Jpan')[0].prepared,'虎杖')

    def test_same_batch_full_name_can_identify_short_name_without_reordering(self):
        plans=SessionContext().prepare(['虎杖!', '虎杖悠仁だ'], 'jpn_Jpan')
        self.assertEqual([p.prepared for p in plans], ['Yuji Itadori!', 'Yuji Itadoriだ'])

    def test_explicit_latin_introduction_is_learned_but_general_words_are_not(self):
        context=SessionContext()
        for text in ('Good Morning!', 'HELLO WORLD!', "I'm Hungry.", 'Call me crazy.'):
            self.assertFalse(context.prepare([text],'eng_Latn')[0].terms)
        plan=context.prepare(['My name is john.'],'eng_Latn')[0]
        self.assertEqual(plan.prepared,'My name is John.')
        self.assertTrue(context.remember('My name is john.','Benim adım John.','eng_Latn'))
        self.assertEqual(context.prepare(['john, come here.'],'eng_Latn')[0].prepared,'John, come here.')
        self.assertFalse(context.prepare(['Johnson is here.'],'eng_Latn')[0].terms)

    def test_mixed_script_acronyms_and_exact_spelling_correction(self):
        context=SessionContext()
        plan=context.prepare(['傳言說他SASUKE, TBS的節目'],'zho_Hant')[0]
        self.assertEqual(plan.canonicalize("Sasuke, tbs'nin programı."),"SASUKE, TBS'nin programı.")
        self.assertEqual(len(plan.terms),2)
        self.assertFalse(context.prepare(['靈異研就是為了解開靈異現象'],'zho_Hant')[0].terms)

    def test_history_terms_and_seen_ids_are_bounded_and_duplicates_ignored(self):
        context=SessionContext(history_limit=2,term_limit=2)
        for index,name in enumerate(('John','Mary','Alice')):
            source='My name is '+name
            self.assertTrue(context.remember(source,name,'eng_Latn',panel=index,event_id=(index,)))
            self.assertFalse(context.remember(source,name,'eng_Latn',panel=index,event_id=(index,)))
        self.assertEqual(len(context.history),2)
        self.assertEqual(len(context.terms),2)
        self.assertEqual(context.history[-1].panel,2)

    def test_uncertain_incomplete_and_semantically_invalid_results_do_not_teach(self):
        context=SessionContext()
        for source,result in [('My name is John','[?] John'),('虎杖悠仁','kaplan sopası'),
                              ('My grandfather is John.','John annem.'),('','John')]:
            self.assertFalse(context.remember(source,result,'eng_Latn' if 'My' in source else 'zho_Hant'))
        self.assertFalse(context.history)
        self.assertFalse(context.terms)

    def test_job_fork_does_not_change_live_session(self):
        live=SessionContext()
        pending=live.fork()
        pending.remember('虎杖悠仁','Yuji Itadori','zho_Hant')
        self.assertTrue(pending.terms)
        self.assertFalse(live.terms)
        self.assertFalse(live.history)


class ContextTranslatorTests(unittest.TestCase):
    def setUp(self):
        self.tr=object.__new__(Translator)
        self.tr.beam_size=4
        self.tr.cache_size=30
        self.tr._cache=OrderedDict()
        self.calls=[]
        def model(texts,source,target,beam):
            self.calls.append((list(texts),source,target))
            return ['Yuji Itadori.' if 'Yuji Itadori' in text else 'Merhaba.' for text in texts]
        self.tr._translate_texts=model

    def test_name_preparation_keeps_balloon_count_and_cache_hits(self):
        context=SessionContext()
        result=self.tr.translate(['虎杖悠仁','你好'],'zho_Hant',context=context)
        self.assertEqual(result,['Yuji Itadori.','Merhaba.'])
        self.assertEqual(self.calls[0][0],['Yuji Itadori','你好'])
        self.tr.translate(['虎杖悠仁','你好'],'zho_Hant',context=context)
        self.assertEqual(len(self.calls),1)
        self.assertFalse(context.history)  # Only the pipeline commits displayed text.

    def test_context_cache_does_not_reuse_a_previous_ambiguous_result(self):
        context=SessionContext()
        self.assertEqual(self.tr.translate(['虎杖'],'zho_Hant',context=context),['Merhaba.'])
        context.remember('虎杖悠仁','Yuji Itadori.','zho_Hant')
        self.assertEqual(self.tr.translate(['虎杖'],'zho_Hant',context=context),['Yuji Itadori.'])
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.tr.translate(['虎杖'],'zho_Hant'),['Merhaba.'])

    def test_only_missing_name_retries_and_failure_is_marked(self):
        def model(texts,source,target,beam):
            self.calls.append((list(texts),source,target))
            return ['wrong' for _ in texts]
        self.tr._translate_texts=model
        result=self.tr.translate(['虎杖悠仁','你好'],'zho_Hant',context=SessionContext())
        self.assertEqual(result,['[?] wrong','Wrong'])
        self.assertEqual(self.tr.last_retry_count,1)
        self.assertEqual(self.calls[1][0],['Yuji Itadori'])

    def test_known_original_spelling_in_output_can_be_canonicalized_without_retry(self):
        self.tr._translate_texts=lambda texts,*args:['虎杖悠仁 geldi.']
        self.assertEqual(self.tr.translate(['虎杖悠仁'],'zho_Hant',context=SessionContext()),['Yuji Itadori geldi.'])
        self.assertEqual(self.tr.last_retry_count,0)


class ContextPipelineTests(unittest.TestCase):
    def worker(self):
        worker=TranslationWorker(Settings(),True)
        worker._write_scan_diagnostic=lambda diagnostic:None
        worker.ocr=SimpleNamespace(process_iter=lambda *a:iter([[OCRBlock(20,20,100,80,'虎杖悠仁',panel=2)]]))
        worker.translator=SimpleNamespace(translate=lambda *a,**kw:['Yuji Itadori.'],clear_cache=Mock())
        return worker

    def test_history_commits_only_when_valid_partial_is_displayed(self):
        worker=self.worker()
        worker._ocr_job(np.full((120,160,3),255,np.uint8),0,worker._gen,'zh_tw',4)
        self.assertFalse(worker._session_context.history)
        worker._drain_partials()
        self.assertEqual(len(worker._session_context.history),1)
        self.assertEqual(worker._session_context.history[0].panel,2)
        worker._reset_content()  # Changing the page preserves session vocabulary.
        worker._ocr_job(np.full((120,160,3),255,np.uint8),0,worker._gen,'zh_tw',4)
        worker._drain_partials()
        self.assertEqual(len(worker._session_context.history),1)

    def test_cancelled_or_failed_job_cannot_poison_live_memory(self):
        worker=self.worker()
        def translate(*a,**kw):
            worker._gen+=1
            return ['Yuji Itadori.']
        worker.translator.translate=translate
        worker._ocr_job(np.full((120,160,3),255,np.uint8),0,worker._gen,'zh_tw',4)
        worker._drain_partials()
        self.assertFalse(worker._session_context.history)
        self.assertTrue(worker._partials.empty())

    def test_pending_partials_discarded_after_page_reset(self):
        worker=self.worker()
        worker._ocr_job(np.full((120,160,3),255,np.uint8),0,worker._gen,'zh_tw',4)
        worker._reset_content()
        worker._drain_partials()
        self.assertFalse(worker._session_context.history)

    def test_manual_reset_clears_history_and_translation_cache_without_loading_models(self):
        worker=self.worker()
        worker._session_context.remember('虎杖悠仁','Yuji Itadori','zho_Hant')
        version=worker._context_version
        worker.reset_translation_context(False)
        self.assertEqual(worker._context_version,version+1)
        self.assertFalse(worker.s.session_context)
        worker._clear_translation_context()
        self.assertFalse(worker._session_context.history)
        worker.translator.clear_cache.assert_called_once()

    def test_disabled_context_keeps_previous_translate_call(self):
        worker=self.worker()
        worker._context_enabled=False
        calls=[]
        worker.translator.translate=lambda *a,**kw:calls.append(kw) or ['Yuji Itadori.']
        worker._ocr_job(np.full((120,160,3),255,np.uint8),0,worker._gen,'zh_tw',4)
        worker._drain_partials()
        self.assertNotIn('context',calls[0])
        self.assertFalse(worker._session_context.history)

    def test_disabled_job_snapshot_cannot_be_enabled_mid_job(self):
        worker=self.worker()
        calls=[]
        worker.translator.translate=lambda *a,**kw:calls.append(kw) or ['Yuji Itadori.']
        worker._ocr_job(np.full((120,160,3),255,np.uint8),0,worker._gen,'zh_tw',4,None)
        self.assertNotIn('context',calls[0])


if __name__=='__main__':
    unittest.main()
