"""Regression of generic I/O and destructive migration boundaries."""
import hashlib
import io
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import json_storage_v1 as storage
from scripts import json_storage_io_v1 as adapter
from scripts import json_storage_batches_v2 as batches
from scripts import season_pipeline_v2 as pipeline


@pytest.fixture
def raw():
    return json.dumps({'name': 'Jos\u00e9', 'players': ['unchanged'] * 110000}, ensure_ascii=False).encode() + b'\n'


def test_plain_binary_and_nonpath_objects_are_delegated_exactly(tmp_path):
    path = tmp_path / 'game.FDI';data = b'\x00\xff\x10'
    assert adapter.write_bytes(path, data) == len(data)
    assert adapter.read_bytes(path) == data
    assert adapter.open_file(path, 'rb').read() == data
    class Resource:
        def read_text(self, encoding='special'):
            return encoding
    assert adapter.read_text(Resource()) == 'special'
    assert adapter.move('one-two', '-', '_', replace=True) == 'one_two'


def test_auto_is_limited_to_audited_roots_and_preserves_existing_formats(tmp_path, raw, monkeypatch):
    monkeypatch.setattr(adapter, 'ROOT', tmp_path)
    monkeypatch.setattr(adapter, 'AUTO_ROOTS', {'audited'})
    folder = tmp_path / '.local/audited';folder.mkdir(parents=True)
    path = folder / 'large.json'
    adapter.write_bytes(path, raw)
    assert not path.exists() and storage.compressed_path(path).exists()
    assert adapter.read_bytes(path) == raw
    adapter.write_bytes(path, b'{"smaller":true}\n')
    assert not path.exists() and adapter.read_text(path) == '{"smaller":true}\n'
    plain = folder / 'plain.json';plain.write_bytes(b'{}')
    adapter.write_bytes(plain, raw)
    assert plain.exists() and not storage.compressed_path(plain).exists()
    outside = tmp_path / '.local/unreviewed';outside.mkdir()
    adapter.write_bytes(outside / 'large.json', raw)
    assert (outside / 'large.json').exists()
    small = folder / 'small.json';adapter.write_bytes(small, b'{}')
    assert small.exists()
    game = folder / 'game';game.mkdir();adapter.write_bytes(game / 'config.json', raw)
    assert (game / 'config.json').exists()


def test_streams_discovery_stats_prefix_and_physical_frame_access(tmp_path, raw):
    p = tmp_path / 'input.json';storage.write_bytes(p, raw, compressed=True)
    with adapter.open_file(p, 'rb') as handle:
        assert handle.read() == raw
        handle.seek(0);assert handle.read(12) == raw[:12]
    with adapter.open_file(p, encoding='utf8') as handle:
        assert json.load(handle)['name'] == 'Jos\u00e9'
    assert list(adapter.glob(tmp_path, '*.json')) == [p]
    assert list(adapter.glob(tmp_path, '*.json', recursive=True)) == [p]
    assert adapter.resolve(p, strict=True) == p
    meta = adapter.stat_result(p)
    assert meta.st_size == len(raw) and meta.st_mtime_ns == storage.physical_path(p).stat().st_mtime_ns
    assert adapter.prefix(p, 21) == raw[:21]
    assert adapter.prefix(p, 21, tail=True) == raw[-21:]
    frame = storage.compressed_path(p)
    assert adapter.read_bytes(frame) == frame.read_bytes()
    assert adapter.size(frame) == frame.stat().st_size


def test_compressed_stream_write_and_exception_never_publish_partial_data(tmp_path, raw):
    p = tmp_path / 'input.json';storage.write_bytes(p, raw, compressed=True)
    with pytest.raises(RuntimeError):
        with adapter.open_file(p, 'w', encoding='utf8') as handle:
            handle.write('partial')
            raise RuntimeError('abort')
    assert storage.read_bytes(p) == raw
    with adapter.open_file(p, 'w', encoding='utf8') as handle:
        json.dump({'complete': True}, handle)
    assert storage.read_json(p) == {'complete': True} and not p.exists()
    with pytest.raises(FileExistsError):
        adapter.open_file(p, 'xb')


