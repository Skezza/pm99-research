# Recursively replace whole-word 'pm99_editor' with 'app' in text files
$include = '*.py','*.md','*.txt','*.rst','*.ini','*.cfg','*.yml','*.yaml','*.html'
$files = Get-ChildItem -Recurse -File -Include $include -ErrorAction SilentlyContinue
foreach ($f in $files) {
    $full = $f.FullName
    if ($full -like '*\.git\*' -or $full -like '*\.pytest_cache\*' -or $full -like '*\DBDAT\*' -or $full -like '*\FDI-PKF\*' -or $full -like '*\htmlcov\*') {
        continue
    }
    try {
        $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $full
    } catch {
        Write-Output "SKIP (read failed): $full"
        continue
    }
    $new = [regex]::Replace($content, '\bpm99_editor\b', 'app')
    if ($new -ne $content) {
        Set-Content -Encoding UTF8 -LiteralPath $full -Value $new
        Write-Output "UPDATED $full"
    }
}