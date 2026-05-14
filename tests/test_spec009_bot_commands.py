"""Unit tests for spec 009 — _BOT_COMMANDS completeness."""

from fastapistock.main import _BOT_COMMANDS


def test_bot_commands_count() -> None:
    assert len(_BOT_COMMANDS) == 6


def test_bot_commands_set() -> None:
    commands = {entry['command'] for entry in _BOT_COMMANDS}
    assert commands == {'q', 'pnl', 'us', 'tw', 'history', 'help'}


def test_bot_commands_descriptions_nonempty() -> None:
    for entry in _BOT_COMMANDS:
        assert entry['description']


def test_help_is_last() -> None:
    assert _BOT_COMMANDS[-1]['command'] == 'help'


def test_pnl_description_contains_keyword() -> None:
    pnl = next(e for e in _BOT_COMMANDS if e['command'] == 'pnl')
    assert '損益' in pnl['description']


def test_history_description_contains_keyword() -> None:
    hist = next(e for e in _BOT_COMMANDS if e['command'] == 'history')
    assert '歷史' in hist['description']


def test_pnl_is_at_index_1() -> None:
    """AC T1: 第 2 個 entry（index 1）必須為 pnl。"""
    assert _BOT_COMMANDS[1]['command'] == 'pnl'


def test_history_is_at_index_4() -> None:
    """AC T1: 第 5 個 entry（index 4）必須為 history。"""
    assert _BOT_COMMANDS[4]['command'] == 'history'