def test_copy_move_link_and_same_file_behavior(tmp_path, raw):
    p = tmp_path / 'input.json';storage.write_bytes(p, raw, compressed=True)
    with pytest.raises(shutil.SameFileError):
        adapter.copy_file(p, p)
    assert adapter.move(p, p, replace=True) == p
    assert storage.read_bytes(p) == raw
    target = tmp_path / 'copy.json';adapter.copy_file(p, target, metadata=True)
    assert storage.read_bytes(target) == raw and not target.exists()
    linked = tmp_path / 'linked.json';adapter.link(target, linked)
    assert os.path.samefile(storage.physical_path(target), storage.physical_path(linked))
    moved = tmp_path / 'moved.json';adapter.move(p, moved, replace=True)
    assert not storage.is_file(p) and storage.read_bytes(moved) == raw
    adapter.unlink(linked);assert not storage.is_file(linked)


@pytest.fixture
def group(tmp_path, raw, monkeypatch):
    monkeypatch.setattr(batches.shutil, 'disk_usage', lambda _: SimpleNamespace(free=100 * 1024**3))
    paths = [tmp_path / '.local/history/one/input.json', tmp_path / '.local/history/two/input.json']
    for p in paths:p.parent.mkdir(parents=True)
    paths[0].write_bytes(raw);paths[0].chmod(0o640);os.link(paths[0], paths[1])
    s = paths[0].stat()
    value = {'paths':[str(p.relative_to(tmp_path)) for p in paths], 'logical_bytes':len(raw),
             'allocated_bytes':s.st_blocks*512, 'links':2, 'uid':s.st_uid,'gid':s.st_gid,
             'mode':0o640,'mtime_ns':s.st_mtime_ns,'sha256':hashlib.sha256(raw).hexdigest()}
    return paths, value, raw


def test_shared_alias_group_roundtrip_preserves_bytes_metadata_and_sharing(group, tmp_path):
    paths, value, raw = group
    log = tempfile.TemporaryFile(mode='w+')
    after = batches.convert_group(value, log, root=tmp_path)
    assert after < value['allocated_bytes']
    assert all(storage.read_bytes(p) == raw for p in paths)
    assert os.path.samefile(*(storage.physical_path(p) for p in paths))
    assert all(storage.physical_path(p).stat().st_mtime_ns == value['mtime_ns'] for p in paths)
    batches.convert_group(value, log, root=tmp_path, restore=True)
    assert all(p.read_bytes() == raw for p in paths) and os.path.samefile(*paths)
    assert paths[0].stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize('failure', ['target-published','source-retired'])
def test_interrupted_groups_recover_deterministically(group, tmp_path, monkeypatch, failure):
    paths, value, raw = group
    event = batches._event;failed = False
    def crash(handle, **row):
        nonlocal failed
        event(handle, **row)
        if row['event'] == failure and not failed:
            failed = True
            raise RuntimeError('power interruption')
    monkeypatch.setattr(batches, '_event', crash)
    with pytest.raises(RuntimeError):
        batches.convert_group(value, tempfile.TemporaryFile(mode='w+'), root=tmp_path)
    monkeypatch.setattr(batches, '_event', event)
    batches.convert_group(value, tempfile.TemporaryFile(mode='w+'), root=tmp_path, recover=True)
    assert all(storage.read_bytes(p) == raw for p in paths)
    assert os.path.samefile(*(storage.physical_path(p) for p in paths))


def test_group_hash_change_external_alias_and_disk_reserve_are_refused(group, tmp_path, monkeypatch):
    paths, value, raw = group
    wrong = dict(value, sha256='0'*64)
    with pytest.raises(storage.StorageError, match='original bytes'):
        batches.convert_group(wrong, tempfile.TemporaryFile(mode='w+'), root=tmp_path)
    external = tmp_path / 'external';os.link(paths[0], external)
    with pytest.raises(storage.StorageError, match='external links'):
        batches.convert_group(value, tempfile.TemporaryFile(mode='w+'), root=tmp_path)
    external.unlink()
    monkeypatch.setattr(batches.shutil, 'disk_usage', lambda _:SimpleNamespace(free=batches.MIN_RESERVE))
    with pytest.raises(storage.StorageError, match='reserve'):
        batches.convert_group(value, tempfile.TemporaryFile(mode='w+'), root=tmp_path)
    assert all(p.read_bytes() == raw for p in paths)


