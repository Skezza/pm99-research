import copy
import pytest

from scripts import advance_targeted_opening_duplicate_plans_v1 as module
from scripts import season_pipeline_v2 as pipeline


def fixture(tmp_path):
    row={'club':'Missing Biography','status':'original-first-fixture-reparsed','identity_gaps':[{'person':1}]}
    old={'seasons':[{'season':'2000-01','clubs':[row]}]}
    path=tmp_path/'prior.json';pipeline.write_canonical_json(path,old)
    current=copy.deepcopy(old)
    current['targeted_original_extension']={'previous_review':{'path':str(path),
        'sha256':module.registry.sha256_file(path)},'added':[{'season':'2000-01','club':row['club']}]}
    return current


def test_identical_partial_source_replay_does_not_redo_completed_season_decisions(tmp_path):
    current=fixture(tmp_path);assert module.advanced_seasons(current)==set()
    current['seasons'][0]['clubs'][0]['identity_gaps']=[]
    assert module.advanced_seasons(current)=={'2000-01'}


def test_new_complete_original_selects_only_its_season(tmp_path):
    current=fixture(tmp_path)
    current['seasons'].append({'season':'2001-02','clubs':[{'club':'New Club','status':'original-first-fixture-reparsed'}]})
    current['targeted_original_extension']['added'].append({'season':'2001-02','club':'New Club'})
    assert module.advanced_seasons(current)=={'2001-02'}


def test_changed_previous_review_cannot_claim_equivalence(tmp_path):
    current=fixture(tmp_path);current['targeted_original_extension']['previous_review']['sha256']='0'*64
    with pytest.raises(ValueError,match='previous review changed'):module.advanced_seasons(current)


def test_season_already_reconsidered_against_newer_review_is_not_repeated(tmp_path):
    current=fixture(tmp_path);current['seasons'][0]['clubs'][0]['identity_gaps']=[]
    advanced=tmp_path/'already-considered.json';pipeline.write_canonical_json(advanced,{'seasons':current['seasons']})
    root=tmp_path/'plans';p=root/'2000-01/ownership-plan.json';p.parent.mkdir(parents=True)
    pipeline.write_canonical_json(p,{'bindings':{'soccerbase_opening_sources':{'review':{
        'path':str(advanced),'sha256':module.registry.sha256_file(advanced)}}}})
    assert module.advanced_seasons(current)=={'2000-01'}
    assert module.advanced_seasons(current,root)==set()
