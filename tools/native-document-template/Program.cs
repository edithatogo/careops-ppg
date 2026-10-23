// One-time PPG template authoring only. No local population or tenant operations.
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Validation;
using DocumentFormat.OpenXml.Wordprocessing;
using W15 = DocumentFormat.OpenXml.Office2013.Word;

if (args.Length == 2 && args[0] == "validate-docx")
{
    using var candidate = WordprocessingDocument.Open(args[1], false);
    var errors = new OpenXmlValidator(FileFormatVersions.Office2013).Validate(candidate).ToList();
    Console.WriteLine(JsonSerializer.Serialize(new { schemaErrors = errors.Count, descriptions = errors.Take(10).Select(e => e.Description) }));
    if (errors.Count != 0) Environment.ExitCode = 1;
    return;
}
if (args.Length > 0 && args[0] == "sharepoint-cover")
{
    SharePointCover.Run(args.Skip(1).ToArray());
    return;
}
if (args.Length > 0 && args[0] == "populate-manual")
{
    ManualPopulation.Run(args.Skip(1).ToArray());
    return;
}
if (args.Length != 3) throw new ArgumentException("TEMPLATE.md EXPECTED_SHA256 NEW_OUTPUT.docx");
var source = Path.GetFullPath(args[0]);
var output = Path.GetFullPath(args[2]);
var raw = File.ReadAllBytes(source);
var sourceHash = Convert.ToHexStringLower(SHA256.HashData(raw));
if (sourceHash != args[1]) throw new InvalidOperationException("Maintained template hash changed.");
if (File.Exists(output) || output == source) throw new InvalidOperationException("Preserve existing output.");
var text = System.Text.Encoding.UTF8.GetString(raw);
var markers = Regex.Matches(text, @"\{\{([A-Za-z_][A-Za-z_0-9]*)\}\}");
var fields = markers.Select(m => m.Groups[1].Value).ToHashSet();
if (!fields.Contains("comparison_rows") || !fields.Contains("consultation_rows") || !fields.Contains("CaseUID"))
    throw new InvalidOperationException("Required maintained template structure missing.");
int id = 200;
SdtProperties Props(string name, OpenXmlElement type) => new(
    new SdtAlias { Val = name }, new Tag { Val = name }, new SdtId { Val = id++ }, type);
Paragraph P(string value) => new(new Run(new Text(value) { Space = SpaceProcessingModeValues.Preserve }));
Paragraph Label(string value) => new(new ParagraphProperties(new KeepNext(),
    new SpacingBetweenLines { Before = "100", After = "20" }),
    new Run(new RunProperties(new Bold(), new Color { Val = "334155" }), new Text(value)));
SdtBlock Plain(string name) => new(Props(name, new SdtContentText { MultiLine = true }),
    new SdtContentBlock(P("[" + name + "]")));