def test_plain_path_semantics_and_native_copy_move(tmp_path):
    p=tmp_path/'plain.json';p.write_bytes(b'\xef\xbb\xbfnot-json\r\n')
    link=tmp_path/'link.json';link.symlink_to(p)
    dangling=tmp_path/'dangling.json';dangling.symlink_to(tmp_path/'missing')
    directory=tmp_path/'directory.json';directory.mkdir()
    assert adapter.exists(link) and adapter.is_file(link)
    assert not adapter.exists(dangling) and not adapter.is_file(dangling)
    assert adapter.exists(directory) and not adapter.is_file(directory)
    assert set(adapter.glob(tmp_path,'*.json'))==set(tmp_path.glob('*.json'))
    assert adapter.read_text(link)==link.read_text()
    target=tmp_path/'copied.json';adapter.copy_file(p,target,metadata=True)
    assert target.read_bytes()==p.read_bytes()
    inode=target.stat().st_ino;renamed=tmp_path/'renamed.json'
    adapter.move(target,renamed,replace=True)
    assert renamed.stat().st_ino==inode
    with pytest.raises(storage.StorageError):adapter.move(renamed,tmp_path/'wrong.json.zst')


def test_text_newline_positional_encoding_and_abandoned_buffer(tmp_path):
    import gc
    p=tmp_path/'text.json';raw='{"name":"Jos\u00e9"}\r\n'.encode()
    storage.write_bytes(p,raw,compressed=True)
    assert adapter.read_text(p,encoding='utf8')=='{"name":"Jos\u00e9"}\n'
    with adapter.open_file(p,'r',-1,'utf8',None,'') as handle:assert handle.read()==raw.decode()
    handle=adapter.open_file(p,'wb');handle.write(b'{"partial":true}');del handle;gc.collect()
    assert storage.read_bytes(p)==raw


def test_link_opposite_representation_and_shared_writes_are_refused(tmp_path,raw):
    a=tmp_path/'a.json';b=tmp_path/'b.json'
    a.write_bytes(raw);storage.write_bytes(b,raw,compressed=True)
    with pytest.raises(FileExistsError):adapter.link(a,b)
    c=tmp_path/'c.json';adapter.link(b,c)
    with pytest.raises(storage.StorageError,match='immutable'):adapter.write_bytes(b,b'{}')
    assert storage.read_bytes(c)==raw


@pytest.mark.parametrize('restore',[False,True])
def test_interrupted_both_directions_and_external_new_alias(group,tmp_path,monkeypatch,restore):
    paths,value,raw=group
    log=tempfile.TemporaryFile(mode='w+')
    if restore:batches.convert_group(value,log,root=tmp_path)
    event=batches._event
    def crash(handle,**row):
        event(handle,**row)
        if row['event']=='source-retired':raise RuntimeError('interrupt')
    monkeypatch.setattr(batches,'_event',crash)
    with pytest.raises(RuntimeError):batches.convert_group(value,log,root=tmp_path,restore=restore)
    monkeypatch.setattr(batches,'_event',event)
    batches.convert_group(value,log,root=tmp_path,restore=restore,recover=True)
    assert all(storage.read_bytes(p)==raw for p in paths)
    if not restore:
        extra=tmp_path/'.local/history/third.json';os.link(storage.physical_path(paths[0]),storage.compressed_path(extra))
        with pytest.raises(storage.StorageError,match='external'):
            batches.convert_group(value,log,root=tmp_path,restore=True)
        assert all(storage.read_bytes(p)==raw for p in paths)


def test_apply_path_exclusions_cannot_be_bypassed(tmp_path):
    with pytest.raises(storage.StorageError,match='excluded'):
        batches._validate_paths({'paths':['.local/season-release-registry-v1/forged.json']},tmp_path)


