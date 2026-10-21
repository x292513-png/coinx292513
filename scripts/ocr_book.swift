import Foundation
import PDFKit
import Vision
import AppKit

// Local OCR only. No network, no credentials, no execution of document contents.
let args = CommandLine.arguments
guard args.count >= 3, let pdf = PDFDocument(url: URL(fileURLWithPath: args[1])) else { fatalError("input PDF and output JSONL required") }
let output = URL(fileURLWithPath: args[2])
if !FileManager.default.fileExists(atPath: output.path) { FileManager.default.createFile(atPath: output.path, contents: nil) }
let handle = try FileHandle(forWritingTo: output)
try handle.seekToEnd()
let existing = (try? String(contentsOf: output, encoding: .utf8)) ?? ""
let completed = Set(existing.split(separator: "\n").compactMap { line -> Int? in
    guard let data = line.data(using: .utf8), let item = try? JSONSerialization.jsonObject(with: data) as? [String:Any] else { return nil }
    return item["page"] as? Int
})
for i in 0..<pdf.pageCount where !completed.contains(i+1) {
    try autoreleasepool {
        guard let page = pdf.page(at:i) else { return }
        let bounds = page.bounds(for: .mediaBox)
        let scale = 2200.0 / max(bounds.width,bounds.height)
        let img = page.thumbnail(of: NSSize(width: bounds.width*scale, height: bounds.height*scale), for: .mediaBox)
        guard let cg = img.cgImage(forProposedRect:nil,context:nil,hints:nil) else { return }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.recognitionLanguages = ["ko-KR","en-US"]
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage:cg,options:[:]).perform([req])
        let rows = (req.results ?? []).compactMap { $0.topCandidates(1).first }
        let text = rows.map { $0.string }.joined(separator:"\n")
        let data = try JSONSerialization.data(withJSONObject:["page":i+1,"text":text,"method":"apple_vision_ocr","mean_confidence":rows.isEmpty ? 0 : rows.map{Double($0.confidence)}.reduce(0,+)/Double(rows.count)],options:[.sortedKeys])
        try handle.write(contentsOf:data);try handle.write(contentsOf:Data([10]))
        if (i+1)%10 == 0 { print("OCR \(i+1)/\(pdf.pageCount)");fflush(stdout) }
    }
}
try handle.close()
