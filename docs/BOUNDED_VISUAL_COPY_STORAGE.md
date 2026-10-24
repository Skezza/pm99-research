# Storage for bounded artwork builds

Visual patch application shares only the immutable media paths `SIMULDAT/`,
`SFX/`, `RECURSOS.PKF` and `IMG.PKF` with its registered source. All native
databases, portrait/kit archives, executables, configuration and saves remain
independent regular copies. Artwork writes cannot target the shared media
paths. The general portrait copy function remains unchanged for other callers.

The copy requires one filesystem, rejects symlinks, verifies complete source
and output inventories, and checks that only allowlisted files share inodes.
A link failure aborts and removes only the new partial output; it does not
fall back to a larger, unbudgeted copy. The copy receipt records linked and
independently copied files. Release orchestration additionally preserves its
larger disk reserve.

Sharing media changes inode link counts and filesystem metadata, not file
contents or game paths. Registered releases remain immutable inputs. Actual
gameplay and runner captures use disposable copies; do not mutate shared
factory media in place.
