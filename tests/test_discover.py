"""Tests for runner/discover.py's dialogue attribution.

Regression coverage for the missing attribution shape: name-before-verb
right after the closing quote ('"..." Mary said.'). That is the dominant
attribution order in English prose. Before this fix, dialogue_by_speaker
only recognized verb-before-name after the quote ('"...," said Mary.') and
name-before-verb before the quote ('Mary said, "...".') -- every normally
punctuated '"..." Mary said.' line fell into the unattributed '?' bucket,
which silently zeroed voice_collisions, speaker_drift, and the
voice-lexicon gate on a typical manuscript.
"""

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.discover import dialogue_by_speaker  # noqa: E402


class DialogueAttributionTests(unittest.TestCase):
    def test_verb_before_name_after_quote(self) -> None:
        text = '"I will not," said Mary.'
        by_speaker, _ = dialogue_by_speaker(text)
        self.assertIn("Mary", by_speaker)
        self.assertNotIn("?", by_speaker)

    def test_name_before_verb_before_quote(self) -> None:
        text = 'Mary said, "I will not."'
        by_speaker, _ = dialogue_by_speaker(text)
        self.assertIn("Mary", by_speaker)
        self.assertNotIn("?", by_speaker)

    def test_name_before_verb_after_quote(self) -> None:
        text = '"I will not," Mary said.'
        by_speaker, _ = dialogue_by_speaker(text)
        self.assertIn("Mary", by_speaker)
        self.assertNotIn("?", by_speaker)

    def test_name_before_verb_after_quote_with_trailing_action(self) -> None:
        text = '"Fine," Mary snapped, turning away.'
        by_speaker, _ = dialogue_by_speaker(text)
        self.assertIn("Mary", by_speaker)

    def test_carried_attribution_across_spans_in_one_paragraph(self) -> None:
        text = '"I will not," John said. "The house is mine."'
        by_speaker, _ = dialogue_by_speaker(text)
        self.assertEqual(2, len(by_speaker.get("John", [])))

    def test_full_tag_verb_list_recognized_not_just_said_asked(self) -> None:
        text = '"Maybe," Sarah whispered, turning away.'
        by_speaker, _ = dialogue_by_speaker(text)
        self.assertIn("Sarah", by_speaker)

    def test_mixed_forms_in_one_manuscript_all_attributed(self) -> None:
        text = (
            '"Get out," Mary said.\n\n'
            '"I will not," said John. "The house is mine."\n\n'
            'Sarah said, "You cannot be serious."\n\n'
            '"Maybe," Sarah whispered, turning away.\n'
        )
        by_speaker, _ = dialogue_by_speaker(text)
        self.assertNotIn("?", by_speaker)
        self.assertIn("Mary", by_speaker)
        self.assertIn("John", by_speaker)
        self.assertIn("Sarah", by_speaker)
        self.assertEqual(2, len(by_speaker["Sarah"]))


if __name__ == "__main__":
    unittest.main()
