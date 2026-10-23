using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Validation;
using DocumentFormat.OpenXml.Wordprocessing;
using W15 = DocumentFormat.OpenXml.Office2013.Word;

// Explicit local/manual preparation only; never a connector or publication substitute.
internal static class ManualPopulation
{
    static void Require(bool ok, string reason) { if (!ok) throw new InvalidOperationException(reason); }
    static string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
    static string Name(SdtElement s) => s.GetFirstChild<SdtProperties>()?.GetFirstChild<SdtAlias>()?.Val?.Value ?? "";
    static Dictionary<string, byte[]> Parts(byte[] bytes)
    {
        using var zip = new ZipArchive(new MemoryStream(bytes), ZipArchiveMode.Read);
        Require(zip.Entries.Select(x => x.FullName).Distinct().Count() == zip.Entries.Count, "Duplicate ZIP member");
        return zip.Entries.ToDictionary(x => x.FullName, x => { using var s = x.Open(); using var b = new MemoryStream(); s.CopyTo(b); return b.ToArray(); });
    }
    static void SetText(SdtElement s, string value)
    {
        var props = s.GetFirstChild<SdtProperties>()!;
        props.RemoveAllChildren<ShowingPlaceholder>();
        props.RemoveAllChildren<SdtPlaceholder>();
        var lines = value.Replace("\r\n", "\n").Split('\n');
        Run MakeRun()
        {
            var run = new Run();
            for (int n = 0; n < lines.Length; n++)
            {
                if (n > 0) run.Append(new Break());
                run.Append(new Text(lines[n]) { Space = SpaceProcessingModeValues.Preserve });
            }
            return run;
        }
        if (s is SdtBlock)
        {
            var content = s.GetFirstChild<SdtContentBlock>()!;
            var pp = content.Descendants<ParagraphProperties>().FirstOrDefault()?.CloneNode(true);
            content.RemoveAllChildren();
            var p = new Paragraph(); if (pp != null) p.Append(pp); p.Append(MakeRun()); content.Append(p);
        }
        else if (s is SdtRun)
        {
            var content = s.GetFirstChild<SdtContentRun>()!; content.RemoveAllChildren(); content.Append(MakeRun());
        }
        else throw new InvalidOperationException("Unsupported control shape: " + Name(s));
    }
    internal static void Run(string[] args)
    {
        Require(args.Length == 7, "BINDING.json EXPECTED_BINDING_SHA INPUT.json TEMPLATE.docx SOURCE NEW_OUTPUT.docx NEW_RECEIPT.json");
        var bindingBytes = File.ReadAllBytes(args[0]); Require(Hash(bindingBytes) == args[1], "Binding changed");
        using var bindingDoc = JsonDocument.Parse(bindingBytes); var b = bindingDoc.RootElement;
        var inputBytes = File.ReadAllBytes(args[2]); Require(Hash(inputBytes) == b.GetProperty("inputSHA256").GetString(), "Input changed");
        using var inputDoc = JsonDocument.Parse(inputBytes); var input = inputDoc.RootElement;
        var templateBytes = File.ReadAllBytes(args[3]); var sourceBytes = File.ReadAllBytes(args[4]);
        Require(Hash(templateBytes) == b.GetProperty("templateSHA256").GetString(), "Template changed");
        Require(templateBytes.Length == int.Parse(b.GetProperty("template").GetProperty("Length").GetString()!), "Template length changed");
        Require(Hash(sourceBytes) == b.GetProperty("sourceScope").GetProperty("DocumentSHA256").GetString(), "Source changed");
        foreach (var field in new[] { "CaseUID", "occurrenceID", "documentKind", "templateSHA256" })
            Require(input.GetProperty(field).GetString() == b.GetProperty(field).GetString(), "Binding mismatch: " + field);
        Require(input.GetProperty("sourceSHA256").GetString() == Hash(sourceBytes), "Input source mismatch");
        Require(input.GetProperty("outputRevision").GetString() == b.GetProperty("jobId").GetString() + "/revision" + b.GetProperty("outputRevision").ToString(), "Job/revision mismatch");
        Require(input.GetProperty("source_snapshot").GetString()!.EndsWith("/LC02-operator-request-" + b.GetProperty("requestId").GetString() + ".json", StringComparison.Ordinal), "Request mismatch");
        Require(input.GetProperty("source_manifest").GetString()!.Contains(b.GetProperty("jobId").GetString()!, StringComparison.Ordinal), "Missing job provenance");
        var output = Path.GetFullPath(args[5]); var receipt = Path.GetFullPath(args[6]);
        Require(output != receipt, "Output and receipt paths must differ");
        Require(!File.Exists(output) && !File.Exists(receipt), "Existing output or receipt; preserve edits and history");
        Require(!new[] { 0, 2, 3, 4 }.Select(i => Path.GetFullPath(args[i])).Contains(output), "Output overlaps input");
        var expected = new[] { "case_title", "CaseUID", "source_snapshot", "version", "intended_result", "source_manifest", "comparison_rows", "draft_links_and_changes", "ownership_and_implementation", "decision_route", "consultation_rows", "candidate_reference", "reviewer_response", "operative_confirmation", "role_acceptance", "review_findings", "decision_evidence", "next_action", "measures", "documentKind", "sourceSHA256", "templateVersion", "outputRevision", "includedRecordIDs", "OptionalContent", "ComparisonSource", "ComparisonGoverningSource", "ComparisonControl", "ComparisonChange", "ComparisonGap", "ConsultationRole", "ConsultationQuestion", "ConsultationVersion", "ConsultationResponse" };
        var before = Parts(templateBytes); var stream = new MemoryStream(); stream.Write(templateBytes);
        var filled = new List<object>(); var omitted = new List<string>();
        using (var doc = WordprocessingDocument.Open(stream, true))
        {
            var main = doc.MainDocumentPart!.Document!;
            var controls = main.Descendants<SdtElement>().Where(s => Name(s) != "").ToList();
            Require(controls.Count == 34 && controls.Select(Name).ToHashSet().SetEquals(expected), "Maintained control inventory mismatch");
            var originalIds = main.Descendants<SdtId>().Select(x => x.Val!.Value).ToList();
            Require(originalIds.Count == originalIds.Distinct().Count(), "Duplicate source control ID");
            int nextId = originalIds.Max() + 1;
            foreach (var repeatName in new[] { "comparison_rows", "consultation_rows" })
            {
                var repeat = controls.Single(x => Name(x) == repeatName);
                var content = repeat.GetFirstChild<SdtContentBlock>()!;
                var prototype = content.Elements<SdtBlock>().Single();
                Require(prototype.GetFirstChild<SdtProperties>()!.GetFirstChild<W15.SdtRepeatedSectionItem>() != null, "Unsupported repeating prototype");
                var fields = prototype.Descendants<SdtElement>().Select(Name).Where(x => x != "").ToHashSet();
                var rows = input.GetProperty(repeatName); Require(rows.ValueKind == JsonValueKind.Array, "Repeat must be array");
                if (rows.GetArrayLength() == 0)
                {
                    omitted.AddRange(fields.Append(repeatName)); repeat.Remove(); continue;
                }
                content.RemoveAllChildren();
                foreach (var row in rows.EnumerateArray())
                {
                    Require(row.EnumerateObject().Select(x => x.Name).ToHashSet().SetEquals(fields), "Repeat fields mismatch");
                    var item = (SdtBlock)prototype.CloneNode(true);
                    foreach (var id in item.Descendants<SdtId>()) id.Val = nextId++;
                    foreach (var child in item.Descendants<SdtElement>().Where(x => Name(x) != ""))
                        SetText(child, row.GetProperty(Name(child)).GetString()!);
                    content.Append(item);
                }
                filled.Add(new { field = repeatName, rows = rows.GetArrayLength() });
            }
            foreach (var s in main.Descendants<SdtElement>().Where(x => Name(x) != "" && x.GetFirstChild<SdtProperties>()!.GetFirstChild<W15.SdtRepeatedSection>() == null).ToList())
            {
                var name = Name(s); if (name.StartsWith("Comparison") || name.StartsWith("Consultation")) continue;
                var value = input.GetProperty(name); var text = value.ValueKind == JsonValueKind.Array ? string.Join("; ", value.EnumerateArray().Select(x => x.GetString())) : value.GetString()!;
                SetText(s, text); filled.Add(new { field = name, value = text });
            }
            main.Save();
            var ids = main.Descendants<SdtId>().Select(x => x.Val!.Value).ToList();
            Require(ids.Count == ids.Distinct().Count(), "Duplicate populated control ID");
            var errors = new OpenXmlValidator(FileFormatVersions.Office2013).Validate(doc).ToList();
            Require(errors.Count == 0, string.Join("; ", errors.Select(e => e.Description)));
        }
        var result = stream.ToArray(); var after = Parts(result);
        Require(before.Keys.ToHashSet().SetEquals(after.Keys), "Package member set changed");
        var changed = before.Keys.Where(k => !before[k].SequenceEqual(after[k])).ToList();
        Require(changed.SequenceEqual(new[] { "word/document.xml" }), "Non-document package parts changed");
        Require(File.ReadAllBytes(args[3]).SequenceEqual(templateBytes) && File.ReadAllBytes(args[4]).SequenceEqual(sourceBytes), "Source/template changed during preparation");
        var proof = new { generationRoute = "local-manual-fallback", nativeGenerationQualified = false, nativeArtifactQualified = false,
            CaseUID = b.GetProperty("CaseUID").GetString(), occurrenceReference = b.GetProperty("occurrenceID").GetString(), documentKind = b.GetProperty("documentKind").GetString(),
            originalSourceScope = b.GetProperty("sourceScope"), jobId = b.GetProperty("jobId").GetString(), outputRevision = b.GetProperty("outputRevision"),
            bindingSHA256 = Hash(bindingBytes), inputSHA256 = Hash(inputBytes), templateSHA256 = Hash(templateBytes), outputSHA256 = Hash(result), outputBytes = result.Length,
            maintainedNamedControls = expected, populatedFields = filled, intentionallyOmittedControls = omitted, changedParts = changed,
            packagePartsPreserved = before.Keys.Count - changed.Count, schemaErrors = 0, qualificationEvidence = "Local only; native rendering/editing/version/retry/access still required" };
        // CreateNew is the final conflict guard even if another writer raced preflight.
        using (var file = new FileStream(output, FileMode.CreateNew, FileAccess.Write)) file.Write(result);
        try
        {
            using var file = new FileStream(receipt, FileMode.CreateNew, FileAccess.Write);
            JsonSerializer.Serialize(file, proof, new JsonSerializerOptions { WriteIndented = true });
        }
        catch (Exception error)
        {
            throw new IOException("Output preserved; receipt creation failed. Reconcile existing output SHA-256 " + Hash(result) + "; do not rerender or overwrite.", error);
        }
        Console.WriteLine(JsonSerializer.Serialize(new { generationRoute = "local-manual-fallback", nativeGenerationQualified = false, bytes = result.Length, outputSHA256 = Hash(result), schemaErrors = 0 }));
    }
}
