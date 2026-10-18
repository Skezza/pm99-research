"""A full surname explicitly identified by an original same-person initial alias.

Only 'R. Hall-Johnson' together with 'Reece Hall-Johnson' identifies the
complete family component. Never take the last token, strip surname particles,
guess missing given names, or shorten a surname to fit a binary slot. Full
names stay intact; this is a separately verified display component, not a
new canonical person or independent ownership proof.
"""
import copy
import json
import re
from scripts import season_published_display_names_v1 as display
from scripts import season_published_person_identity_v1 as people
from scripts import season_release_registry_v1 as registry

POLICY='original-initial-alias-and-full-name-verbatim-family-component-v1'


def components(raw):
    full=raw.get('name')
    if not isinstance(full,str):return []
    full=' '.join(full.split());parts=full.split(' ',1)
    if len(parts)!=2:return []
    given,family=parts
    # An already abbreviated full-name field cannot establish the expansion.
    if len(given)<2 or '.' in given or not given[0].isalpha():return []
    results=[]
    for field in ('displayName','shortName'):
        alias=raw.get(field)
        if not isinstance(alias,str):continue
        alias=' '.join(alias.split())
        match=re.fullmatch(r'([^\W\d_])(?:\.\s*|\s+)(.+)',alias)
        if not match or match[1].casefold()!=given[0].casefold() or match[2].casefold()!=family.casefold():continue
        results.append({'field':field,'name':family,'original_full_name':full,
            'original_alias':alias,'explicit_given_component':given,
            'method':'one-original-initial-plus-verbatim-entire-remaining-full-name'})
    return results


def claims(path,required_ids):
    doc=json.loads(path.read_text())
    if doc.get('schema_version')!=people.SCHEMA or doc.get('policy')!=people.POLICY:
        raise ValueError('family display components require the original confirmed-person source input')
    required=set(required_ids);result={}
    for batch in doc['batches']:
        if batch['status']!='original-entities-parsed' or not required.intersection(batch['requested_ids']):continue
        raw,confirmed=display.read_batch(batch)
        for id in sorted(required.intersection(raw)):
            derived=components(raw[id])
            if not derived:continue
            claim={'policy':POLICY,'source_player_id':id,'birth_date':confirmed[id]['birth_date'],
                'components':derived,'original_batch':{k:copy.deepcopy(batch[k]) for k in display.BATCH_KEYS}}
            if id in result and claim!=result[id]:raise ValueError('original family display component sources conflict')
            result[id]=claim
    return result


def verify(claim,person):
    if (claim.get('policy')!=POLICY or
            (claim.get('source_player_id'),claim.get('birth_date'))!=(person['source_player_id'],person['birth_date'])):
        raise ValueError('family display component identifies a different confirmed person/DOB')
    originals,confirmed=display.read_batch(claim['original_batch']);id=person['source_player_id']
    if id not in originals or confirmed[id]['birth_date']!=person['birth_date'] or claim.get('components')!=components(originals[id]):
        raise ValueError('full family display component cannot be reproduced from both original name fields')
    return [{'field':'family-component-of-original-'+r['field'],'name':r['name']} for r in claim['components']]


def verify_plan(plan):
    rows=[r for r in plan['updates'] if r.get('published_family_component') is not None]
    enabled=bool(plan.get('allow_published_family_components'))
    policy=plan.get('bindings',{}).get('published_family_component_policy')
    if not rows and not enabled and policy is None:return
    binding=plan.get('bindings',{}).get('published_person_supplement')
    if not enabled or policy!=POLICY or not binding:
        raise ValueError('full family display components require the explicitly bound original-person policy')
    path=registry.ROOT/binding['path']
    if registry.sha256_file(path)!=binding['sha256']:
        raise ValueError('family display component original-person input changed')
    wanted={r['replacement']['source_person']['source_player_id'] for r in rows}
    originals=claims(path,wanted)
    for row in rows:
        person=row['replacement']['source_person'];claim=row['published_family_component']
        if claim!=originals.get(person['source_player_id']):
            raise ValueError('family display component claim is outside the bound original-person input')
        verify(claim,person)


def native_candidates(claim,person):
    """Respect the native two-string writer's first-token given-name split.

    A bare 'di Giacomo' would silently store 'di' as the given name. Keep an
    explicit original initial for multiword surnames instead of dropping it.
    Single-token/hyphenated surnames can safely occupy the surname-only form.
    """
    verify(claim,person)
    return [{'field':'full-family-from-original-'+r['field'],
             'name':(r['explicit_given_component'][0]+'. '+r['name']
                     if ' ' in r['name'] else r['name'])}
            for r in claim['components']]
