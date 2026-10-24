"""Source-bound roster transfer preserves unrelated data and rejects mixed native pairs."""
import importlib.util
from pathlib import Path
import pytest
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.season_opening_order_repair_v1 import native_owners
from scripts import season_package_compiler_v2 as compiler

from scripts import season_shuker_city_reserve_move_v1 as adapter
pytestmark = pytest.mark.skipif(not adapter.INPUT.is_file(), reason="local historical source corpus is not present")


def test_r220a_shuker_move_postimages_and_guards():
    base=registry.load_registered_release("2000-01",adapter.PARENT)
    plan=adapter.prepare(base)
    adapter.verify(base,plan)
    before=pipeline.read_json_file(base.package_path)
    after=adapter.bind(before,plan)
    oldclubs={c["carrier_id"]:c for c in before["clubs"]}
    newclubs={c["carrier_id"]:c for c in after["clubs"]}
    assert len(oldclubs[311]["roster_player_ids"])==24
    assert len(oldclubs[382]["roster_player_ids"])==25
    assert len(newclubs[311]["roster_player_ids"])==25
    assert len(newclubs[382]["roster_player_ids"])==24
    assert newclubs[311]["roster_player_ids"][-1]=="english-player-32945"
    assert "english-player-32945" not in newclubs[382]["roster_player_ids"]
    assert "english-player-32945" not in newclubs[382]["opening"]["substitute_player_ids"]
    assert len(newclubs[382]["opening"]["substitute_player_ids"])==6
    assert newclubs[311]["opening"]==oldclubs[311]["opening"]
    assert newclubs[382]["opening"]["starting_xi_player_ids"]==oldclubs[382]["opening"]["starting_xi_player_ids"]
    assert newclubs[382]["opening"]["tactics_context"]==oldclubs[382]["opening"]["tactics_context"]
    assert newclubs[382]["opening"]["tactics_positions"]==oldclubs[382]["opening"]["tactics_positions"]
    oldp={p["id"]:p for p in before["players"]};newp={p["id"]:p for p in after["players"]}
    assert all(oldp[k]==newp[k] for k in oldp if k!="english-player-32945")
    old=newp["english-player-32945"];oldrow=oldp["english-player-32945"]
    assert old["club_id"]==newclubs[311]["id"]
    assert old["person_id"]==oldrow["person_id"] and old["ratings"]==oldrow["ratings"]
    assert old["facts"]["fine_roles"]==oldrow["facts"]["fine_roles"]
    old_facts=dict(oldrow["facts"]);new_facts=dict(old["facts"])
    old_facts.pop("shirt_number");new_facts.pop("shirt_number")
    assert new_facts==old_facts
    assert old["facts"]["shirt_number"]=={"policy":"preserve-existing-mode1"}
    assert after["assets"]==before["assets"]
    assert after.get("managers")==before.get("managers")

    jug=(base.game_path/"DBDAT/JUG98030.FDI").read_bytes()
    eq=(base.game_path/"DBDAT/EQ98030.FDI").read_bytes()
    postj,posteq=adapter.apply(jug,eq,plan)
    assert adapter.apply(postj,posteq,plan)==(postj,posteq)
    assert native_owners(posteq)[32945]=={311}
    ix0=IndexedFDIFile.from_bytes(jug);ix1=IndexedFDIFile.from_bytes(postj)
    e0={e.record_id:e for e in ix0.entries};e1={e.record_id:e for e in ix1.entries}
    changed=set(plan["native_postimages"])
    changed_ids={r["carrier_id"] for r in plan["startup_order_changes"]}
    for cid in set(e0)-changed_ids:
        assert e0[cid].decode_payload(jug)==e1[cid].decode_payload(postj)
    for cid in changed_ids:
        a=e0[cid].decode_payload(jug);b=e1[cid].decode_payload(postj)
        order=read_initial_order(a).offset
        assert all(a[i]==b[i] for i in range(len(a)) if i!=order)
    assert packages.canonical_json_bytes(adapter.source_artifact(plan)["document"]).endswith(b"\n")
    with pytest.raises(ValueError): adapter.bind(before,{**plan,"scope":"tampered"})
    with pytest.raises(ValueError): adapter.apply(jug,posteq,plan)
    with pytest.raises(ValueError): adapter.reject_factory_recipe({"artifacts":[{"id":adapter.artifact_id(plan)}]})
