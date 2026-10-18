"""Store rejected replay recovery as exact base archive plus tiny byte delta."""
import hashlib
import tarfile
from scripts.archive_rejected_rating_trial_20261011 import ROOT
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

def main():
    archive_root=ROOT/'rejected-recovery';rows=[];saved=0
    for b in pipeline.read_json_file(ROOT/'pinned-baselines.json'):
        season=b['season'];ap=archive_root/(season+'-r100a-receipt.json');bp=archive_root/(season+'-r100b-receipt.json')
        if not ap.exists() or not bp.exists():continue
        a=pipeline.read_json_file(ap);b=pipeline.read_json_file(bp)
        full_a=registry.ROOT/a['archive'];full_b=registry.ROOT/b['archive']
        patch=archive_root/(season+'-r100b-delta.tar.gz');receipt=archive_root/(season+'-replay-recovery-sharing.json')
        if not full_b.exists():
            if not receipt.exists():raise ValueError('missing unreceipted replay recovery')
            rows.append(pipeline.read_json_file(receipt));continue
        if registry.sha256_file(full_a)!=a['archive_sha256'] or registry.sha256_file(full_b)!=b['archive_sha256']:
            raise ValueError('rejected full recovery hash differs')
        differences={name for name,digest in b['archived_member_hashes'].items() if a['archived_member_hashes'].get(name)!=digest}
        if not patch.exists():
            with tarfile.open(full_b,'r:gz') as source,tarfile.open(patch,'w:gz') as output:
                for name in sorted(differences):
                    member=source.getmember(name);output.addfile(member,source.extractfile(member))
        with tarfile.open(full_a,'r:gz') as base,tarfile.open(patch,'r:gz') as change:
            if {m.name for m in change.getmembers()}!=differences:raise ValueError('rejected replay delta member set differs')
            for name,digest in b['archived_member_hashes'].items():
                source=change if name in differences else base
                if hashlib.file_digest(source.extractfile(name),'sha256').hexdigest()!=digest:raise ValueError('rejected replay reconstruction differs')
        row=dict(season=season,original_replay_receipt=registry.relative_workspace_path(bp),
            original_full_archive=registry.relative_workspace_path(full_b),original_full_archive_sha256=b['archive_sha256'],
            recovery_base_archive=registry.relative_workspace_path(full_a),base_sha256=registry.sha256_file(full_a),
            recovery_delta_archive=registry.relative_workspace_path(patch),delta_sha256=registry.sha256_file(patch),
            exact_original_member_hashes=b['archived_member_hashes'],recovery_content_byte_identical=True,
            note='Compressed container superseded; every original recipe/native/metadata member remains exactly recoverable. Existing playable games untouched.')
        retained(receipt,row);saved+=full_b.stat().st_size-patch.stat().st_size
        full_b.unlink();rows.append(row)
    retained(ROOT/'rejected-recovery-representation-index.json',rows)
    print(dict(replay_recovery_containers_shared=len(rows),bytes_saved=saved,all_recovery_content_preserved=True),flush=True)

if __name__=='__main__':main()
