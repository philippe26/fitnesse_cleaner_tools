Attribute VB_Name = "ExportReviewJSON"
Option Explicit

' ============================================================
'  ExportReviewJSON.bas  —  Excel VBA (Office 2016+)
'  Exports review rows from the "Remarks" sheet to a JSON file
'  compatible with mhtml-cleaner -R.
'
'  Installation:
'    Alt+F11 -> File -> Import File -> select this .bas
'    OR: Alt+F11 -> Insert -> Module, then paste the content.
'
'  Usage: run ExportReviewJSON()
' ============================================================

Private Const DATA_START  As Long = 15  ' First data row (row 14 is blank)

' Column indices (1-based)
Private Const COL_PEER    As Long = 1   ' A  Peer
Private Const COL_NO      As Long = 2   ' B  No.
Private Const COL_SECTION As Long = 4   ' D  Section
Private Const COL_REMARKS As Long = 5   ' E  Remarks
Private Const COL_TYPE    As Long = 6   ' F  Type

' Valid review types — any other value in Type column is skipped
Private Const VALID_TYPES As String = "|Operational|Significant|Major|Minor|Typo|Comment|"

' ============================================================
'  Entry point
' ============================================================
Public Sub ExportReviewJSON()

    ' 1. Locate sheet
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ThisWorkbook.Sheets("Remarks")
    On Error GoTo 0
    If ws Is Nothing Then
        MsgBox "Sheet 'Remarks' not found.", vbExclamation
        Exit Sub
    End If

    ' 2. Choose output file
    '    GetSaveAsFilename returns False (Boolean) on cancel
    Dim vPath As Variant
    vPath = Application.GetSaveAsFilename( _
        InitialFileName:="reviews.json", _
        FileFilter:="JSON files (*.json),*.json,All files (*.*),*.*", _
        Title:="Export reviews to JSON")
    If VarType(vPath) = vbBoolean Then Exit Sub
    Dim fPath As String: fPath = CStr(vPath)

    ' 3. Collect rows
    Dim entries() As String
    Dim count     As Long
    count = 0
    ReDim entries(0)

    Dim r     As Long
    Dim peer  As String
    Dim sect  As String
    Dim rem   As String
    Dim typ   As String
    Dim entry As String

    r = DATA_START
    Do While r <= ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1
        peer = Trim(CStr(ws.Cells(r, COL_PEER).Value))
        sect = Trim(CStr(ws.Cells(r, COL_SECTION).Value))
        rem  = Trim(CStr(ws.Cells(r, COL_REMARKS).Value))
        typ  = Trim(CStr(ws.Cells(r, COL_TYPE).Value))

        ' Skip empty rows and rows with invalid/empty Type
        If peer = "" And sect = "" And rem = "" Then
            r = r + 1
            GoTo NextRow
        End If
        If InStr(VALID_TYPES, "|" & typ & "|") = 0 Then
            r = r + 1
            GoTo NextRow
        End If

        ' Retrieve date from cell comment if present
        Dim sDate As String
        sDate = ""
        On Error Resume Next
        sDate = Trim(ws.Cells(r, COL_PEER).Comment.Text)
        On Error GoTo 0

        entry = "  {" & vbCrLf & _
                "    ""user"": "     & JsonStr(peer) & "," & vbCrLf & _
                "    ""artifact"": " & JsonStr(sect) & "," & vbCrLf & _
                "    ""context"": "  & JsonStr(typ)  & "," & vbCrLf & _
                "    ""text"": "     & JsonStr(rem)  & "," & vbCrLf & _
                "    ""date"": "     & JsonStr(sDate) & vbCrLf & _
                "  }"

        ReDim Preserve entries(count)
        entries(count) = entry
        count = count + 1

        r = r + 1
        NextRow:
    Loop

    If count = 0 Then
        MsgBox "No valid review rows found to export.", vbInformation
        Exit Sub
    End If

    ' 4. Build JSON and write file
    Dim json As String
    json = "[" & vbCrLf & Join(entries, "," & vbCrLf) & vbCrLf & "]" & vbCrLf

    Dim fNum As Integer: fNum = FreeFile()
    On Error GoTo WriteError
    Open fPath For Output As #fNum
    Print #fNum, json
    Close #fNum
    On Error GoTo 0

    MsgBox count & " review(s) exported to:" & vbCrLf & fPath, vbInformation
    Exit Sub

WriteError:
    MsgBox "Cannot write file:" & vbCrLf & fPath, vbExclamation
End Sub

' ============================================================
'  JSON string helper
'  Wraps a value in double quotes and escapes special chars.
' ============================================================
Private Function JsonStr(v As String) As String
    v = Replace(v, "\",  "\\")
    v = Replace(v, """", "\""")
    v = Replace(v, Chr(10), "\n")
    v = Replace(v, Chr(13), "")
    v = Replace(v, Chr(9),  "\t")
    JsonStr = """" & v & """"
End Function
