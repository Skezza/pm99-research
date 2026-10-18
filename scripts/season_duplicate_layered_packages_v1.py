"""Apply exact, independently bound ownership changes to their actual layer.

The compiler view is private, not a recipe. Published main/English documents
retain all unrelated rows and the main artifact binds the new English bytes.
"""
import copy
import hashlib
from scripts import season_duplicate_english_overlay_v1 as overlay
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_package_v2 as package_v2


def compiler_view(main,english=None):
    layers=[main]+([english] if english is not None else [])
    players=[p for pkg in layers for p in pkg['players']]
    clubs=[c for pkg in layers for c in pkg['clubs']]
    if len({p['id'] for p in players})!=len(players) or len({c['id'] for c in clubs})!=len(clubs):
        raise ValueError('layered compiler inputs contain ambiguous recipe IDs')
    return {'players':players,'clubs':clubs}


def prepare(release,plan,original,main=None):
    labels={r['layer'] for r in plan['updates']}
    if labels-{'main','english'}:raise ValueError('unsupported ownership recipe layer')
    if main is None:
        main=next(pkg for label,pkg,_ in planner.package_layers(release) if label=='main')
    if 'english' not in labels:
        result=delta.updated_package(main,plan)
        aliases=delta.fit_display_names(original,result,plan)
        return result,None,compiler_view(result),aliases
    overlay.validate_binding(release,plan)
    english=next(pkg for label,pkg,_ in planner.package_layers(release) if label=='english')
    result=(delta.updated_package(main,plan,selected_layer='main')
            if 'main' in labels else copy.deepcopy(main))
    updated=delta.updated_package(english,plan,selected_layer='english')
    private=compiler_view(result,updated)
    aliases=delta.fit_display_names(original,private,plan)
    # Fit changed names before hashing: this is the published English recipe.
    digest=hashlib.sha256(package_v2.canonical_json_bytes(updated)).hexdigest()
    artifacts=[a for a in result['artifacts'] if a['id']==overlay.ARTIFACT]
    if len(artifacts)!=1 or artifacts[0]['sha256']!=plan['bindings']['english_overlay']['sha256']:
        raise ValueError('main recipe does not bind the exact previous English layer')
    relative=artifacts[0].get('relative_path')
    if not relative:raise ValueError('English recipe artifact needs a local relative path')
    artifacts[0]['sha256']=digest
    package_v2.validate_package(result,strict=False)
    return result,updated,private,aliases
