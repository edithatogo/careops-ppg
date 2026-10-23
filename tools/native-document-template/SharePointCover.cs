// One-time template authoring. Operational values are populated by SharePoint.
using System.Text.Json;
using System.Xml.Linq;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Validation;
using DocumentFormat.OpenXml.Wordprocessing;

internal static class SharePointCover
{
    static Paragraph P(string text) => new(new Run(new Text(text)));
    public static void Run(string[] args)
    {
        if (args.Length == 2 && args[0] == "seed")
        {
            using var stream = new FileStream(args[1], FileMode.CreateNew, FileAccess.ReadWrite);
            using var doc = WordprocessingDocument.Create(stream, WordprocessingDocumentType.Document);
            doc.AddMainDocumentPart().Document = new Document(new Body(P("DRAFT — FICTIONAL PPG COVER TEMPLATE")));
            return;
        }
        if (args.Length != 4 || args[0] != "bind")
            throw new ArgumentException("sharepoint-cover seed NEW.docx | bind NATIVE-SEED.docx MAPPING.json NEW-TEMPLATE.docx");
        var fields = JsonSerializer.Deserialize<Dictionary<string, string>>(File.ReadAllText(args[2]))!;
        var bytes = File.ReadAllBytes(args[1]);
        // The native seed supplies the library's actual property namespace/store ID.
        // No speculative namespace, runtime content merge or desktop automation.
        using var memory = new MemoryStream(); memory.Write(bytes); memory.Position = 0;
        using (var doc = WordprocessingDocument.Open(memory, true))
        {
            var main = doc.MainDocumentPart ?? throw new InvalidDataException("Main document part missing");
            var bindings = new Dictionary<string, (string Store, string Namespace)>();
            foreach (var part in main.CustomXmlParts)
            {
                XDocument xml;
                using (var partStream = part.GetStream()) xml = XDocument.Load(partStream);
                foreach (var element in xml.Descendants().Where(x => fields.ContainsKey(x.Name.LocalName)))
                {
                    if (element.Parent?.Name.LocalName != "documentManagement") continue;
                    var store = part.CustomXmlPropertiesPart?.DataStoreItem?.ItemId?.Value;
                    if (store == null || !bindings.TryAdd(element.Name.LocalName, (store, element.Name.NamespaceName)))
                        throw new InvalidDataException("Missing or ambiguous native property binding");
                    if (!string.IsNullOrEmpty(element.Value))
                        throw new InvalidDataException("Seed contains values; use a fresh blank seed");
                }
            }
            var body = new Body(P("DRAFT — FICTIONAL PPG REVIEW PACK"),
                P("Prepared metadata only. Review and approval remain unresolved."));
            int id = 1000;
            foreach (var (name, label) in fields)
            {
                if (!bindings.TryGetValue(name, out var binding))
                    throw new InvalidDataException("Native library property not found: " + name);
                var prefix = "xmlns:p='http://schemas.microsoft.com/office/2006/metadata/properties' xmlns:f='" + binding.Namespace + "'";
                var xpath = "/p:properties[1]/documentManagement[1]/f:" + name + "[1]";
                body.Append(P(label), new SdtBlock(new SdtProperties(new SdtAlias { Val = name },
                    new Tag { Val = name }, new SdtId { Val = id++ },
                    new DataBinding { StoreItemId = binding.Store, PrefixMappings = prefix, XPath = xpath },
                    new SdtContentText { MultiLine = true }), new SdtContentBlock(P("[Unresolved]"))));
            }
            body.Append(P("Evidence files accompany this cover. Preserve this revision when editing."),
                new SectionProperties(new PageSize { Width = 11906, Height = 16838 },
                    new PageMargin { Top = 1080, Bottom = 1080, Left = 1080, Right = 1080, Header = 425, Footer = 425, Gutter = 0 }));
            (main.Document ?? throw new InvalidDataException("Document missing")).Body = body;
            var errors = new OpenXmlValidator(FileFormatVersions.Office2013).Validate(doc).ToList();
            if (errors.Count != 0) throw new InvalidDataException(string.Join("; ", errors.Select(x => x.Description)));
            main.Document.Save();
        }
        using var output = new FileStream(args[3], FileMode.CreateNew, FileAccess.Write);
        memory.Position = 0; memory.CopyTo(output);
        Console.WriteLine(JsonSerializer.Serialize(new { mappedFields = fields.Count, schemaErrors = 0, nativePopulationVerified = false }));
    }
}
