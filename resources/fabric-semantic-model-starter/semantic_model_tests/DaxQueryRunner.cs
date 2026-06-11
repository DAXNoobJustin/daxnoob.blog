// Standalone DAX query runner using AdomdClient.
// Compiled at runtime by the Python test harness via csc.exe.
// Runs out-of-proc (no TE2 dependency) to avoid assembly-loading conflicts.
//
// Environment variables:
//   UDF_TEST_CONNSTR - XMLA connection string (Provider=MSOLAP;...)
//   UDF_TEST_INPUT   - sentinel-delimited input file
//   UDF_TEST_OUTPUT  - JSONL output file

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Microsoft.AnalysisServices.AdomdClient;

class DaxQueryRunner
{
    static int Main()
    {
        var connStr    = Environment.GetEnvironmentVariable("UDF_TEST_CONNSTR");
        var inputPath  = Environment.GetEnvironmentVariable("UDF_TEST_INPUT");
        var outputPath = Environment.GetEnvironmentVariable("UDF_TEST_OUTPUT");

        if (string.IsNullOrWhiteSpace(connStr)
            || string.IsNullOrWhiteSpace(inputPath)
            || string.IsNullOrWhiteSpace(outputPath))
        {
            Console.Error.WriteLine("Missing env vars: UDF_TEST_CONNSTR, UDF_TEST_INPUT, UDF_TEST_OUTPUT");
            return 1;
        }

        // Parse sentinel-delimited input: ===CASE <id>===\n<dax>\n...
        var raw = File.ReadAllText(inputPath, Encoding.UTF8);
        var marker = "===CASE ";
        var segments = raw.Split(new[] { marker }, StringSplitOptions.RemoveEmptyEntries);
        var cases = new List<KeyValuePair<string, string>>();

        foreach (var seg in segments)
        {
            var endMark = seg.IndexOf("===");
            if (endMark < 0) continue;
            var id = seg.Substring(0, endMark).Trim();
            var daxStart = endMark + 3;
            while (daxStart < seg.Length && (seg[daxStart] == '\r' || seg[daxStart] == '\n'))
                daxStart++;
            var dax = (daxStart < seg.Length) ? seg.Substring(daxStart).TrimEnd() : "";
            if (!string.IsNullOrEmpty(id) && !string.IsNullOrEmpty(dax))
                cases.Add(new KeyValuePair<string, string>(id, dax));
        }

        Console.WriteLine("AdomdClient batch: " + cases.Count + " queries");

        var resultLines = new List<string>();

        try
        {
            using (var conn = new AdomdConnection(connStr))
            {
                conn.Open();
                Console.WriteLine("Connected to model");

                foreach (var kv in cases)
                {
                    var id  = kv.Key;
                    var dax = kv.Value;

                    try
                    {
                        using (var cmd = conn.CreateCommand())
                        {
                            cmd.CommandText = dax;
                            using (var reader = cmd.ExecuteReader())
                            {
                                // Read column names from reader schema
                                var cols = new List<string>();
                                for (int i = 0; i < reader.FieldCount; i++)
                                    cols.Add(reader.GetName(i));

                                // Read rows directly (avoids DataTable constraint issues)
                                var rows = new List<string>();
                                while (reader.Read())
                                {
                                    var rb = new StringBuilder("{");
                                    for (int i = 0; i < reader.FieldCount; i++)
                                    {
                                        if (i > 0) rb.Append(",");
                                        rb.Append("\"").Append(EscapeJson(cols[i])).Append("\":");
                                        rb.Append(JsonVal(reader.IsDBNull(i) ? null : reader.GetValue(i)));
                                    }
                                    rb.Append("}");
                                    rows.Add(rb.ToString());
                                }

                                // Columns JSON
                                var colsJ = new StringBuilder();
                                for (int i = 0; i < cols.Count; i++)
                                {
                                    if (i > 0) colsJ.Append(",");
                                    colsJ.Append("\"").Append(EscapeJson(cols[i])).Append("\"");
                                }

                                resultLines.Add(
                                    "{\"id\":\"" + EscapeJson(id)
                                    + "\",\"ok\":true,\"columns\":["
                                    + colsJ.ToString()
                                    + "],\"rows\":["
                                    + string.Join(",", rows.ToArray())
                                    + "],\"error\":null}");
                            }
                        }
                    }
                    catch (Exception ex)
                    {
                        resultLines.Add(
                            "{\"id\":\"" + EscapeJson(id)
                            + "\",\"ok\":false,\"columns\":[],\"rows\":[],"
                            + "\"error\":{\"message\":\"" + EscapeJson(ex.Message) + "\"}}");
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("Connection failed: " + ex.Message);
            foreach (var kv in cases)
            {
                resultLines.Add(
                    "{\"id\":\"" + EscapeJson(kv.Key)
                    + "\",\"ok\":false,\"columns\":[],\"rows\":[],"
                    + "\"error\":{\"message\":\""
                    + EscapeJson("Connection failed: " + ex.Message) + "\"}}");
            }
        }

        File.WriteAllText(outputPath, string.Join("\n", resultLines.ToArray()), new UTF8Encoding(false));
        Console.WriteLine("Results written (" + resultLines.Count + " cases)");
        return 0;
    }

    static string EscapeJson(string s)
    {
        if (s == null) return "";
        var sb = new StringBuilder(s.Length + 16);
        foreach (var ch in s)
        {
            switch (ch)
            {
                case '\\': sb.Append("\\\\"); break;
                case '"':  sb.Append("\\\""); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                default:   sb.Append(ch); break;
            }
        }
        return sb.ToString();
    }

    static string JsonVal(object val)
    {
        if (val == null || val is DBNull) return "null";
        if (val is bool) return ((bool)val) ? "true" : "false";
        if (val is int || val is long || val is short || val is byte)
            return val.ToString();
        if (val is double)
            return ((double)val).ToString(System.Globalization.CultureInfo.InvariantCulture);
        if (val is float)
            return ((float)val).ToString(System.Globalization.CultureInfo.InvariantCulture);
        if (val is decimal)
            return ((decimal)val).ToString(System.Globalization.CultureInfo.InvariantCulture);
        return "\"" + EscapeJson(val.ToString()) + "\"";
    }
}
