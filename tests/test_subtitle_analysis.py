from pathlib import Path
import tempfile
import unittest

from scripts.analyze_subtitles import Cue, align, analyze, episode, read_ass, read_srt


class SubtitleAnalysisTests(unittest.TestCase):
    def test_timing_match_is_one_to_one(self):
        english = [Cue(10, 12, 'hello', 1), Cue(20, 23, 'bye', 2)]
        turkish = [Cue(10.02, 12.01, 'merhaba', 1), Cue(20, 23, 'görüşürüz', 2)]
        pairs = align(english, turkish)
        self.assertEqual([(i, j) for i, j, _ in pairs], [(0, 0), (1, 1)])

    def test_ambiguous_simultaneous_speakers_are_not_guessed(self):
        english = [Cue(10, 12, 'hello', 1)]
        turkish = [Cue(10, 12, 'merhaba', 1), Cue(10, 12, 'selam', 2)]
        self.assertEqual(align(english, turkish), [])

    def test_split_sentence_not_forced_into_single_pair(self):
        english = [Cue(10, 12, 'first', 1), Cue(12, 14, 'second', 2)]
        turkish = [Cue(10, 14, 'birinci ve ikinci', 1)]
        self.assertEqual(align(english, turkish), [])

    def test_ass_filters_lyrics_drawings_and_duplicate_layers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.ass'
            path.write_text('[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
                'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\i1}merhaba, dünya\\Nnasılsın\n'
                'Dialogue: 1,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\i1}merhaba, dünya\\Nnasılsın\n'
                'Dialogue: 0,0:00:04.00,0:00:05.00,Songs_OP,,0,0,0,,şarkı\n'
                'Dialogue: 0,0:00:06.00,0:00:07.00,Default,,0,0,0,,{\\p1}m 0 0 l 1 1\n', encoding='utf-8')
            cues, excluded, _ = read_ass(path)
            self.assertEqual(len(cues), 1)
            self.assertEqual(cues[0].text, 'merhaba, dünya nasılsın')
            self.assertEqual(excluded['non_dialogue_style'], 1)
            self.assertEqual(excluded['drawing'], 1)
            self.assertEqual(excluded['duplicate'], 1)

    def test_srt_bom_crlf_and_markup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.srt'
            path.write_bytes('\ufeff1\r\n00:00:01,200 --> 00:00:03,000\r\n<i>hello</i>\r\nworld\r\n'.encode('utf-8'))
            cues, malformed = read_srt(path)
            self.assertEqual(malformed, 0)
            self.assertEqual(cues[0].text, 'hello world')
            self.assertEqual(cues[0].start, 1.2)

    def test_episode_filenames(self):
        self.assertEqual(episode(Path('show S01E1 title.srt')), 1)
        self.assertEqual(episode(Path('show S01E12.en-US.srt')), 12)
        self.assertEqual(episode(Path('[group]_show_-_03.ass')), 3)

    def test_refuses_output_inside_originals_and_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'originals'
            source.mkdir()
            with self.assertRaises(ValueError):
                analyze(source, source / 'results')
            existing = Path(folder) / 'results'
            existing.mkdir()
            keep = existing / 'keep.txt'
            keep.write_text('keep')
            with self.assertRaises(ValueError):
                analyze(source, existing)
            self.assertEqual(keep.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
