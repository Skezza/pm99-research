"""Record ROOT's direct inspection of the two original runner frames."""
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.capture_barnet2018_runtime_20261017 import FOLDER, TAG
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

def run():
    rows = [
        ('cousins',48,'M COUSINS','England',31,'Goalkeeper',dict(speed=41,stamina=48,aggression=47,quality=60,handling=59,passing=50,dribbling=30,heading=33,tackling=33,shooting=24)),
        ('boucaud',52,'Andre BOUCAUD','Trinidad and Tobago',34,'Midfielder',dict(speed=65,stamina=68,aggression=62,quality=63,handling=8,passing=66,dribbling=68,heading=61,tackling=66,shooting=60)),
    ]
    for label,number,name,country,age,role,skills in rows:
        screenshot=FOLDER/'runtime'/label/(TAG+'_'+label)/'screens'/f'{number}_profile_only_{label}_done.png'
        retained(FOLDER/(label+'-profile-visual-review.json'),dict(
            method='assistant-original-image-visual-review',reviewer='ROOT',original_frame_visually_inspected=True,
            screenshot=registry.relative_workspace_path(screenshot),screenshot_sha256=registry.sha256_file(screenshot),
            observed_native_name=name,observed_club='Barnet',observed_nationality=country,
            observed_age=age,expected_age=age,observed_role=role,observed_no_photo=True,
            observed_skills=skills,all_ten_visible_skills_inspected=True,visible_skills_match_native_baseline=True,
            machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4'))

if __name__=='__main__':run()