def test_transitive_pin_and_inbound_symlink_detection(tmp_path):
    (tmp_path/'data').mkdir();(tmp_path/'data/preferred-season-releases-v1.json').write_text('{"seasons":[{"season":"2022-23","release_id":"current"}]}')
    locator=tmp_path/'.local/season-release-registry-v1/releases/2022-23/current/locator.json'
    locator.parent.mkdir(parents=True)
    history=tmp_path/'.local/history/2022-23';history.mkdir(parents=True)
    recipe=history/'recipe.json';child=history/'child.json';child.write_text('{}')
    recipe.write_text('{"input":"child.json"}')
    locator.write_text(json.dumps({'recipe':str(recipe.relative_to(tmp_path))}))
    pins,_=batches.protected_paths(tmp_path)
    assert recipe in pins and child in pins
    (tmp_path/'pointer').symlink_to(child)
    assert child in batches.inbound_json_symlinks(tmp_path)


def test_sigkill_leaves_journal_and_recovery_completes(group,tmp_path):
    import subprocess,sys
    paths,value,raw=group
    spec=tmp_path/'group.json';spec.write_text(json.dumps(value))
    code='''import json,os,signal,sys
from pathlib import Path
from scripts import json_storage_batches_v2 as b
root=Path(sys.argv[1]);group=json.loads((root/'group.json').read_text())
b.MIN_RESERVE=0
original=b._event
def crash(handle,**row):
 original(handle,**row)
 if row['event']=='source-retired':os.kill(os.getpid(),signal.SIGKILL)
b._event=crash
with (root/'journal.jsonl').open('w') as handle:b.convert_group(group,handle,root=root)
'''
    run=subprocess.run([sys.executable,'-c',code,str(tmp_path)],cwd=batches.ROOT)
    assert run.returncode==-9
    batches.convert_group(value,tempfile.TemporaryFile(mode='w+'),root=tmp_path,recover=True)
    assert all(storage.read_bytes(p)==raw for p in paths)
    assert not list(paths[0].parent.glob('.json-storage-*'))


@pytest.mark.parametrize('utf8mode',['0','1'])
def test_python_locale_defaults_match_path(tmp_path,utf8mode):
    import subprocess,sys
    p=tmp_path/'plain.json';p.write_bytes('{"name":"Jos\u00e9"}\r\n'.encode())
    packed=tmp_path/'packed.json';storage.write_bytes(packed,p.read_bytes(),compressed=True)
    code='''from pathlib import Path
import sys
from scripts import json_storage_io_v1 as a
root=Path(sys.argv[1])
def outcome(f):
 try:return ('ok',f())
 except UnicodeError as e:return(type(e).__name__,)
assert outcome(lambda:(root/'plain.json').read_text())==outcome(lambda:a.read_text(root/'packed.json'))
'''
    env=dict(os.environ,LC_ALL='C',PYTHONUTF8=utf8mode,PYTHONCOERCECLOCALE='0')
    subprocess.run([sys.executable,'-c',code,str(tmp_path)],cwd=batches.ROOT,env=env,check=True)


def test_atomic_replace_retains_compressed_format_and_temporary_metadata(tmp_path):
    p=tmp_path/'out.json';storage.write_bytes(p,b'{}',compressed=True)
    temp=tmp_path/'write.tmp';temp.write_bytes(b'{"atomic":true}\n')
    adapter.replace_file(str(temp),str(p))
    assert not temp.exists() and not p.exists() and storage.read_json(p)=={'atomic':True}
    temp.write_bytes(b'{"copied":true}')
    adapter.copy_file(temp,p)
    assert not p.exists() and storage.read_json(p)=={'copied':True}
    with pytest.raises(storage.StorageError):adapter.link(storage.compressed_path(p),tmp_path/'wrong.json')
    with pytest.raises(storage.StorageError):adapter.link(temp,tmp_path/'wrong.json.zst')


