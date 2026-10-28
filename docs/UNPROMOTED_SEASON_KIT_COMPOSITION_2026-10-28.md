# Compose a kit correction before release promotion

The Python stock-kit materialiser accepts `allow_registered_parent=True` when the
bound approval receipt also contains that literal boolean. The exact parent
release ID, manifest, checklist, source archive hashes and selected cases remain
mandatory. The default still requires the preferred release.

This permits one final release to combine an already built club/manager correction
with a same-club factory kit correction before installation. It avoids publishing
an intermediate state merely to add artwork. It does not grant promotion or
certify historical kit design.

The existing visual materialiser and kit extension accept the explicit immutable
`source_release`, as their apply/publish counterparts already do. Season and
input bindings are checked; all unselected archive bytes remain unchanged.

Verification: 32 focused stock-kit, visual-patch and reconstruction tests passed.
Independent full recipe and game reconstruction also matched for the 2024/25
Sparta and 2025/26 Rennes composed candidates (r483 and r482). These build proofs
are distinct from runner verification and preferred-release installation.
