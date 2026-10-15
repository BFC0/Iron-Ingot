$ErrorActionPreference = 'Stop'
$taskRoot = '.'
$taskDocx = Join-Path $taskRoot '预测模型与变量说明.docx'
$taskPdf = Join-Path $PSScriptRoot 'preview.pdf'
$taskWord = $null
$taskDocument = $null
try {
    $taskWord = New-Object -ComObject Word.Application
    $taskWord.Visible = $false
    $taskWord.DisplayAlerts = 0
    $taskDocument = $taskWord.Documents.Open($taskDocx, $false, $true)
    $taskDocument.Repaginate()
    $taskPageCount = $taskDocument.ComputeStatistics(2)
    $taskEquationCount = $taskDocument.OMaths.Count
    $taskDocument.ExportAsFixedFormat($taskPdf, 17)
    Write-Output "Word preview: $taskPageCount pages; $taskEquationCount native equations."
} finally {
    if ($null -ne $taskDocument) { $taskDocument.Close(0); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($taskDocument) }
    if ($null -ne $taskWord) { $taskWord.Quit(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($taskWord) }
}
