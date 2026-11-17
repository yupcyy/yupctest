import pytest

from qq_deepseek.core.config import parse_first_id


def test_voice_source_accepts_one_or_multiple_groups():
    assert parse_first_id("") == 0
    assert parse_first_id("123") == 123
    assert parse_first_id("123,456") == 123
    assert parse_first_id(" 123 , 456 ") == 123


@pytest.mark.parametrize("value", ["abc", "-1", "0", "abc,123"])
def test_voice_source_rejects_invalid_first_group(value):
    with pytest.raises(ValueError): parse_first_id(value)
