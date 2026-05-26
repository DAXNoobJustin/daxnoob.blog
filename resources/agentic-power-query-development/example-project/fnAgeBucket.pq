(d as datetime) as text =>
    let
        days = Duration.Days(DateTime.LocalNow() - d)
    in
        if days = 0 then "today"
        else if days = 1 then "yesterday"
        else Text.From(days) & " days ago"
