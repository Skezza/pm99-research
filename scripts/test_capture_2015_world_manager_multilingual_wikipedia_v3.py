from __future__ import annotations

from scripts import capture_2015_world_manager_multilingual_wikipedia_v3 as capture


def test_reads_a_localised_manager_parameter_and_named_template_value() -> None:
    manager, issue = capture._manager(
        "| trainer = {{AUT|Ziel=Zoran Barisic}}\n", "de"
    )
    assert issue is None
    assert manager == "Zoran Barisic"


def test_rejects_joint_localised_manager_value() -> None:
    manager, issue = capture._manager(
        "| tränare = [[Joel Cedergren]] och [[Roger Franzén]]\n", "sv"
    )
    assert manager is None
    assert issue == "multiple-or-joint-manager-value"


def test_rejects_malformed_infobox_tail() -> None:
    manager, issue = capture._manager(
        "| entraîneur = |joueur le plus capé = [[Not a manager]]\n", "fr"
    )
    assert manager is None
    assert issue == "manager-field-blank"


def test_marks_non_cp1252_source_text_for_transliteration_before_game_write() -> None:
    assert capture._pm99_representable("Zoran Barisic")
    assert capture._pm99_representable("Zdeněk Ščasný")
    assert not capture._pm99_representable("Τόμας Κρίστιανσεν")