def test_policy_shared_control_and_game_exclusions(tmp_path,monkeypatch):
    monkeypatch.setattr(adapter,'ROOT',tmp_path);monkeypatch.setattr(adapter,'AUTO_ROOTS',{'history'})
    for rel in ['.local/history/current.json','.local/history/working.json','.local/history/coverage-matrix-current.json','.local/history/game/receipt.json']:
        assert batches.excluded(rel) and not adapter.automatic(tmp_path/rel)
    assert adapter.automatic(tmp_path/'.local/history/revisions/old/evidence.json')


def test_path_reference_scanner_keeps_escaped_names_and_directory_prefix(tmp_path):
    values={'a':'sub/a.json','b':'odd"quote.json','c':'.local/history','d':str(tmp_path/'.local/history/folder')}
    text=json.dumps(values)
    files,locals_=batches._path_strings(text,tmp_path)
    assert set(files)=={'sub/a.json','odd"quote.json'}
    assert set(locals_)=={values['c'],values['d']}


def test_recover_cli_requires_journal_and_preserves_restore_direction(tmp_path,monkeypatch):
    import sys
    journal=tmp_path/'journal.jsonl';manifest={'schema':'pm99-json-storage-batch-v2'}
    journal.write_text(json.dumps({'event':'batch-prepared','manifest':manifest,'restore':True})+'\n')
    received=[]
    monkeypatch.setattr(batches,'apply',lambda value,output,**kwargs:received.append((value,kwargs)))
    monkeypatch.setattr(sys,'argv',['batches','recover',str(journal),'--output',str(tmp_path/'next.jsonl')])
    batches.main();assert received==[(manifest,{'restore':True,'recover':True})]
    journal.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='journal'):batches.main()


def test_mechanical_checker_detects_native_atomic_and_builtin_bypasses():
    from scripts.check_json_storage_io_v2 import violations
    assert len(violations('import os\nopen(path)\nos.replace(a,b)\nos.path.exists(path)\n'))==3


def test_glob_skips_inaccessible_directory_and_plain_prefix_follows_symlinks(tmp_path):
    p=tmp_path/'input.json';p.write_bytes(b'{}\r\n')
    symlink=tmp_path/'link.json';symlink.symlink_to(p)
    assert adapter.prefix(symlink,2,tail=True)==b'\r\n'
    denied=tmp_path/'denied';denied.mkdir();(denied/'hidden.json').write_text('{}');denied.chmod(0)
    try:assert set(adapter.glob(tmp_path,'*.json',recursive=True))==set(tmp_path.rglob('*.json'))
    finally:denied.chmod(0o700)


def test_dedup_temporary_never_receives_frame_bytes(tmp_path):
    a=tmp_path/'a.json';b=tmp_path/'b.json';storage.write_bytes(a,b'{}',compressed=True);b.write_bytes(b'{}')
    temporary=tmp_path/'b.json.verified-link'
    with pytest.raises(storage.StorageError,match='logical'):adapter.link(a,temporary)
    assert not temporary.exists() and b.read_bytes()==b'{}'
    assert adapter.is_compressed(a) and not adapter.is_compressed(b)
    with pytest.raises(storage.StorageError):adapter.copy_file(storage.compressed_path(a),b)
    adapter.copy_file(a,temporary,metadata=True);assert temporary.read_bytes()==b'{}'
    temporary.chmod(0o600);os.utime(temporary,ns=(123456789000,123456789000))
    adapter.replace_file(temporary,a)
    meta=storage.physical_path(a).stat()
    assert meta.st_mode&0o777==0o600 and meta.st_mtime_ns==123456789000


def test_direct_bare_adapter_import_and_policy(tmp_path):
    import subprocess,sys
    code="import json_storage_io_v1 as a; from pathlib import Path; assert not a.automatic(Path(a.ROOT)/'.local/history/current.json'); a.assert_plain_reference_scan([Path('.')])"
    subprocess.run([sys.executable,'-I','-c','import sys; sys.path.insert(0,sys.argv[1]);'+code,str(batches.ROOT/'scripts')],cwd=tmp_path,check=True)