SdtBlock Repeat(string name, string[] children)
{
    var contents = new SdtContentBlock();
    var labels = name == "comparison_rows"
        ? new[] { "Local source / version / clause", "Governing source / clause", "Necessary control", "Proposed change", "Gap / response" }
        : new[] { "Role / requirement basis", "Question", "Candidate version", "Actual response / disposition" };
    for (var n = 0; n < children.Length; n++) contents.Append(Label(labels[n]), Plain(children[n]));
    var item = new SdtBlock(new SdtProperties(new SdtId { Val = id++ }, new W15.SdtRepeatedSectionItem()), contents);
    return new SdtBlock(Props(name, new W15.SdtRepeatedSection()), new SdtContentBlock(item));
}
Directory.CreateDirectory(Path.GetDirectoryName(output)!);
// Exclusive create avoids replacing a candidate, edited output or issued history.
using (var stream = new FileStream(output, FileMode.CreateNew, FileAccess.ReadWrite))
using (var doc = WordprocessingDocument.Create(stream, WordprocessingDocumentType.Document))
{
    var main = doc.AddMainDocumentPart();
    var styles = main.AddNewPart<StyleDefinitionsPart>();
    styles.Styles = new Styles(new Style(new StyleName { Val = "Normal" },
        new StyleParagraphProperties(new SpacingBetweenLines { After = "100", Line = "260", LineRule = LineSpacingRuleValues.Auto }),
        new StyleRunProperties(new RunFonts { Ascii = "Arial", HighAnsi = "Arial" }, new FontSize { Val = "22" }))
        { Type = StyleValues.Paragraph, StyleId = "Normal", Default = true });
    foreach (var (styleId, title, size, level) in new[] { ("Title", "Title", "32", 0), ("Heading1", "heading 1", "26", 0) })
        styles.Styles.Append(new Style(new StyleName { Val = title }, new BasedOn { Val = "Normal" },
            new NextParagraphStyle { Val = "Normal" }, new PrimaryStyle(),
            new StyleParagraphProperties(new KeepNext(), new KeepLines(),
                new SpacingBetweenLines { Before = "220", After = "100" }, new OutlineLevel { Val = level }),
            new StyleRunProperties(new Bold(), new Color { Val = "17365D" }, new FontSize { Val = size }))
            { Type = StyleValues.Paragraph, StyleId = styleId });
    var body = new Body(P("FICTIONAL / UNISSUED — PPG DEVELOPMENT QUALIFICATION ONLY"));
    foreach (var sourceLine in text.Split('\n'))
    {
        // Markdown tables become labelled repeating groups; no pipe scaffolding
        // or connector property names should appear in the rendered document.
        if (sourceLine.TrimStart().StartsWith('|') || string.IsNullOrWhiteSpace(sourceLine)) continue;
        var heading = sourceLine.StartsWith("## ") ? "Heading1" : sourceLine.StartsWith("# ") ? "Title" : null;
        var line = heading == "Heading1" ? sourceLine[3..] : heading == "Title" ? sourceLine[2..] : sourceLine;
        var found = Regex.Matches(line, @"\{\{([A-Za-z_][A-Za-z_0-9]*)\}\}");
        if (line.Trim() == "{{comparison_rows}}")
            body.Append(Repeat("comparison_rows", ["ComparisonSource", "ComparisonGoverningSource", "ComparisonControl", "ComparisonChange", "ComparisonGap"]));
        else if (line.Trim() == "{{consultation_rows}}")
            body.Append(Repeat("consultation_rows", ["ConsultationRole", "ConsultationQuestion", "ConsultationVersion", "ConsultationResponse"]));
        else if (found.Count == 1 && line.Trim() == found[0].Value)
            body.Append(Plain(found[0].Groups[1].Value));
        else
        {
            var paragraph = new Paragraph();
            if (heading != null) paragraph.Append(new ParagraphProperties(new ParagraphStyleId { Val = heading }));
            var cursor = 0;
            foreach (Match m in found)
            {
                paragraph.Append(new Run(new Text(line[cursor..m.Index]) { Space = SpaceProcessingModeValues.Preserve }));
                paragraph.Append(new SdtRun(Props(m.Groups[1].Value, new SdtContentText()),
                    new SdtContentRun(new Run(new Text("[" + m.Groups[1].Value + "]")))));
                cursor = m.Index + m.Length;
            }
            paragraph.Append(new Run(new Text(line[cursor..]) { Space = SpaceProcessingModeValues.Preserve }));
            body.Append(paragraph);
        }
    }
    body.Append(new Paragraph(new ParagraphProperties(new ParagraphStyleId { Val = "Heading1" }),
        new Run(new Text("Generation provenance"))));
    var technicalNames = new[] { "documentKind", "sourceSHA256", "templateVersion", "outputRevision", "includedRecordIDs" };
    var technicalLabels = new[] { "Document kind", "Source SHA-256", "Template version", "Output revision", "Included record identities" };
    for (var n = 0; n < technicalNames.Length; n++) body.Append(Label(technicalLabels[n]), Plain(technicalNames[n]));
    // Empty optional content leaves no unconditional section title behind.
    body.Append(Plain("OptionalContent"));
    body.Append(new SectionProperties(new PageSize { Width = 11906, Height = 16838 },
        new PageMargin { Top = 1080, Bottom = 1080, Left = 1080, Right = 1080, Header = 425, Footer = 425, Gutter = 0 }));
    main.Document = new Document(body) { MCAttributes = new MarkupCompatibilityAttributes { Ignorable = "w15" } };
    main.Document.AddNamespaceDeclaration("w15", "http://schemas.microsoft.com/office/word/2012/wordml");
    main.Document.Save();
}
using (var doc = WordprocessingDocument.Open(output, false))
{
    var errors = new OpenXmlValidator(FileFormatVersions.Office2013).Validate(doc).ToList();
    if (errors.Count != 0) throw new InvalidOperationException(string.Join("\n", errors.Select(e => e.Description)));
    var props = doc.MainDocumentPart!.Document!.Descendants<SdtProperties>().ToList();
    var names = props.Select(p => p.GetFirstChild<SdtAlias>()?.Val?.Value).Where(n => n != null).ToList();
    if (names.Distinct().Count() != names.Count || props.Select(p => p.GetFirstChild<SdtId>()!.Val!.Value).Distinct().Count() != props.Count)
        throw new InvalidOperationException("Duplicate control names/IDs.");
    if (!fields.IsSubsetOf(names!)) throw new InvalidOperationException("Maintained placeholder omitted.");
    if (File.ReadAllBytes(source).SequenceEqual(raw) is false) throw new InvalidOperationException("Template changed during authoring.");
    Console.WriteLine(JsonSerializer.Serialize(new { schemaErrors = errors.Count, sourceSHA256 = sourceHash,
        templateSHA256 = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(output))),
        namedControls = names, locallyPopulated = false, nativeGenerationQualified = false }));
}
