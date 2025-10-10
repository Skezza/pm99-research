# PKF String Searcher

A powerful tool for searching strings and patterns across PKF (archive) files in Premier Manager 99. This tool helps with debugging, reverse engineering, and data analysis.

## Features

### Search Modes
- **Text Search**: Plain text string search with case-sensitive/insensitive options
- **Regex Search**: Regular expression pattern matching
- **Hex Search**: Search for hexadecimal byte patterns
- **XOR-Decoded Search**: Search content after applying XOR transformation

### Multi-Encoding Support
- UTF-8
- CP1252 (Windows-1252)
- Latin1
- Raw bytes

### Advanced Features
- **Context Preview**: Shows surrounding bytes (configurable size)
- **Hex + ASCII View**: Dual representation of matches
- **Parallel Processing**: Multi-threaded file scanning
- **Export Results**: Save to CSV or JSON format
- **Recursive Directory Scanning**: Search entire directory trees

## Usage

### GUI Interface

Access via **Tools → PKF String Searcher** in the main application.

#### Search Controls
1. **Directory**: Select the directory containing PKF files
2. **Search Query**: Enter your search term/pattern
3. **Mode**: Choose Text, Regex, or Hex search
4. **Options**:
   - Case sensitive (Text mode only)
   - Recursive directory scan
   - Encoding selection
   - XOR decode (optional)
   - Context bytes (default: 32)
   - Max results (default: 1000)

#### Results Display
- **Results List**: Shows all matches with file, entry, offset, and preview
- **Details Pane**: Full hex dump with context when a result is selected
- **Double-click**: (Future) Open in PKF Viewer at exact location

#### Export
- Click **Export CSV** to save results as CSV file
- Includes file path, offsets, hex data, and decoded text

### Command Line Interface

```bash
# Basic text search
python -m app.cli pkf-search SIMULDAT "player_name"

# Case-sensitive search
python -m app.cli pkf-search . "Beckham" --case-sensitive

# Regex search
python -m app.cli pkf-search data/ --mode regex "team.*\d+"

# Hex search
python -m app.cli pkf-search . --mode hex "48656C6C6F"

# XOR-decoded search
python -m app.cli pkf-search SIMULDAT "secret" --xor 0x5A

# Export to CSV
python -m app.cli pkf-search . "search" --export results.csv

# Custom encoding
python -m app.cli pkf-search . "text" --encoding cp1252

# Limit results and context
python -m app.cli pkf-search . "pattern" --limit 100 --context 64

# Non-recursive search
python -m app.cli pkf-search data/ "test" --no-recursive

# Custom file pattern
python -m app.cli pkf-search . "query" --file-pattern "*.PKF"
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `directory` | Directory to search | Required |
| `query` | Search string/pattern | Required |
| `--mode` | Search mode: text\|regex\|hex | text |
| `--encoding` | Text encoding | utf-8 |
| `--case-sensitive` | Enable case-sensitive search | False |
| `--xor KEY` | XOR key (hex or decimal) | None |
| `--context N` | Context bytes before/after | 32 |
| `--no-recursive` | Don't search subdirectories | False |
| `--file-pattern` | PKF file glob pattern | *.pkf |
| `--limit N` | Maximum results | 1000 |
| `--export FILE` | Export to CSV/JSON | None |
| `--no-parallel` | Disable parallel processing | False |

### Python API

```python
from pathlib import Path
from app.pkf_searcher import PKFSearcher

# Create searcher
searcher = PKFSearcher(
    directory=Path("SIMULDAT"),
    recursive=True,
    max_results=1000,
    context_size=32
)

# Text search
results = searcher.search_text("Beckham", case_sensitive=False)

# Regex search
results = searcher.search_regex(r"Team: [A-Z][a-z]+")

# Hex search
results = searcher.search_hex("48656C6C6F")  # "Hello"

# XOR-decoded search
results = searcher.search_with_xor("secret", xor_key=0x5A)

# Process results
for result in results:
    print(f"Found in {result.file_path}")
    print(f"  Entry: {result.entry_index}")
    print(f"  Offset: 0x{result.absolute_offset:08X}")
    print(f"  Match: {result.get_match_text('utf-8')}")
    print(f"  Preview:\n{result.format_preview()}")
