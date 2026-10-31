import SwiftUI
import AppKit

@MainActor enum ScreenshotCapture {
    private static var started = false
    static func run(model: AppModel, directory: String) async {
        guard !started else { return }
        started = true
        do {
            try FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
            NSApp.appearance = NSAppearance(named: .aqua)
            model.fixtures = true
            try await Task.sleep(for: .seconds(1))
            let screens: [(String, () -> Void)] = [
                ("sign-in", { model.user = nil }),
                ("learn", { model.loadFixtures() }),
                ("course", { model.destination = .course }),
                ("plan", { model.destination = .plan }),
                ("plan-option-2", { model.optionIndex = 1 }),
                ("plan-option-3", { model.optionIndex = 2 }),
                ("ta", { model.loadFixtures(role: "ta") }),
                ("instructor", { model.loadFixtures(role: "instructor") }),
                ("moodle", { model.loadFixtures(role: "instructor"); model.destination = .moodle })
            ]
            for (name, prepare) in screens {
                prepare()
                try await captureScene(name: name, directory: directory)
            }
            NSApp.appearance = NSAppearance(named: .darkAqua)
            model.loadFixtures()
            try await capture(RootView(model: model), name: "learn-dark", directory: directory, size: NSSize(width: 1320, height: 960), scheme: .dark)
            model.destination = .plan
            try await capture(RootView(model: model), name: "plan-dark", directory: directory, size: NSSize(width: 1320, height: 960), scheme: .dark)
            NSApp.appearance = NSAppearance(named: .aqua)
            model.user = nil
            try await capture(AuthView(model: model, settings: .constant(false), initialSignup: true), name: "sign-up", directory: directory, size: NSSize(width: 1320, height: 960))
            model.document = Fixtures.load().document
            try await capture(DocumentReader(model: model), name: "document", directory: directory, size: NSSize(width: 760, height: 700))
            if let option = Fixtures.load().plan.options?.first {
                try await capture(VStack(alignment: .leading, spacing: 20) {
                    PageHeading(title: "Option 1 · Your sections", subtitle: "Sample data · 13 credits · ★ 4.4 average rating")
                    ForEach(Array((option.sections ?? []).enumerated()), id: \.offset) { _, section in SectionRow(section: section) }
                }.padding(30).background(Color.wolfPaper), name: "plan-sections", directory: directory, size: NSSize(width: 920, height: 500))
            }
            print("Screenshots saved to \(directory)")
            NSApplication.shared.terminate(nil)
        } catch { fputs("Screenshot capture failed: \(error)\n", stderr); exit(1) }
    }
    private static func captureScene(name: String, directory: String) async throws {
        guard let window = NSApp.windows.first(where: { $0.contentView != nil && !($0 is NSPanel) }), let content = window.contentView else { throw CocoaError(.fileReadUnknown) }
        window.setContentSize(NSSize(width: 1320, height: 960))
        window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        try await Task.sleep(for: .milliseconds(400))
        content.layoutSubtreeIfNeeded(); window.displayIfNeeded()
        let frame = content.superview ?? content
        guard let bitmap = frame.bitmapImageRepForCachingDisplay(in: frame.bounds) else { throw CocoaError(.fileWriteUnknown) }
        frame.cacheDisplay(in: frame.bounds, to: bitmap)
        guard let png = bitmap.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
        try png.write(to: URL(fileURLWithPath: directory).appendingPathComponent("\(name).png"))
    }
    private static func capture<V: View>(_ view: V, name: String, directory: String, size: NSSize, scheme: ColorScheme = .light) async throws {
        let host = NSHostingView(rootView: view.environment(\.colorScheme, scheme))
        let window = NSWindow(contentRect: NSRect(origin: .zero, size: size), styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.appearance = NSAppearance(named: scheme == .dark ? .darkAqua : .aqua)
        window.title = "WolfBox · \(name)"; window.contentView = host
        window.setContentSize(size); window.center(); window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        try await Task.sleep(for: .milliseconds(350))
        host.layoutSubtreeIfNeeded(); window.displayIfNeeded()
        guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { throw CocoaError(.fileWriteUnknown) }
        host.cacheDisplay(in: host.bounds, to: bitmap)
        guard let png = bitmap.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
        try png.write(to: URL(fileURLWithPath: directory).appendingPathComponent("\(name).png"))
        window.orderOut(nil)
    }
}
