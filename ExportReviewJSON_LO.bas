' ============================================================
'  ExportReviewJSON_LO.bas  —  LibreOffice Basic (UNO API)
'  Exports review rows from the "Remarks" sheet to a JSON file
'  compatible with mhtml-cleaner -R.
'
'  Installation:
'    Tools -> Macros -> Edit Macros...
'    Paste under "My Macros" or the document macro library.
'
'  Usage: Tools -> Macros -> Run Macro -> ExportReviewJSON
'
'  LO Basic constraints:
'    - All Dim at top of function
'    - No For-loop counter modification (use Do While)
'    - No Chr() in Case expressions (use local DQ variable)
'    - No String() return type (use Variant or String)
' ============================================================

Option Explicit

Private Const DATA_START  As Long = 15  ' First data row (row 14 is blank)

' Column indices — 0-based for UNO getCellByPosition(col, row)
Private Const COL_PEER    As Long = 0   ' A  Peer
Private Const COL_NO      As Long = 1   ' B  No.
Private Const COL_SECTION As Long = 3   ' D  Section
Private Const COL_REMARKS As Long = 4   ' E  Remarks
Private Const COL_TYPE    As Long = 5   ' F  Type

' Valid review types — any other value in Type column is skipped
Private Const VALID_TYPES As String = "|Operational|Significant|Major|Minor|Typo|Comment|"

' ============================================================
'  Entry point
' ============================================================
Public Sub ExportReviewJSON()
    Dim oDoc         As Object
    Dim oSheet       As Object
    Dim oAnnotations As Object
    Dim ann          As Object
    Dim annAddr      As Object
    Dim oDialog      As Object
    Dim files        As Variant
    Dim url          As String
    Dim fPath        As String
    Dim fNum         As Integer
    Dim lastRow      As Long
    Dim r            As Long
    Dim peer         As String
    Dim sect         As String
    Dim cRem          As String
    Dim typ          As String
    Dim sDate        As String
    Dim entry        As String
    Dim entries()    As String
    Dim count        As Long
    Dim j            As Long
    Dim json         As String
    Dim oCursor      As Object

    ' 1. Locate sheet
    oDoc = ThisComponent
    If Not oDoc.Sheets.hasByName("Remarks") Then
        MsgBox "Sheet 'Remarks' not found in this document."
        Exit Sub
    End If
    oSheet = oDoc.Sheets.getByName("Remarks")

    ' 2. Choose output file via save dialog
    '    Mode 1 = FILESAVE_SIMPLE (write dialog, not open dialog)
    oDialog = CreateUnoService("com.sun.star.ui.dialogs.FilePicker")
    oDialog.initialize(Array(1))
    oDialog.appendFilter("JSON files (*.json)", "*.json")
    oDialog.appendFilter("All files (*.*)", "*.*")
    oDialog.setCurrentFilter("JSON files (*.json)")
    oDialog.setDefaultName("reviews.json")

    If oDialog.execute() <> 1 Then Exit Sub
    files  = oDialog.getSelectedFiles()
    url    = files(0)
    ' Ensure .json extension
    If Right(LCase(url), 5) <> ".json" Then url = url & ".json"
    fPath  = ConvertFromURL(url)

    ' 3. Collect rows
    '    Use sheet cursor to find the actual last used row (0-based)
    count  = 0
    ReDim entries(0)
    oCursor = oSheet.createCursor()
    oCursor.gotoEndOfUsedArea(True)
    lastRow = oCursor.getRangeAddress().EndRow
    r = DATA_START - 1   ' 0-based

    Do While r <= lastRow
        peer = Trim(oSheet.getCellByPosition(COL_PEER,    r).getString())
        sect = Trim(oSheet.getCellByPosition(COL_SECTION, r).getString())
        cRem  = Trim(oSheet.getCellByPosition(COL_REMARKS, r).getString())
        typ  = Trim(oSheet.getCellByPosition(COL_TYPE,    r).getString())

        ' Skip empty rows
        If peer = "" And sect = "" And cRem = "" Then
            r = r + 1
            GoTo NextRow
        End If

        ' Skip rows with unknown Type
        If InStr(VALID_TYPES, "|" & typ & "|") = 0 Then
            r = r + 1
            GoTo NextRow
        End If

        ' Retrieve date from cell annotation if present
        sDate = ""
        oAnnotations = oSheet.getAnnotations()
        For j = 0 To oAnnotations.getCount() - 1
            ann     = oAnnotations.getByIndex(j)
            annAddr = ann.getPosition()
            If annAddr.Column = COL_PEER And annAddr.Row = r Then
                sDate = Trim(ann.getString())
                Exit For
            End If
        Next j

        entry = "  {" & Chr(10) & _
                "    " & JsonStr("user")     & ": " & JsonStr(peer) & "," & Chr(10) & _
                "    " & JsonStr("artifact") & ": " & JsonStr(sect) & "," & Chr(10) & _
                "    " & JsonStr("context")  & ": " & JsonStr(typ)  & "," & Chr(10) & _
                "    " & JsonStr("text")     & ": " & JsonStr(cRem)  & "," & Chr(10) & _
                "    " & JsonStr("date")     & ": " & JsonStr(sDate) & Chr(10) & _
                "  }"

        ReDim Preserve entries(count)
        entries(count) = entry
        count = count + 1

        r = r + 1
        NextRow:
    Loop

    If count = 0 Then
        MsgBox "No valid review rows found to export."
        Exit Sub
    End If

    ' 4. Build JSON string
    Dim i    As Long
    Dim body As String
    body = ""
    For i = 0 To count - 1
        If i > 0 Then body = body & "," & Chr(10)
        body = body & entries(i)
    Next i
    json = "[" & Chr(10) & body & Chr(10) & "]" & Chr(10)

    ' 5. Write file
    fNum = FreeFile()
    On Error GoTo WriteError
    Open fPath For Output As #fNum
    Print #fNum, json
    Close #fNum
    On Error GoTo 0

    MsgBox count & " review(s) exported to:" & Chr(10) & fPath
    Exit Sub

WriteError:
    Close #fNum
    MsgBox "Cannot write file:" & Chr(10) & fPath
End Sub

' ============================================================
'  JsonStr — wraps a string in double quotes, escapes specials
' ============================================================
Private Function JsonStr(v As String) As String
    Dim DQ As String
    DQ = Chr(34)
    v = Replace(v, "\",    "\\")
    v = Replace(v, DQ,     "\" & DQ)
    v = Replace(v, Chr(10), "\n")
    v = Replace(v, Chr(13), "")
    v = Replace(v, Chr(9),  "\t")
    JsonStr = DQ & v & DQ
End Function