```

## Use Cases

### 1. Find Player Name Strings
Search for specific player names across all PKF archives to locate player data structures.

```bash
python -m app.cli pkf-search SIMULDAT "Beckham" --encoding utf-8
```

### 2. Locate Numeric Patterns
Find specific numeric values (e.g., salaries, prices) using hex search.

```bash
# Search for value 1000 (0x03E8 in hex, little-endian: E8 03 00 00)
python -m app.cli pkf-search . --mode hex "E8030000"
```

### 3. Debug XOR Encoding
Test XOR decoding keys to find obfuscated strings.

```bash
python -m app.cli pkf-search data/ "team" --xor 0x5A
```

### 4. Find File References
Use regex to locate file path patterns.

```bash
python -m app.cli pkf-search . --mode regex "\\.TGA|\\.BMP"
```

### 5. Cross-File Validation
Search for team IDs across multiple archives to verify data consistency.

```bash
python -m app.cli pkf-search . --mode hex "0100" --export team_refs.csv
```

## Output Format

### Console Output
```
Searching in: SIMULDAT/
Found 2 PKF file(s)
Pattern: Beckham

Found 3 match(es) across 2 file(s):

File: SIMULDAT/archive1.pkf
  Entry 0 @ 0x00001234 (offset in entry: 0x0042):
    00001230  00 00 00 00 44 61 76 69  64 20 42 65 63 6B 68 61  ....David Beckha
    00001240  6D 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  m...............
                        ^^^^^^^^^^
```

### CSV Export
```csv
File,Entry,Entry Offset,Match Offset,Absolute Offset,Match (Hex),Match (Text),Encoding,XOR Key
archive1.pkf,0,0x00001234,0x0042,0x00001276,4265636B68616D,Beckham,utf-8,
```

### JSON Export
```json
{
  "results": [
    {
      "file": "archive1.pkf",
      "entry_index": 0,
      "entry_offset": "0x00001234",
      "match_offset": "0x0042",
      "absolute_offset": "0x00001276",
      "match_hex": "4265636B68616D",
      "match_text": "Beckham",
      "context_before_hex": "0000000044617669642",
      "context_after_hex": "0000000000000000",
      "encoding": "utf-8",
      "xor_key": null
    }
  ],
  "total": 1
}
```

## Performance Considerations

### Large File Handling
- Files are processed entry-by-entry to avoid loading entire archives into memory
- Parallel processing automatically enabled for multiple files
- Memory-mapped files used for very large PKF archives (>10MB)

### Search Optimization
- Early exit when max_results limit reached
- Parallel search across multiple files using ThreadPoolExecutor
- Efficient byte-level searching without string conversions

### Recommended Limits
- **Max Results**: 1000 (prevents extremely long searches)
- **Context Size**: 32-64 bytes (balance between context and performance)
- **File Pattern**: Use specific patterns when possible (e.g., `TEAM*.pkf`)

## Troubleshooting

### No Results Found
- Verify the search query matches the expected encoding
- Try case-insensitive search for text
- Check if XOR decoding is needed
- Ensure PKF files exist in the specified directory

### Too Many Results
- Reduce `--limit` parameter
- Use more specific search patterns
- Add regex anchors (^, $) to match precise locations
- Filter by file pattern

### Slow Searches
- Reduce `--limit` to stop earlier
- Use `--no-recursive` if subdirectories aren't needed
- Specify smaller directory scope
- Use hex search instead of text for binary patterns

### Encoding Issues
- Try different encodings (utf-8, cp1252, latin1)
- Use hex mode for binary data
- Check if XOR decoding is required

## Integration with PKF Viewer

The PKF String Searcher integrates with the PKF Viewer:
1. Search for patterns in the searcher
2. Note the file path and offset
3. Open the file in PKF Viewer
4. Navigate to the specific entry to inspect the data

## Technical Details

### Search Algorithm
- **Text Search**: Boyer-Moore-Horspool for fast string matching
- **Regex Search**: Python `re` module with compiled patterns
- **Hex Search**: Direct byte comparison
- **XOR Search**: XOR decode then search decoded data

### Memory Management
- Streaming entry processing (no full file loads)
- Configurable context size to limit memory per result
- Garbage collection between file processing

### Thread Safety
- Thread-safe result collection
- Independent searcher instances per thread
- No shared mutable state during parallel search

## Future Enhancements

Potential improvements for future versions:
- [ ] Double-click result to open in PKF Viewer at exact location
- [ ] Search history and saved searches
- [ ] Advanced filters (file size, date modified)
- [ ] Search result highlighting in hex view
- [ ] Batch search with multiple queries
- [ ] Search within decoded payloads using PKF decoder registry
- [ ] Performance profiling and optimization dashboard

## See Also

- [`pkf.py`](../app/pkf.py) - PKF file format parser
- [`pkf_searcher.py`](../app/pkf_searcher.py) - Core search engine
- [PKF Viewer Documentation](PKF_VIEWER.md) - PKF archive inspection tool
