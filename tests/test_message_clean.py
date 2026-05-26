# tests/test_message_clean.py
from linkedin.actions.message import clean_message_punctuation

def test_clean_message_punctuation_replaces_emdashes():
    """Test em-dashes and en-dashes are correctly replaced with spaced hyphens."""
    input_text = "I noticed your work on GEO—how are you measuring it?"
    expected = "I noticed your work on GEO - how are you measuring it?"
    assert clean_message_punctuation(input_text) == expected


def test_clean_message_punctuation_replaces_multiple_emdashes():
    """Test multiple occurrences of em-dashes are handled."""
    input_text = "SEO—how is it? SGE—any thoughts?"
    expected = "SEO - how is it? SGE - any thoughts?"
    assert clean_message_punctuation(input_text) == expected


def test_clean_message_punctuation_replaces_endashes():
    """Test en-dashes are also replaced."""
    input_text = "June–July timeline"
    expected = "June - July timeline"
    assert clean_message_punctuation(input_text) == expected


def test_clean_message_punctuation_collapses_spaces():
    """Test that introduced duplicate spaces are collapsed to single spaces."""
    input_text = "hello — — world"
    expected = "hello - - world"
    assert clean_message_punctuation(input_text) == expected


def test_clean_message_punctuation_handles_empty_or_none():
    """Test function handles empty or None input gracefully."""
    assert clean_message_punctuation("") == ""
    assert clean_message_punctuation(None) is None