def test_shallow_glob_does_not_walk_nested_game_assets(tmp_path,monkeypatch):
    folder=tmp_path/'release';folder.mkdir();p=folder/'input.json';storage.write_bytes(p,b'{}',compressed=True)
    game=folder/'game/deep/assets';game.mkdir(parents=True);(game/'not-a-source.json').write_text('{}')
    original=adapter.os.walk;visited=[]
    def observe(*args,**kwargs):
        for row in original(*args,**kwargs):visited.append(Path(row[0]));yield row
    monkeypatch.setattr(adapter.os,'walk',observe)
    assert list(adapter.glob(tmp_path,'*/*.json'))==[p]
    assert folder/'game' not in visited


def test_reference_cache_deduplicates_repeated_source_paths(tmp_path):
    text=json.dumps(['sub/input.json']*10000+['.local/history/input.json']*10000)
    files,local=batches._path_strings(text,tmp_path)
    assert set(files)=={'sub/input.json','.local/history/input.json'} and len(files)==2
    assert local==('.local/history/input.json',)
    history=tmp_path/'.local/history';history.mkdir(parents=True)
    (tmp_path/'directory-alias').symlink_to(history,target_is_directory=True)
    assert history in batches.inbound_json_symlinks(tmp_path)


def test_abandoned_text_handle_never_publishes_a_valid_partial_object(tmp_path):
    import gc
    p=tmp_path/'input.json';storage.write_bytes(p,b'{}',compressed=True)
    handle=adapter.open_file(p,'w',encoding='utf8');handle.write('{"unfinished":true}');del handle;gc.collect()
    assert storage.read_bytes(p)==b'{}'


def test_parent_reference_extraction_matches_json_keys_not_string_values():
    doc={'release_id':'first','nested':[{'parent_release_id':'second'},{'source_release_id':'first'}],
         'string':'release_id','ignored_number':{'release_id':5},'quote':'a"release_id"b'}
    assert batches._parent_strings(json.dumps(doc,indent=2))=={'first','second'}


def test_archive_member_hash_is_physical_and_source_hash_stays_logical(tmp_path):
    import tarfile
    from scripts import season_release_registry_v1 as registry
    p=tmp_path/'input.json';raw=b'{"original":true}\n';storage.write_bytes(p,raw,compressed=True)
    frame=adapter.physical_path(p);assert frame==storage.compressed_path(p)
    physical=adapter.physical_sha256_file(frame)
    assert physical==hashlib.sha256(frame.read_bytes()).hexdigest()
    assert registry.sha256_file(p)==registry.sha256_file(frame)==hashlib.sha256(raw).hexdigest()
    assert physical!=registry.sha256_file(p)
    archive=tmp_path/'archive.tar.gz'
    with tarfile.open(archive,'w:gz') as bundle:bundle.add(frame,arcname=frame.name,recursive=False)
    with tarfile.open(archive) as bundle:
        member=bundle.extractfile(frame.name);assert hashlib.file_digest(member,'sha256').hexdigest()==physical


def test_plain_only_retirement_scan_refuses_compressed_references(tmp_path):
    (tmp_path/'plain.json').write_text('{}');adapter.assert_plain_reference_scan([tmp_path])
    storage.write_bytes(tmp_path/'retained.json',b'{"source":"must-stay"}',compressed=True)
    with pytest.raises(storage.StorageError,match='reference scan'):adapter.assert_plain_reference_scan([tmp_path])
    assert storage.read_json(tmp_path/'retained.json')=={'source':'must-stay'}


def test_retirement_reference_scan_decodes_frames_and_spans_chunks(tmp_path,monkeypatch):
    p=tmp_path/'retained.json';raw=b'{"source":"123456important-source"}'
    storage.write_bytes(p,raw,compressed=True)
    monkeypatch.setattr(storage,'CHUNK',8)
    assert adapter.find_json_reference([tmp_path],'important-source')==p
    assert adapter.find_json_reference([tmp_path],'absent-source') is None
    storage.compressed_path(p).write_bytes(b'corrupt frame')
    with pytest.raises(storage.StorageError):adapter.find_json_reference([tmp_path],'absent-source')
    with pytest.raises(FileNotFoundError):adapter.find_json_reference([tmp_path/'missing'],'source')
