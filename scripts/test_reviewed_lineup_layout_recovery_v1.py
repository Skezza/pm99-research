"""Synthetic negative guards; these fixtures are not historical evidence."""
import copy
from types import SimpleNamespace
from PIL import Image
import pytest
from scripts import verify_reviewed_lineup_layout_recovery_v1 as subject


def setup_summary():
    release=SimpleNamespace(manifest_sha256='a'*64,locator={'game_inventory_fingerprint':'b'*64})
    selector=dict(team_name='Example Club',team_select_x=176,team_select_y=323,division_select_x=78,division_select_y=338)
    summary=dict(success=False,mode='generic-club-route-capture',release_manifest_sha256='a'*64,output_inventory_fingerprint='b'*64,phase_reached='return_from_line_up',dashboard_reached=True,requested_routes=['line_up'],team_name='Example Club',team_selection={k:v for k,v in selector.items() if k!='team_name'},confidence_notes=[subject.NOTE],crash_detected=False,wine_debugger_detected=False,process_exit_code=None,route_summaries={'line_up':dict(screen='unknown',expected_screen='lineup_screen',return_screen='club_dashboard_screen',team_identity=dict(matched=True,expected='Example Club',expected_normalized='example club',observed_normalized='example club'))})
    return release,selector,summary


def test_only_classification_false_negative_is_eligible():
    release,selector,summary=setup_summary();before=copy.deepcopy(summary)
    subject.require_eligible_summary(summary,release,selector)
    assert summary==before and summary['success'] is False


@pytest.mark.parametrize('field,value',[('success',True),('crash_detected',True),('wine_debugger_detected',True),('process_exit_code',9),('confidence_notes',[subject.NOTE,'another failure']),('release_manifest_sha256','c'*64),('requested_routes',['tactics']),('team_name','Other Club')])
def test_other_failures_and_mismatched_inputs_rejected(field,value):
    release,selector,summary=setup_summary();summary[field]=value
    with pytest.raises(ValueError):subject.require_eligible_summary(summary,release,selector)


@pytest.mark.parametrize('key,value',[('matched',False),('observed_normalized','other club')])
def test_wrong_club_cannot_be_recovered(key,value):
    release,selector,summary=setup_summary();summary['route_summaries']['line_up']['team_identity'][key]=value
    with pytest.raises(ValueError):subject.require_eligible_summary(summary,release,selector)


def test_pixel_layout_requires_all_fixed_regions_and_preserves_originals(tmp_path):
    a,b=tmp_path/'a.png',tmp_path/'b.png';image=Image.new('RGB',(640,480),(11,22,33));image.save(a);image.save(b)
    before=(a.read_bytes(),b.read_bytes());assert len(subject.compare_regions(a,b))==4;assert before==(a.read_bytes(),b.read_bytes())
    image.putpixel((210,20),(255,0,0));image.save(b)
    with pytest.raises(ValueError,match='lineup-title'):subject.compare_regions(a,b)


def test_different_client_dimensions_rejected(tmp_path):
    a,b=tmp_path/'a.png',tmp_path/'b.png';Image.new('RGB',(640,480)).save(a);Image.new('RGB',(640,460)).save(b)
    with pytest.raises(ValueError,match='640x480'):subject.compare_regions(a,b)
