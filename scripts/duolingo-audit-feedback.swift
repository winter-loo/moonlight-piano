#!/usr/bin/env swift
// Read the game's visible judgment banner from an archived live run.
// This is an audit of screen feedback, not an assertion that an input ACK hit.

import Foundation
import ImageIO
import Vision

guard CommandLine.arguments.count == 2 else {
    fputs("usage: swift scripts/duolingo-audit-feedback.swift <run-directory>\n", stderr)
    exit(2)
}

let run = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let framesURL = run.appendingPathComponent("frames.json")
let framesData = try Data(contentsOf: framesURL)
guard let frames = try JSONSerialization.jsonObject(with: framesData) as? [[String: Any]] else {
    fatalError("frames.json must contain a list of frames")
}

let grades = ["完美", "优秀", "厉害", "好棒", "迟了", "早了", "失误", "哎呀"]
let comboPattern = try NSRegularExpression(pattern: #"(\d+)\s*连击"#)
var observations: [[String: Any]] = []

for (position, frame) in frames.enumerated() {
    guard let path = frame["image"] as? String,
          let index = frame["index"] as? Int,
          let tMS = frame["t_ms"] as? Double else { continue }
    let imageURL = run.appendingPathComponent(path)
    guard let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { continue }

    let request = VNRecognizeTextRequest()
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.recognitionLevel = .accurate
    // Vision's normalized origin is bottom-left. The banner is above the staff.
    request.regionOfInterest = CGRect(x: 0.24, y: 0.82, width: 0.29, height: 0.18)
    try VNImageRequestHandler(cgImage: image).perform([request])
    let text = (request.results ?? [])
        .compactMap { $0.topCandidates(1).first?.string }
        .joined(separator: " ")
    guard let grade = grades.first(where: { text.contains($0) }) else { continue }
    var observation: [String: Any] = [
        "frame_index": index, "t_ms": tMS, "grade": grade, "text": text,
    ]
    let range = NSRange(text.startIndex..<text.endIndex, in: text)
    if let match = comboPattern.firstMatch(in: text, range: range),
       let digits = Range(match.range(at: 1), in: text),
       let combo = Int(text[digits]) {
        observation["combo"] = combo
    }
    observations.append(observation)
    if (position + 1) % 50 == 0 {
        fputs("audited \(position + 1)/\(frames.count) frames\n", stderr)
    }
}

let output = run.appendingPathComponent("feedback.json")
let data = try JSONSerialization.data(withJSONObject: observations, options: [.prettyPrinted, .sortedKeys])
try data.write(to: output)
print("\(observations.count) visible feedback frames -> \(output.path)")
