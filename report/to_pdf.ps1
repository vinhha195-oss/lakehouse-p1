# Convert a .docx to .pdf with Microsoft Word (COM). Usage: powershell -File report\to_pdf.ps1 in.docx out.pdf
param([string]$In, [string]$Out)
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open((Resolve-Path $In).Path, $false, $true)
    $doc.ExportAsFixedFormat($Out, 17)   # 17 = wdExportFormatPDF
    "pages: " + $doc.ComputeStatistics(2)  # 2 = wdStatisticPages
    $doc.Close($false)
} finally {
    $word.Quit()
}
