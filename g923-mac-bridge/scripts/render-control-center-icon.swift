#!/usr/bin/env swift
// Original vector artwork for G923 Control Center. No external images or fonts.
// Run: swift -module-cache-path /tmp/g923-icon-module-cache scripts/render-control-center-icon.swift [output-directory]
import AppKit
import Foundation

let output = URL(fileURLWithPath: CommandLine.arguments.dropFirst().first ?? "assets/control-center")
let files = FileManager.default
try files.createDirectory(at: output, withIntermediateDirectories: true)
let iconset = output.appendingPathComponent("AppIcon.iconset")
try files.createDirectory(at: iconset, withIntermediateDirectories: true)

func color(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: r / 255, green: g / 255, blue: b / 255, alpha: a)
}

func artwork() {
    let tile = NSBezierPath(roundedRect: NSRect(x: 70, y: 70, width: 884, height: 884), xRadius: 200, yRadius: 200)
    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow()
    shadow.shadowColor = color(0, 5, 18, 0.45)
    shadow.shadowBlurRadius = 22
    shadow.shadowOffset = NSSize(width: 0, height: -12)
    shadow.set()
    color(9, 18, 37).setFill()
    tile.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient(colors: [color(10, 22, 43), color(24, 47, 75)])!.draw(in: tile, angle: 80)

    NSGraphicsContext.saveGraphicsState()
    tile.addClip()
    NSGradient(colors: [color(0, 153, 255, 0.18), color(0, 153, 255, 0)])!.draw(
        fromCenter: NSPoint(x: 660, y: 820), radius: 0,
        toCenter: NSPoint(x: 660, y: 820), radius: 680,
        options: [.drawsBeforeStartingLocation, .drawsAfterEndingLocation])
    NSGraphicsContext.restoreGraphicsState()
    color(161, 210, 255, 0.12).setStroke()
    tile.lineWidth = 2
    tile.stroke()

    // Continuous wheel rim, three spokes, and an audio waveform in the hub.
    let center = NSPoint(x: 512, y: 520)
    let rim = NSBezierPath()
    rim.windingRule = .evenOdd
    rim.appendOval(in: NSRect(x: 224, y: 232, width: 576, height: 576))
    rim.appendOval(in: NSRect(x: 274, y: 282, width: 476, height: 476))
    NSGraphicsContext.saveGraphicsState()
    let rimShadow = NSShadow()
    rimShadow.shadowColor = color(0, 7, 20, 0.65)
    rimShadow.shadowBlurRadius = 18
    rimShadow.shadowOffset = NSSize(width: 0, height: -8)
    rimShadow.set()
    color(21, 127, 221).setFill()
    rim.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient(colors: [color(18, 111, 240), color(82, 231, 255)])!.draw(in: rim, angle: 60)
    let outerHighlight = NSBezierPath(ovalIn: NSRect(x: 225, y: 233, width: 574, height: 574))
    color(174, 245, 255, 0.33).setStroke()
    outerHighlight.lineWidth = 2
    outerHighlight.stroke()

    for endpoint in [NSPoint(x: 260, y: 555), NSPoint(x: 764, y: 555), NSPoint(x: 512, y: 268)] {
        let spoke = NSBezierPath()
        spoke.move(to: center)
        spoke.line(to: endpoint)
        spoke.lineCapStyle = .round
        spoke.lineWidth = 42
        color(41, 162, 228).setStroke()
        spoke.stroke()
        spoke.lineWidth = 2
        color(157, 239, 255, 0.25).setStroke()
        spoke.stroke()
    }

    let hub = NSBezierPath(ovalIn: NSRect(x: 407, y: 415, width: 210, height: 210))
    NSGradient(colors: [color(16, 37, 66), color(31, 69, 102)])!.draw(in: hub, angle: 90)
    hub.lineWidth = 5
    color(86, 215, 255).setStroke()
    hub.stroke()
    let lengths: [CGFloat] = [34, 64, 100, 64, 34]
    for (index, length) in lengths.enumerated() {
        let x = CGFloat(462 + index * 25)
        let bar = NSBezierPath(roundedRect: NSRect(x: x, y: center.y - length / 2, width: 10, height: length), xRadius: 5, yRadius: 5)
        color(204, 251, 255).setFill()
        bar.fill()
    }

    // The top marker makes the wheel readable at small Dock/sidebar sizes.
    let marker = NSBezierPath(roundedRect: NSRect(x: 502, y: 760, width: 20, height: 48), xRadius: 8, yRadius: 8)
    color(232, 255, 255).setFill()
    marker.fill()
}

func render(size: Int, destination: URL) throws {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    let context = NSGraphicsContext(bitmapImageRep: bitmap)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    context.shouldAntialias = true
    let transform = NSAffineTransform()
    transform.scale(by: CGFloat(size) / 1024)
    transform.concat()
    artwork()
    NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using: .png, properties: [:])!.write(to: destination)
}

for size in [16, 32, 128, 256, 512] {
    try render(size: size, destination: iconset.appendingPathComponent("icon_\(size)x\(size).png"))
    try render(size: size * 2, destination: iconset.appendingPathComponent("icon_\(size)x\(size)@2x.png"))
}
try render(size: 1024, destination: output.appendingPathComponent("AppIcon.png"))
// PNG-compressed ICNS elements are supported by macOS directly. Writing the
// container here keeps generation deterministic without iconutil's XPC service.
func bigEndian(_ value: Int) -> Data {
    var encoded = UInt32(value).bigEndian
    return withUnsafeBytes(of: &encoded) { Data($0) }
}
var elements = Data()
for (type, pixels) in [("icp4", 16), ("icp5", 32), ("icp6", 64), ("ic07", 128), ("ic08", 256), ("ic09", 512), ("ic10", 1024)] {
    let source: String
    if pixels == 64 { source = "icon_32x32@2x.png" }
    else if pixels == 1024 { source = "icon_512x512@2x.png" }
    else { source = "icon_\(pixels)x\(pixels).png" }
    let png = try Data(contentsOf: iconset.appendingPathComponent(source))
    elements.append(type.data(using: .ascii)!)
    elements.append(bigEndian(png.count + 8))
    elements.append(png)
}
var container = "icns".data(using: .ascii)!
container.append(bigEndian(elements.count + 8))
container.append(elements)
let destination = output.appendingPathComponent("AppIcon.icns")
try container.write(to: destination)
guard let icon = NSImage(contentsOf: destination), !icon.representations.isEmpty else {
    throw NSError(domain: "IconGeneration", code: 1, userInfo: [NSLocalizedDescriptionKey: "Generated ICNS could not be decoded by AppKit"])
}
try files.removeItem(at: iconset)
print(output.appendingPathComponent("AppIcon.icns").path)
