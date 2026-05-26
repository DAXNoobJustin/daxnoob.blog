let
    Source = Json.Document(Web.Contents(SourceUrl)),
    AsTable = Table.FromList(Source, Splitter.SplitByNothing(), null, null, ExtraValues.Error),
    Expanded = Table.ExpandRecordColumn(AsTable, "Column1", {"number", "title", "state", "created_at"}, {"Number", "Title", "State", "CreatedAt"}),
    Typed = Table.TransformColumnTypes(Expanded, {{"CreatedAt", type datetime}}),
    WithAge = Table.AddColumn(Typed, "Age", each fnAgeBucket([CreatedAt]), type text)
in
    WithAge
