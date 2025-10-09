# Final Filter Adjustments - Summary

## Changes Made

### 1. Teams Filter - Significantly Relaxed

**Problem:** Only 2 teams showing (was WAY too strict)

**Changes:**
- Removed 2-letter garbage prefix filter ("Aa", "Ba", "Ca"...) - too aggressive
- Removed random character pattern check - caught legitimate teams
- Made 3-letter prefix check ("Tva", "Uxa") conditional:
  - Only rejects if NO team indicators found in rest of name
  - Team indicators: FC, AC, AS, CF, United, City, Town, Football, Club, etc.
- Kept only OBVIOUS multi-'a' patterns: "Baaa", "Caaa", "Daaa", etc.

**Result:** Should now show 50-70+ valid teams

### 2. Coaches Filter - Added Player Blocklist

**Problem:** Many players showing in coaches list

**Added ~50 known player names to blocklist:**
```python
'boa morte', 'rui barros', 'mark hatelely', 'stan collymore',
'jamie redknapp', 'bobby moore', 'bryan robson', 'nick barmby',
'darren huckerby', 'michael gray', 'fabrizio ravanelli',
'roberto baggio', 'marcus stewart', 'wayne allison', 'keith gillespie',
# ... and many more
```

**Also added:**
- Descriptors: "scottish footballer", "french football", "second world"
- Additional stadiums: "highfield road", "shepshed charterhouse", "filbert street"

**Result:** Should filter out most visible players

## Testing Results

✓ All unit tests pass (4/4)
```bash
python -m pytest tests/test_loaders.py -v
> 4 passed in 8.34s ✓
```

## Expected GUI Results

### Teams Tab:
**Before:** 2 teams  
**After:** 50-70+ teams

Should now include:
- ✓ Sportiva Lazio (was showing)
- ✓ Premier League teams (Arsenal, Man United, Liverpool, etc.)
- ✓ La Liga teams (Real Madrid, Barcelona, etc.)
- ✓ Serie A teams (Juventus, Milan, etc.)
- ✓ Other European leagues

Should NOT include:
- ✗ Garbage prefixes like "TvaManchester United"
- ✗ Embedded garbage like "ZorrillawHvaReal"
- ✗ GomesNGvaC.F. patterns (has embedded NGva)

### Coaches Tab:
**Before:** ~200 entries (mixed coaches, players, locations)  
**After:** ~80-120 actual coach names

Should now EXCLUDE (blocked):
- ✗ Players: Boa Morte, Stan Collymore, Jamie Redknapp, etc.
- ✗ Locations: Highfield Road, Shepshed Charterhouse, Filbert Street
- ✗ Descriptors: Scottish Footballer, French Football, Second World

Should INCLUDE (valid coaches):
- ✓ Arsene Wenger
- ✓ Alex Ferguson  
- ✓ Glenn Hoddle
- ✓ George Graham
- ✓ Brian Kidd
- ✓ Howard Kendall
- ✓ Walter Smith
- ✓ And other actual managers

## Why This Approach

The FDI files contain biographical text about coaches, and our parser extracts ANY two-word phrase as a potential coach name. This means:

1. **Player names appear** because coach bios mention players they managed
2. **Stadium names appear** because bios mention where coaches worked
3. **Phrases appear** because bios describe careers

The blocklist approach is necessary because there's no structural way to distinguish coach names from biographical content in the file format.

## Files Modified

**[`pm99_editor/loaders.py`](pm99_editor/loaders.py)**
- Lines 119-136: Relaxed team 3-letter prefix filter
- Lines 147-152: Removed overly strict team filters
- Lines 284-295: Added ~50 player names to coach blocklist
- Lines 341-347: Added descriptors and locations to blocklist

## Next Steps

1. Test in GUI: `python -m pm99_editor.gui`
2. Navigate to Teams tab - should see 50-70+ teams
3. Navigate to Coaches tab - should see clean coach names only
4. If any players/locations still appear, add them to blocklist

## Note on Filtering Philosophy

We've moved from:
- ✗ **Over-filtering** (rejecting valid data) 
- ✓ **Targeted filtering** (blocking known bad patterns and specific names)

This gives better results while maintaining data quality.