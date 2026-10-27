import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from app.core.nllb_current_mask import generate_batch


class ContextBatchTests(unittest.TestCase):
    def test_finished_row_padding_does_not_report_token_limit(self):
        class Inputs(dict):
            def to(self,device):return self
        tokenizer=Mock(padding_side='right',eos_token_id=2)
        tokenizer.pad.return_value=Inputs(input_ids=SimpleNamespace(shape=(2,5)),attention_mask='encoder-mask')
        tokenizer.decode.side_effect=['short','unfinished']
        model=Mock()
        model.generate.return_value=SimpleNamespace(tolist=lambda:[[2,300,42,2]+[1]*189,[2,300]+[42]*191])
        rows=[dict(source='first',previous_sources=['history']),dict(source='second',previous_sources=[])]
        encoded=[(dict(input_ids=[3,4,2]),[0,1,1]),(dict(input_ids=[3,4,5,6,2]),[0,0,1,1,1])]
        tensor=Mock(return_value='cross-mask')
        with patch.dict(sys.modules,torch=SimpleNamespace(tensor=tensor)),patch('app.core.nllb_current_mask.encode',side_effect=encoded):
            results=generate_batch(model,tokenizer,rows,'cuda:0')
        tensor.assert_called_once_with([[0,1,1,0,0],[0,0,1,1,1]],device='cuda:0')
        self.assertFalse(results[0]['limit_reached'])
        self.assertTrue(results[1]['limit_reached'])
        self.assertEqual(tokenizer.decode.call_args_list[0].args[0],[2,300,42,2])
        self.assertEqual(model.generate.call_args.kwargs['attention_mask'],'cross-mask')
        self.assertEqual(model.generate.call_args.kwargs['num_beams'],4)


if __name__=='__main__':unittest.main()
